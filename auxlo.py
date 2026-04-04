#!/usr/bin/env python3
"""Auxlo CLI - One command to rule them all.

Usage:
    python auxlo.py add "task description"
    python auxlo.py run
    python auxlo.py config --model stepfun-ai/step-3.5-flash
    python auxlo.py status
    python auxlo.py logs
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path

AUXLO_DIR = Path(__file__).parent
TASKS_DIR = AUXLO_DIR / "tasks"
CONFIG_FILE = AUXLO_DIR / ".auxlo_config.json"

def load_config():
    """Load or create config."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {
        "model": os.environ.get("AUXLO_MODEL", "stepfun-ai/step-3.5-flash"),
        "base_url": os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key_env": "NVIDIA_API_KEY"
    }

def save_config(config):
    """Save config."""
    CONFIG_FILE.write_text(json.dumps(config, indent=2))

def cmd_add(task: str):
    """Add a new task."""
    TASKS_DIR.mkdir(exist_ok=True)
    
    # Generate filename from task
    name = re.sub(r"[^a-z0-9]", "_", task.lower())[:40]
    timestamp = len(list(TASKS_DIR.glob("*.md")))
    filename = TASKS_DIR / f"task_{timestamp:03d}_{name}.md"
    
    filename.write_text(f"# Task\n\n{task}\n")
    print(f"Added: {filename.name}")
    return filename

def cmd_run():
    """Run the evolution loop."""
    print("Starting Auxlo evolution...")
    result = subprocess.run(
        ["bash", str(AUXLO_DIR / "scripts" / "evolve.sh")],
        cwd=AUXLO_DIR,
        env={**os.environ, "AUXLO_RUNNING": "1"}
    )
    return result.returncode

def cmd_config(args):
    """Change configuration."""
    config = load_config()
    
    if args.model:
        config["model"] = args.model
        print(f"Model set to: {args.model}")
    
    if args.base_url:
        config["base_url"] = args.base_url
        print(f"Base URL set to: {args.base_url}")
    
    if args.api_key:
        config["api_key_env"] = args.api_key
        print(f"API key env var set to: {args.api_key}")
    
    save_config(config)
    return 0

def cmd_status():
    """Show status."""
    config = load_config()
    print(f"Model: {config['model']}")
    print(f"Base URL: {config['base_url']}")
    print(f"API Key Env: {config['api_key_env']}")
    print()
    
    tasks = list(TASKS_DIR.glob("*.md"))
    print(f"Tasks: {len(tasks)}")
    for t in tasks[:5]:
        print(f"  - {t.name}")
    if len(tasks) > 5:
        print(f"  ... and {len(tasks) - 5} more")
    print()
    
    results_file = AUXLO_DIR / "results.tsv"
    if results_file.exists():
        lines = results_file.read_text().strip().split("\n")
        if len(lines) > 1:
            last = lines[-1].split("\t")
            print(f"Last run: {last[2]} passed, score: {last[1]}")

def cmd_logs(lines: int = 20):
    """Show recent logs."""
    log_file = AUXLO_DIR / "evolve.log"
    if log_file.exists():
        content = log_file.read_text().split("\n")
        print("\n".join(content[-lines:]))
    else:
        print("No logs yet. Run `python auxlo.py run` first.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "add":
        if len(sys.argv) < 3:
            print("Usage: python auxlo.py add \"task description\"")
            sys.exit(1)
        sys.exit(0 if cmd_add(sys.argv[2]) else 1)
    
    elif cmd == "run":
        sys.exit(cmd_run())
    
    elif cmd == "config":
        import argparse
        parser = argparse.ArgumentParser(description="Configure Auxlo")
        parser.add_argument("--model")
        parser.add_argument("--base-url")
        parser.add_argument("--api-key")
        args = parser.parse_args(sys.argv[2:] if len(sys.argv) > 2 else [])
        sys.exit(cmd_config(args))
    
    elif cmd == "status":
        cmd_status()
        sys.exit(0)
    
    elif cmd == "logs":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        cmd_logs(lines)
        sys.exit(0)
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
