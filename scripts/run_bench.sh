#!/usr/bin/env bash
# =====================================================================
#  run_bench.sh — runs all benchmarks of Parts 1, 2, 3 on ONE machine
#  [Assignment: item 3 of each part: "performance and scalability study ... on all
#   shared-memory platforms you possess"]
#
#  Runs on: macOS (Terminal) and Windows (MSYS2 UCRT64 window).
#
#  Usage:      scripts/run_bench.sh <machine> [quick]
#    <machine>  : name of the results folder, e.g. mac_m5, dell_laptop, dell_pc
#    quick      : short trial run (~1-2 minutes) before the real measurement
#  Example:    scripts/run_bench.sh mac_m5
#
#  Output:     results/<machine>/part1_locks.csv
#               results/<machine>/part2_barriers.csv
#               results/<machine>/part3_counters.csv
#  Then plot:  python3 scripts/plot_results.py
#
#  Parameters can be changed with environment variables, e.g.:  REPS=5 P1_TOTAL=20000 scripts/run_bench.sh mac_m5
# =====================================================================
set -u
cd "$(dirname "$0")/.." || exit 1

MACHINE=${1:?"Missing machine name. Example: scripts/run_bench.sh mac_m5"}
MODE=${2:-full}
OUT=results/$MACHINE
mkdir -p "$OUT"

# Number of hardware threads (logical CPUs)
HW=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)

# ---------------- Parameters (default values) ----------------
REPS=${REPS:-3}                   # repetitions per configuration (the median is plotted)
P1_TOTAL=${P1_TOTAL:-10000}       # Part 1: TOTAL number of critical-section entries (divided evenly among the threads)
P1_N=${P1_N:-10007}               # Part 1: N is prime -> is_prime() always runs its full loop
P1_OW=${P1_OW:-"0 1 2 4"}         # Part 1: OUTSIDE_WORK values
P2_EPI=${P2_EPI:-100000}          # Part 2: number of episodes when threads <= HW
P2_EPI_SLOW=${P2_EPI_SLOW:-2000}  # Part 2: number of episodes when threads > HW or for sleeping barriers
P3_TOTAL=${P3_TOTAL:-2000000}     # Part 3: total number of inc() calls
P3_TOTAL_SLOW=${P3_TOTAL_SLOW:-100000}  # Part 3: when threads > HW or for sleeping counters
export BENCH_TIMEOUT=${BENCH_TIMEOUT:-30}   # seconds; exceeded -> recorded as seconds=-1

if [ "$MODE" = "quick" ]; then
    REPS=1; P1_TOTAL=2000; P1_OW="0 1"; P2_EPI=20000; P2_EPI_SLOW=500
    P3_TOTAL=200000; P3_TOTAL_SLOW=20000; export BENCH_TIMEOUT=10
fi

# Thread counts: 1 2 4 8 ... (< HW), HW, 1.5 x HW, 2 x HW
THREADS=""
for t in 1 2 4 8 16 32 64 128; do [ "$t" -lt "$HW" ] && THREADS="$THREADS $t"; done
THREADS="$THREADS $HW $((HW + HW / 2)) $((HW * 2))"

echo "Machine: $MACHINE | hardware threads: $HW | thread counts: $THREADS | REPS=$REPS | timeout=${BENCH_TIMEOUT}s"
make -s bench_lock bench_barrier bench_counter ${MAKE_ARGS:-} || { echo "Build failed"; exit 1; }

