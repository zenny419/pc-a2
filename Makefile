.RECIPEPREFIX = >

ROOT   := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
INC    := $(ROOT)/include
SRC    := $(ROOT)/src
BUILD  := $(ROOT)/build
DIST   := $(ROOT)/dist

CXX       ?= g++
CXXFLAGS  := -std=c++20 -O2 -Wall -Wextra -pthread -I$(INC)
TSANFLAGS := -std=c++20 -O1 -g -fsanitize=thread -pthread -I$(INC)

NPROC  := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu)
NPROC2 := $(shell echo $$(( 2 * $(NPROC) )))

HEADERS := $(wildcard $(INC)/*.h)

.PHONY: all astar test tsan bench dist clean test_astar tsan_astar

all: $(BUILD)/test_list $(BUILD)/bench_list $(BUILD)/astar_seq $(BUILD)/astar_par $(BUILD)/test_astar_par $(BUILD)/astar_batch $(BUILD)/spawn_bench

$(BUILD):
> mkdir -p $@

$(BUILD)/test_list: $(SRC)/test_list.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

$(BUILD)/bench_list: $(SRC)/bench_list.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

$(BUILD)/test_list_tsan: $(SRC)/test_list.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(TSANFLAGS) $< -o $@

$(BUILD)/astar_seq: $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

$(BUILD)/astar_par: $(SRC)/astar_par.cpp $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@
$(BUILD)/test_astar_par: $(SRC)/test_astar_par.cpp $(SRC)/astar_par.cpp $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@
$(BUILD)/test_astar_par_tsan: $(SRC)/test_astar_par.cpp $(SRC)/astar_par.cpp $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(TSANFLAGS) $< -o $@
$(BUILD)/astar_batch: $(SRC)/astar_batch.cpp $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@
$(BUILD)/spawn_bench: $(SRC)/spawn_bench.cpp | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

test_astar: $(BUILD)/test_astar_par
> $(BUILD)/test_astar_par $(ROOT)/data/nodes.csv $(ROOT)/data/edges.csv 50 7 $(NPROC)
tsan_astar: $(BUILD)/test_astar_par_tsan
> @$(BUILD)/test_astar_par_tsan $(ROOT)/data/nodes.csv $(ROOT)/data/edges.csv 5 7 4 > $(BUILD)/tsan_astar.log 2>&1; \
  status=$$?; cat $(BUILD)/tsan_astar.log; \
  if grep -q "WARNING: ThreadSanitizer" $(BUILD)/tsan_astar.log; then echo "TSAN: data race reported"; exit 1; fi; \
  echo "TSAN: clean"; exit $$status

astar: $(BUILD)/astar_seq

OPS_OVER := 200

test: $(BUILD)/test_list
> @echo "== test_list, $(NPROC) threads (= logical cores) =="
> $(BUILD)/test_list $(NPROC)
> @echo "== test_list, $(NPROC2) threads (2 x logical cores), $(OPS_OVER) ops/thread =="
> $(BUILD)/test_list $(NPROC2) $(OPS_OVER) 2

TSAN_OPS  := 2000
TSAN_REPS := 2

tsan: $(BUILD)/test_list_tsan
> @$(BUILD)/test_list_tsan $(NPROC) $(TSAN_OPS) $(TSAN_REPS) > $(BUILD)/tsan.log 2>&1; \
>   status=$$?; cat $(BUILD)/tsan.log; \
>   if grep -q "WARNING: ThreadSanitizer" $(BUILD)/tsan.log; then \
>     echo "TSAN: data race reported (see build/tsan.log)"; exit 1; \
>   elif [ $$status -ne 0 ]; then \
>     echo "TSAN: program failed (exit $$status) -> result NOT valid"; exit 1; \
>   else echo "TSAN: clean"; fi

REPORT ?= DHY_Parallel_Computing_Assignment_2.pdf
ZIP    := $(DIST)/DHY_Assignment2_submission.zip
LIMIT  := 20971520

dist:
> mkdir -p $(DIST)
> rm -f $(ZIP)
> @test -f $(ROOT)/$(REPORT) || echo "WARNING: report $(REPORT) not found in $(ROOT)"
> cd $(ROOT) && zip -r $(ZIP) Makefile include src python scripts results \
>   $(notdir $(wildcard $(ROOT)/*.md)) $(wildcard $(REPORT)) \
>   -x "*__pycache__*" "data/*" "build/*" "*.bak"
> @size=$$(stat -c %s $(ZIP)); \
>   if [ $$size -gt $(LIMIT) ]; then echo "FAIL: zip is $$size bytes (> 20 MB)"; exit 1; \
>   else echo "OK: zip is $$size bytes (< 20 MB)"; fi

VARIANTS := coarse+ttas coarse+ttas_bo coarse+std fine+ttas fine+ttas_bo fine+std

bench: $(BUILD)/bench_list
> @for v in $(VARIANTS); do $(BUILD)/bench_list $$v $(NPROC) 1; done

clean:
> rm -rf $(BUILD) $(DIST)
