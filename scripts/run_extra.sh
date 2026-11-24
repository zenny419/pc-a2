#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
DATA="$ROOT/data"
MACHINE="${1:?usage: run_extra.sh <machine>}"
OUT="$ROOT/results/$MACHINE"
RUNS="${RUNS:-5}"
SECS="${SECS:-2}"
NPAIRS="${NPAIRS:-10}"
NP="$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
TLIST="${THREADS:-1 2 4 8 $NP $((2 * NP))}"
TLIST="$(echo $TLIST | tr ' ' '\n' | sort -n | uniq | tr '\n' ' ')"
PQ_VARIANTS="${PQ_VARIANTS:-coarse+ttas coarse+std fine+ttas fine+std lazy+ttas}"
AS_EXTRA="${AS_EXTRA:-list:create heap:create lazy:create list:pool heap:pool lazy:pool}"

cd "$ROOT" || exit 1
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run_extra.log") 2>&1
echo "== start $(date '+%F %T') machine=$MACHINE nproc=$NP threads=[$TLIST] runs=$RUNS secs=$SECS pairs=$NPAIRS"
make all || exit 1

echo "== test_astar_par ($(date +%T))"
./build/test_astar_par "$DATA/nodes.csv" "$DATA/edges.csv" 50 7 "$NP" | tee "$OUT/test_astar_par_extra.txt"
make tsan_astar 2>&1 | tail -n 2 | tee "$OUT/tsan_astar_extra.txt"

echo "== bench_list pq ($(date +%T))"
echo "variant,threads,run,ops_per_sec" > "$OUT/list_pq.csv"
for run in $(seq 1 "$RUNS"); do
    for t in $TLIST; do
        for v in $PQ_VARIANTS; do
            out="$("$BUILD/bench_list" "$v" "$t" "$SECS" "$run" pq)"
            rc=$?
            if [ $rc -eq 0 ]; then echo "$out" >> "$OUT/list_pq.csv"; else echo "$v,$t,$run,-1" >> "$OUT/list_pq.csv"; echo "bench_list pq $v $t run $run: rc=$rc"; fi
        done
    done
    echo "list pq run $run done ($(date +%T))"
done

echo "== astar extra ($(date +%T))"
echo "variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,list_len_avg,ms" > "$OUT/astar_extra.csv"
for run in $(seq 1 "$RUNS"); do
    for set in teacher random; do
        if [ "$set" = teacher ]; then args="teacher 0"; else args="$NPAIRS 42"; fi
        "$BUILD/astar_par" "$DATA/nodes.csv" "$DATA/edges.csv" $args 0 "$run" | tail -n +2 >> "$OUT/astar_extra.csv"
        for t in $TLIST; do
            for av in $AS_EXTRA; do
                "$BUILD/astar_par" "$DATA/nodes.csv" "$DATA/edges.csv" $args "$t" "$run" "${av%%:*}" "${av##*:}" | tail -n +2 >> "$OUT/astar_extra.csv"
            done
        done
    done
    echo "astar extra run $run done ($(date +%T))"
done
echo "== done $(date '+%F %T')"
