#!/bin/bash
# Auxlo Autonomous Evolution Loop

AUXLO_DIR="/home/workspace/auxlo"
cd "$AUXLO_DIR"

# Load environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

LOG_FILE="/home/workspace/auxlo/evolve.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] === Auxlo Evolution Run Started ===" | tee -a "$LOG_FILE"
echo "[$TIMESTAMP] Commit: $(git rev-parse --short HEAD)" | tee -a "$LOG_FILE"

TOTAL=0
PASSED=0

for TASK_FILE in tasks/*.md tasks/*.txt; do
    if [ ! -e "$TASK_FILE" ]; then
        continue
    fi
    
    TASK_NAME=$(basename "$TASK_FILE")
    TASK_NAME=${TASK_NAME%.md}
    TASK_NAME=${TASK_NAME%.txt}
    TOTAL=$((TOTAL + 1))
    
    echo "[$TIMESTAMP] Running: $TASK_NAME" | tee -a "$LOG_FILE"
    
    mkdir -p /task
    cp "$TASK_FILE" /task/instruction.md
    
    # Run with environment variables
    OUTPUT=$(timeout 300 env NVIDIA_API_KEY="$NVIDIA_API_KEY" NVIDIA_BASE_URL="${NVIDIA_BASE_URL:-https://integrate.api.nvidia.com/v1}" AUXLO_MODEL="${AUXLO_MODEL:-stepfun-ai/step-3.5-flash}" uv run python auxlo.py 2>&1)
    echo "$OUTPUT" >> "$LOG_FILE"
    
    # Check for success indicators
    if echo "$OUTPUT" | grep -qiE "(success|complete|done|passed|task completed)"; then
        PASSED=$((PASSED + 1))
        STATUS="PASS"
    else
        STATUS="FAIL"
    fi
    
    echo "[$TIMESTAMP] $TASK_NAME: $STATUS" | tee -a "$LOG_FILE"
    rm -rf /task
done

echo "" | tee -a "$LOG_FILE"
echo "[$TIMESTAMP] === SUMMARY ===" | tee -a "$LOG_FILE"
echo "[$TIMESTAMP] Results: $PASSED/$TOTAL passed" | tee -a "$LOG_FILE"

# Log to results.tsv
if [ $TOTAL -gt 0 ]; then
    COMMIT=$(git rev-parse --short HEAD)
    SCORE=$(python3 -c "print(round($PASSED / $TOTAL, 3))")
    echo -e "${COMMIT}\t${SCORE}\t${PASSED}/${TOTAL}\t\t\t\t" >> results.tsv
    cat results.tsv | tail -5 >> "$LOG_FILE"
fi

echo "[$TIMESTAMP] === Done ===" | tee -a "$LOG_FILE"