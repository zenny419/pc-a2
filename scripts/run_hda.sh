#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
DATA="$ROOT/data"
MACHINE="${1:?usage: run_hda.sh <machine>}"
OUT="$ROOT/results/$MACHINE"
RUNS="${RUNS:-5}"
NPAIRS="${NPAIRS:-10}"
NP="$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
TLIST="${THREADS:-1 2 4 8 $NP $((2 * NP))}"
TLIST="$(echo $TLIST | tr ' ' '\n' | sort -n | uniq | tr '\n' ' ')"
BATCHES="${BATCHES:-1 64}"

cd "$ROOT" || exit 1
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run_hda.log") 2>&1
echo "== start $(date '+%F %T') machine=$MACHINE nproc=$NP threads=[$TLIST] runs=$RUNS pairs=$NPAIRS batches=[$BATCHES]"
make all hda || exit 1

echo "== test_astar_hda ($(date +%T))"
./build/test_astar_hda "$DATA/nodes.csv" "$DATA/edges.csv" 50 7 "$NP" | tee "$OUT/test_astar_hda.txt"
make tsan_hda 2>&1 | tail -n 2 | tee "$OUT/tsan_hda.txt"

echo "== astar hda ($(date +%T))"
echo "variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,list_len_avg,ms" > "$OUT/astar_hda_ref.csv"
echo "variant,threads,run,src,dst,cost_m,expanded,stale_pops,pruned,remote_msgs,remote_frac,imbalance,ms" > "$OUT/astar_hda.csv"
for run in $(seq 1 "$RUNS"); do
    for set in teacher random; do
        if [ "$set" = teacher ]; then args="teacher 0"; else args="$NPAIRS 42"; fi
        "$BUILD/astar_par" "$DATA/nodes.csv" "$DATA/edges.csv" $args 0 "$run" | tail -n +2 >> "$OUT/astar_hda_ref.csv"
        for t in $TLIST; do
            "$BUILD/astar_par" "$DATA/nodes.csv" "$DATA/edges.csv" $args "$t" "$run" lazy pool | tail -n +2 >> "$OUT/astar_hda_ref.csv"
            for b in $BATCHES; do
                "$BUILD/astar_hda" "$DATA/nodes.csv" "$DATA/edges.csv" $args "$t" "$run" "$b" pool | tail -n +2 >> "$OUT/astar_hda.csv"
            done
        done
    done
    echo "astar hda run $run done ($(date +%T))"
done
echo "== done $(date '+%F %T')"
