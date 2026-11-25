#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.." || exit 1

MACHINE=${1:?"Missing machine name. Example: scripts/run_bench.sh mac_m5"}
MODE=${2:-full}
OUT=results/$MACHINE
mkdir -p "$OUT"

HW=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)

REPS=${REPS:-3}
P1_TOTAL=${P1_TOTAL:-10000}
P1_N=${P1_N:-10007}
P1_OW=${P1_OW:-"0 1 2 4"}
P2_EPI=${P2_EPI:-100000}
P2_EPI_SLOW=${P2_EPI_SLOW:-2000}
P3_TOTAL=${P3_TOTAL:-2000000}
P3_TOTAL_SLOW=${P3_TOTAL_SLOW:-100000}
export BENCH_TIMEOUT=${BENCH_TIMEOUT:-30}

if [ "$MODE" = "quick" ]; then
    REPS=1; P1_TOTAL=2000; P1_OW="0 1"; P2_EPI=20000; P2_EPI_SLOW=500
    P3_TOTAL=200000; P3_TOTAL_SLOW=20000; export BENCH_TIMEOUT=10
fi

THREADS=""
for t in 1 2 4 8 16 32 64 128; do [ "$t" -lt "$HW" ] && THREADS="$THREADS $t"; done
THREADS="$THREADS $HW $((HW + HW / 2)) $((HW * 2))"

echo "Machine: $MACHINE | hardware threads: $HW | thread counts: $THREADS | REPS=$REPS | timeout=${BENCH_TIMEOUT}s"
make -s bench_lock bench_barrier bench_counter ${MAKE_ARGS:-} || { echo "Build failed"; exit 1; }

available() {
    local prog=$1; shift
    for n in "$@"; do BENCH_TIMEOUT=5 ./$prog "$n" $TRY >/dev/null 2>&1 && printf '%s ' "$n"; done
}
TRY="1 10 0 7";   LOCKS=$(available bench_lock tas tas_bo_sleep tas_bo_spin ttas ttas_bo_sleep ttas_bo_spin mcs std pthread omp)
TRY="1 10";       BARRIERS=$(available bench_barrier sr sr_bo_spin sr_bo_sleep std pthread omp)
TRY="1 10";       COUNTERS=$(available bench_counter lock_tas lock_tas_bo_spin lock_ttas lock_ttas_bo_spin lock_mcs lock_std lock_pthread lock_omp cas cas_bo_spin cas_bo_sleep faa sharded)
echo "Locks   : $LOCKS"
echo "Barriers: $BARRIERS"
echo "Counters: $COUNTERS"

DEAD=" "
is_dead() { case "$DEAD" in *" $1 "*) return 0 ;; esac; return 1; }
record() {
    local file=$1 key=$2 rep=$3; shift 3
    local line
    line=$("$@" 2>/dev/null | tail -n 1)
    [ -z "$line" ] && return
    echo "$MACHINE,$HW,$rep,$line" >> "$file"
    case "$line" in *",-1,0"|*",-1") DEAD="$DEAD$key "; echo "   TIMEOUT: $key (skipping larger thread counts)" ;; esac
}

START=$(date +%s)

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
