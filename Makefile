# Makefile for Parallel Computing - Assignment 2
# Recipe lines start with '>' instead of TAB (see .RECIPEPREFIX),
# so copy-pasting from a browser cannot break the file.
.RECIPEPREFIX = >

# ---- Paths: declare ROOT first, every other folder is built from ROOT ----
ROOT   := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
INC    := $(ROOT)/include
SRC    := $(ROOT)/src
BUILD  := $(ROOT)/build
DIST   := $(ROOT)/dist

# ---- Compiler settings ----
CXX       ?= g++
CXXFLAGS  := -std=c++20 -O2 -Wall -Wextra -pthread -I$(INC)
TSANFLAGS := -std=c++20 -O1 -g -fsanitize=thread -pthread -I$(INC)

# ---- Thread counts used by the tests ----
NPROC  := $(shell nproc)
NPROC2 := $(shell echo $$(( 2 * $(NPROC) )))

HEADERS := $(wildcard $(INC)/*.h)

.PHONY: all astar test tsan dist clean

# Default target: build the list test
all: $(BUILD)/test_list

$(BUILD):
> mkdir -p $@

# ---- Part 2: concurrent sorted list ----
$(BUILD)/test_list: $(SRC)/test_list.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

$(BUILD)/test_list_tsan: $(SRC)/test_list.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(TSANFLAGS) $< -o $@

# ---- Part 3: sequential A* in C++ (speedup baseline) ----
$(BUILD)/astar_seq: $(SRC)/astar_seq.cpp $(HEADERS) | $(BUILD)
> $(CXX) $(CXXFLAGS) $< -o $@

astar: $(BUILD)/astar_seq

# ---- Correctness tests: threads = cores, then 2 x cores ----
# With 2 x cores, spin locks get very slow (the lock holder is descheduled
# while others spin), so use fewer ops per thread to stay inside the watchdog limit.
OPS_OVER := 200

test: $(BUILD)/test_list
> @echo "== test_list, $(NPROC) threads (= logical cores) =="
> $(BUILD)/test_list $(NPROC)
> @echo "== test_list, $(NPROC2) threads (2 x logical cores), $(OPS_OVER) ops/thread =="
> $(BUILD)/test_list $(NPROC2) $(OPS_OVER) 2

# ---- Data-race check with ThreadSanitizer ----
# TSan makes the program 5-15x slower, so use fewer ops and repeats.
# Fail if TSan reports a race OR the program itself fails (e.g. watchdog timeout).
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

# ---- Submission zip (limit 20 MB) ----
REPORT ?= DHY_Parallel_Computing_Assignment_2.pdf
ZIP    := $(DIST)/DHY_Assignment2_submission.zip
LIMIT  := 20971520

dist:
> mkdir -p $(DIST)
> rm -f $(ZIP)
> @test -f $(ROOT)/$(REPORT) || echo "WARNING: report $(REPORT) not found in $(ROOT)"
> cd $(ROOT) && zip -r $(ZIP) Makefile include src python scripts results \
>   $(notdir $(wildcard $(ROOT)/*.md)) $(wildcard $(REPORT)) \
>   -x "*__pycache__*" "data/*" "build/*"
> @size=$$(stat -c %s $(ZIP)); \
>   if [ $$size -gt $(LIMIT) ]; then echo "FAIL: zip is $$size bytes (> 20 MB)"; exit 1; \
>   else echo "OK: zip is $$size bytes (< 20 MB)"; fi

clean:
> rm -rf $(BUILD) $(DIST)
