#!/bin/bash
# Auxlo Autonomous Evolution Loop
# Runs the agent on benchmark tasks, analyzes results, improves harness

AUXLO_DIR="/home/workspace/auxlo"
cd "$AUXLO_DIR"

LOG_FILE="/home/workspace/auxlo/evolve.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$TIMESTAMP] === Auxlo Evolution Run Started ===" >> "$LOG_FILE"
echo "[$TIMESTAMP] Current commit: $(git rev-parse --short HEAD)" >> "$LOG_FILE"

# Initialize results tracking
touch results.tsv

# Check if there are tasks to run
if [ ! -d "tasks" ] || [ -z "$(ls -A tasks/ 2>/dev/null)" ]; then
    echo "[$TIMESTAMP] No tasks found in tasks/ directory" >> "$LOG_FILE"
    echo "[$TIMESTAMP] Creating sample task..." >> "$LOG_FILE"
    mkdir -p tasks
fi

# Run agent on each task
TOTAL=0
PASSED=0

for TASK_FILE in tasks/*.md tasks/*.txt 2>/dev/null; do
    [ -e "$TASK_FILE" ] || continue
    
    TASK_NAME=$(basename "$TASK_FILE" .md)
    TASK_NAME=${TASK_NAME%.txt}
    TOTAL=$((TOTAL + 1))
    
    echo "[$TIMESTAMP] Running task: $TASK_NAME" >> "$LOG_FILE"
    
    # Copy task to instruction location
    mkdir -p /task
    cp "$TASK_FILE" /task/instruction.md
    
    # Run the agent
    TASK_LOG="/tmp/auxlo_task_${TASK_NAME}.log"
    timeout 300 uv run python auxlo.py 2>&1 | tee "$TASK_LOG"
    
    # Check result (look for success indicators)
    if grep -qi "success\|complete\|done\|passed" "$TASK_LOG" 2>/dev/null; then
        PASSED=$((PASSED + 1))
        STATUS="PASS"
    else
        STATUS="FAIL"
    fi
    
    echo "[$TIMESTAMP] Task $TASK_NAME: $STATUS" >> "$LOG_FILE"
    
    # Clean up
    rm -rf /task
done

# Log summary
echo "[$TIMESTAMP] Results: $PASSED/$TOTAL tasks passed" >> "$LOG_FILE"

# Analyze and suggest improvements (placeholder for meta-agent logic)
if [ $TOTAL -gt 0 ]; then
    SCORE=$(python3 -c "print($PASSED / $TOTAL)")
    echo "[$TIMESTAMP] Score: $SCORE" >> "$LOG_FILE"
    
    # Log to results.tsv
    COMMIT=$(git rev-parse --short HEAD)
    echo -e "${COMMIT}\t${SCORE}\t${PASSED}/${TOTAL}\t\t\t\t" >> results.tsv
fi

echo "[$TIMESTAMP] === Run Complete ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"