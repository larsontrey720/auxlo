#!/bin/bash
# Auxlo Autonomous Evolution Loop
# This script runs the experiment loop and logs results

AUXLO_DIR="/home/workspace/auxlo"
cd "$AUXLO_DIR"

LOG_FILE="/home/workspace/auxlo/evolve.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] === Auxlo Evolution Run Started ===" >> "$LOG_FILE"

# Source environment if needed
if [ -f ".env" ]; then
    set -a && source .env && set +a
fi

# Ensure results.tsv exists
if [ ! -f "results.tsv" ]; then
    echo -e "commit\tavg_score\tpassed\ttask_scores\tcost_usd\tstatus\tdescription" > results.tsv
fi

# Get current commit hash
COMMIT=$(git rev-parse --short HEAD)
echo "[$TIMESTAMP] Current commit: $COMMIT" >> "$LOG_FILE"

# Run the benchmark
echo "[$TIMESTAMP] Running benchmark..." >> "$LOG_FILE"
rm -rf jobs; mkdir -p jobs

timeout 1800 uv run harbor run -p tasks/ --agent-import-path auxlo:Auxlo -o jobs >> "$LOG_FILE" 2>&1
RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "[$TIMESTAMP] Benchmark completed successfully" >> "$LOG_FILE"
elif [ $RESULT -eq 124 ]; then
    echo "[$TIMESTAMP] Benchmark timed out (30min)" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] Benchmark failed with code: $RESULT" >> "$LOG_FILE"
fi

# Parse results if available
if [ -d "jobs" ]; then
    PASSED=$(find jobs -name "*.passed" 2>/dev/null | wc -l)
    TOTAL=$(find jobs -name "*.json" 2>/dev/null | wc -l)
    echo "[$TIMESTAMP] Results: $PASSED/$TOTAL tasks passed" >> "$LOG_FILE"
    
    # Check for improvements
    LAST_LINE=$(tail -1 results.tsv 2>/dev/null)
    if [ -n "$LAST_LINE" ]; then
        echo "[$TIMESTAMP] Last results: $LAST_LINE" >> "$LOG_FILE"
    fi
fi

echo "[$TIMESTAMP] === Run Complete ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"