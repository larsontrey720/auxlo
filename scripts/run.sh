#!/bin/bash
set -e

AUXLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$AUXLO_DIR"

usage() {
    cat << EOF
Auxlo - Autonomous Agent Engineering Framework

Usage: ./scripts/run.sh <command> [options]

Commands:
  build          Build the auxlo-base Docker image
  single <task>  Run a single task
  all [concurr]  Run all tasks (default concurrency: 4)
  clean          Clean up Docker artifacts
  help           Show this help message

Examples:
  ./scripts/run.sh build
  ./scripts/run.sh single my-task
  ./scripts/run.sh all 8
  ./scripts/run.sh clean
EOF
}

build() {
    echo "Building auxlo-base Docker image..."
    docker build -f Dockerfile.base -t auxlo-base .
    echo "Build complete."
}

run_single() {
    local task="${1:?Usage: run_single <task-name>}"
    echo "Running task: $task"
    rm -rf jobs; mkdir -p jobs
    uv run harbor run -p tasks/ --task-name "$task" -l 1 -n 1 --agent-import-path auxlo:Auxlo -o jobs --job-name latest > run.log 2>&1
    echo "Done. See jobs/ and run.log"
}

run_all() {
    local concurrency="${1:-4}"
    echo "Running all tasks with concurrency: $concurrency"
    rm -rf jobs; mkdir -p jobs
    uv run harbor run -p tasks/ -n "$concurrency" --agent-import-path auxlo:Auxlo -o jobs --job-name latest > run.log 2>&1
    echo "Done. See jobs/ and run.log"
}

clean() {
    echo "Cleaning up Docker artifacts..."
    uv run harbor cache clean -f 2>/dev/null || true
    docker system prune -a -f 2>/dev/null || true
    echo "Clean complete."
}

case "${1:-help}" in
    build)    build ;;
    single)   run_single "$2" ;;
    all)      run_all "$2" ;;
    clean)    clean ;;
    help|*)   usage ;;
esac