# Keep only the names supported on this machine (e.g. pthread barrier does not exist on the Mac)
available() {   # $1 = program, $2... = list of names, test arguments in variable TRY
    local prog=$1; shift
    for n in "$@"; do BENCH_TIMEOUT=5 ./$prog "$n" $TRY >/dev/null 2>&1 && printf '%s ' "$n"; done
}
TRY="1 10 0 7";   LOCKS=$(available bench_lock tas tas_bo_sleep tas_bo_spin ttas ttas_bo_sleep ttas_bo_spin mcs std pthread omp)
TRY="1 10";       BARRIERS=$(available bench_barrier sr sr_bo_spin sr_bo_sleep std pthread omp)
TRY="1 10";       COUNTERS=$(available bench_counter lock_tas lock_tas_bo_spin lock_ttas lock_ttas_bo_spin lock_mcs lock_std lock_pthread lock_omp cas cas_bo_spin cas_bo_sleep faa sharded)
echo "Locks   : $LOCKS"
echo "Barriers: $BARRIERS"
echo "Counters: $COUNTERS"

# Record one result line; on TIMEOUT, LARGER thread counts of the same configuration
# are skipped (they would certainly be even slower) -> saves measurement time.
# (No associative arrays, because macOS ships bash 3.2 by default)
DEAD=" "
is_dead() { case "$DEAD" in *" $1 "*) return 0 ;; esac; return 1; }
record() {   # $1 = file, $2 = configuration key, $3 = rep, $4... = command
    local file=$1 key=$2 rep=$3; shift 3
    local line
    line=$("$@" 2>/dev/null | tail -n 1)
    [ -z "$line" ] && return
    echo "$MACHINE,$HW,$rep,$line" >> "$file"
    case "$line" in *",-1,0"|*",-1") DEAD="$DEAD$key "; echo "   TIMEOUT: $key (skipping larger thread counts)" ;; esac
}

START=$(date +%s)

# ---------------- PART 1: Mutex locks ----------------
F1=$OUT/part1_locks.csv
echo "machine,hw_threads,rep,lock,threads,iters_per_thread,outside_work,N,seconds" > "$F1"
echo "== Part 1: Mutex locks"
for ow in $P1_OW; do
  for lock in $LOCKS; do
    for t in $THREADS; do
      key="$lock/ow$ow"; is_dead "$key" && continue
      iters=$((P1_TOTAL / t)); [ "$iters" -lt 1 ] && iters=1
      for r in $(seq 1 "$REPS"); do
        is_dead "$key" && break
        record "$F1" "$key" "$r" ./bench_lock "$lock" "$t" "$iters" "$ow" "$P1_N"
      done
    done
    echo "   done: $lock, OUTSIDE_WORK=$ow"
  done
done

# ---------------- PART 2: Barrier ----------------
F2=$OUT/part2_barriers.csv
echo "machine,hw_threads,rep,barrier,threads,episodes,seconds,episodes_per_sec" > "$F2"
echo "== Part 2: Barrier"
for b in $BARRIERS; do
  for t in $THREADS; do
    key="$b"; is_dead "$key" && continue
    e=$P2_EPI
    if [ "$t" -gt "$HW" ] || [[ "$b" == *sleep* ]]; then e=$P2_EPI_SLOW; fi
    for r in $(seq 1 "$REPS"); do
      is_dead "$key" && break
      record "$F2" "$key" "$r" ./bench_barrier "$b" "$t" "$e"
    done
  done
  echo "   done: $b"
done

# ---------------- PART 3: Concurrent counters ----------------
F3=$OUT/part3_counters.csv
echo "machine,hw_threads,rep,counter,threads,total_ops,seconds,mops_per_sec" > "$F3"
echo "== Part 3: Counters"
for c in $COUNTERS; do
  for t in $THREADS; do
    key="c_$c"; is_dead "$key" && continue
    n=$P3_TOTAL
    if [ "$t" -gt "$HW" ] || [[ "$c" == *sleep* ]]; then n=$P3_TOTAL_SLOW; fi
    for r in $(seq 1 "$REPS"); do
      is_dead "$key" && break
      record "$F3" "$key" "$r" ./bench_counter "$c" "$t" "$n"
    done
  done
  echo "   done: $c"
done

echo "Finished in $(( $(date +%s) - START )) seconds. Results in $OUT/"
