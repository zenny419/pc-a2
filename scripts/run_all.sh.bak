#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
DATA="$ROOT/data"
MACHINE="${1:-$(hostname)}"
OUT="$ROOT/results/$MACHINE"
RUNS="${RUNS:-5}"
SECS="${SECS:-2}"
NPAIRS="${NPAIRS:-10}"
NP="$(nproc)"
THREADS="${THREADS:-1 2 4 8 $NP $((2 * NP))}"
TLIST="$(echo $THREADS | tr ' ' '\n' | sort -n | uniq | tr '\n' ' ')"
VARIANTS="${VARIANTS:-coarse+ttas coarse+ttas_bo coarse+std fine+ttas fine+ttas_bo fine+std lazy+ttas lazy+ttas_bo}"
AS_TIMEOUT="${AS_TIMEOUT:-1800}"
CXXF="-std=c++20 -O2 -Wall -Wextra -I$ROOT/include -pthread"

mkdir -p "$OUT" "$BUILD"
cd "$ROOT"
exec > >(tee -a "$OUT/run_all.log") 2>&1

echo "== start $(date '+%F %T') machine=$MACHINE nproc=$NP threads=[$TLIST] runs=$RUNS secs=$SECS pairs=$NPAIRS"

while pgrep -f exp_pareto.py > /dev/null; do
    echo "waiting for exp_pareto.py to finish ($(date +%T))"
    sleep 60
done

echo "== build"
make all || exit 1
g++ $CXXF src/astar_par.cpp -o "$BUILD/astar_par" || exit 1
g++ $CXXF src/test_astar_par.cpp -o "$BUILD/test_astar_par" || exit 1

echo "== sysinfo"
{
    date '+%F %T'
    uname -a
    lscpu
    echo "nproc: $NP"
    free -h
    g++ --version | head -n 1
} > "$OUT/sysinfo.txt"

echo "== correctness: list"
make test 2>&1 | tail -n 40 | tee "$OUT/test_list.txt"

echo "== correctness: parallel A* ($(date +%T))"
./build/test_astar_par "$DATA/nodes.csv" "$DATA/edges.csv" 50 7 "$NP" | tee "$OUT/test_astar_par.txt"

echo "== tsan: parallel A* ($(date +%T))"
g++ -std=c++20 -O1 -g -fsanitize=thread -I"$ROOT/include" -pthread src/test_astar_par.cpp -o "$BUILD/test_astar_par_tsan" &&
    ./build/test_astar_par_tsan "$DATA/nodes.csv" "$DATA/edges.csv" 5 7 4 > "$OUT/tsan_astar.txt" 2>&1
if grep -q "WARNING: ThreadSanitizer" "$OUT/tsan_astar.txt"; then echo "TSAN astar: RACE REPORTED"; else echo "TSAN astar: clean"; fi
tail -n 3 "$OUT/tsan_astar.txt"

echo "== tsan: list ($(date +%T))"
make tsan 2>&1 | tail -n 15 | tee "$OUT/tsan_list.txt"

echo "== bench_list ($(date +%T))"
echo "variant,threads,run,ops_per_sec" > "$OUT/list.csv"
for run in $(seq 1 "$RUNS"); do
    for t in $TLIST; do
        for v in $VARIANTS; do
            out="$(timeout $((SECS * 10 + 60)) ./build/bench_list "$v" "$t" "$SECS" "$run")"
            rc=$?
            if [ $rc -eq 0 ]; then
                echo "$out" | grep -v '^variant' >> "$OUT/list.csv"
            else
                echo "$v,$t,$run,-1" >> "$OUT/list.csv"
                echo "bench_list $v $t run $run: rc=$rc"
            fi
        done
    done
    echo "list run $run done ($(date +%T))"
done

echo "== astar ($(date +%T))"
echo "variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,list_len_avg,ms" > "$OUT/astar.csv"
for run in $(seq 1 "$RUNS"); do
    for set in teacher random; do
        if [ "$set" = teacher ]; then args="teacher 0"; else args="$NPAIRS 42"; fi
        for t in 0 $TLIST; do
            out="$(timeout "$AS_TIMEOUT" ./build/astar_par "$DATA/nodes.csv" "$DATA/edges.csv" $args "$t" "$run")"
            rc=$?
            if [ $rc -eq 0 ]; then
                echo "$out" | tail -n +2 >> "$OUT/astar.csv"
            else
                echo "$out" | tail -n +2 >> "$OUT/astar.csv"
                echo "astar $set threads=$t run=$run: rc=$rc (124 = timeout after ${AS_TIMEOUT}s)"
            fi
        done
        echo "astar run $run set $set done ($(date +%T))"
    done
done

echo "== done $(date '+%F %T')"
