#!/usr/bin/env python3
"""Auxlo Evolution Engine - Full adaptive evolution loop."""

import json
import subprocess
from pathlib import Path
from collections import Counter
from openai import OpenAI

# Config
MODEL = "stepfun-ai/step-3.5-flash"
BASE_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = "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"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

WORKSPACE_ROOT = Path("/home/workspace/auxlo/auxlo_agent")
SKILL_THRESHOLD = 3
MEMORY_CAP = 20

# Skill templates
SKILL_TEMPLATES = {
    "timeout": """---
name: timeout-handler
description: Handle command timeouts gracefully
---

# Timeout Handler

When commands timeout:
1. Try simpler/faster equivalent
2. Use timeout flag or reduce scope
3. Check target exists and is accessible
4. Report partial results if available
""",
    "permission": """---
name: permission-handler
description: Handle permission errors
---

# Permission Handler

On permission errors:
1. Check permissions: ls -la /path/
2. Use sudo if appropriate
3. Verify path exists
4. Try alternative locations
""",
    "not_found": """---
name: file-checker
description: Verify file existence before operations
---

# File Checker

Before file operations:
1. Check existence: ls -la /path/
2. Check parent: ls /parent/
3. Create parent if needed: mkdir -p
4. Use absolute paths
""",
}

def read_prompt():
    path = WORKSPACE_ROOT / "prompts" / "system.md"
    return path.read_text() if path.exists() else ""

def write_prompt(content):
    (WORKSPACE_ROOT / "prompts" / "system.md").write_text(content)

def list_skills():
    skills = []
    for d in (WORKSPACE_ROOT / "skills").glob("*"):
        if d.is_dir():
            f = d / "SKILL.md"
            if f.exists():
                skills.append(f.read_text())
    return skills

def write_skill(name, content):
    d = WORKSPACE_ROOT / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(content)

def delete_skill(name):
    import shutil
    d = WORKSPACE_ROOT / "skills" / name
    if d.exists():
        shutil.rmtree(d)

def get_memory():
    f = WORKSPACE_ROOT / "memory" / "episodic.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().strip().split("\n") if l]

def add_memory(entry):
    f = WORKSPACE_ROOT / "memory" / "episodic.jsonl"
    f.open("a").write(json.dumps(entry) + "\n")
    # Prune
    lines = f.read_text().strip().split("\n")
    if len(lines) > MEMORY_CAP:
        f.write_text("\n".join(lines[-MEMORY_CAP:]) + "\n")

def git_commit(msg, tag=None):
    subprocess.run(["git", "add", "."], cwd=WORKSPACE_ROOT, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=WORKSPACE_ROOT, capture_output=True)
    if tag:
        subprocess.run(["git", "tag", "-a", tag, "-m", tag], cwd=WORKSPACE_ROOT, capture_output=True)

def git_rollback(tag):
    subprocess.run(["git", "reset", "--hard", tag], cwd=WORKSPACE_ROOT, capture_output=True)

def analyze_failures(observations):
    patterns = Counter()
    for obs in observations:
        if not obs.get("success"):
            feedback = obs.get("feedback", "").lower()
            if "timeout" in feedback:
                patterns["timeout"] += 1
            elif "permission" in feedback:
                patterns["permission"] += 1
            elif "not found" in feedback:
                patterns["not_found"] += 1
    return patterns

def auto_seed_skills(failure_patterns):
    seeded = []
    for pattern, count in failure_patterns.items():
        if count >= SKILL_THRESHOLD:
            skill_name = f"{pattern}-handler"
            skill_dir = WORKSPACE_ROOT / "skills" / skill_name
            if not skill_dir.exists() and pattern in SKILL_TEMPLATES:
                write_skill(skill_name, SKILL_TEMPLATES[pattern])
                seeded.append(skill_name)
                print(f"  Auto-seeded skill: {skill_name}")
    return seeded

def llm_evolve(pass_rate, patterns, cycle):
    """Use LLM to propose prompt improvements."""
    if pass_rate >= 0.9:
        return False
    
    prompt = f"""Analyze task failures and propose prompt improvements.

Pass rate: {pass_rate:.1%}
Failure patterns: {dict(patterns)}

Current prompt:
{read_prompt()[:2000]}

Current skills: {[str(d.name) for d in (WORKSPACE_ROOT / "skills").glob("*") if d.is_dir()]}

Propose a concise improvement to the system prompt. Return the new prompt.
Start with "NEW_PROMPT:" followed by the improved prompt.
"""
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.5
        )
        content = resp.choices[0].message.content or ""
        if "NEW_PROMPT:" in content:
            new_prompt = content.split("NEW_PROMPT:")[-1].strip()
            if len(new_prompt) < len(read_prompt()) * 3:  # Sanity check
                write_prompt(new_prompt)
                print(f"  LLM improved prompt")
                return True
    except Exception as e:
        print(f"  LLM evolve failed: {e}")
    return False

def run_evolution():
    print("=== Auxlo Evolution Engine ===\n")
    
    # Analyze recent observations
    memory = get_memory()
    observations = [{"success": m.get("success", False), "feedback": ""} for m in memory]
    
    patterns = analyze_failures(observations)
    pass_rate = sum(1 for o in observations if o["success"]) / max(len(observations), 1)
    
    print(f"Pass rate: {pass_rate:.1%}")
    print(f"Total tasks: {len(observations)}")
    print(f"Failure patterns: {dict(patterns)}")
    
    if not patterns:
        print("\nNo failures detected. Evolution not needed.")
        return
    
    # Pre-evolution snapshot
    git_commit(f"pre-evolution: {pass_rate:.3f}", f"pre-evolution")
    
    mutations = 0
    
    # Auto-seed skills
    seeded = auto_seed_skills(patterns)
    mutations += len(seeded)
    
    # LLM-driven evolution
    if llm_evolve(pass_rate, patterns, 1):
        mutations += 1
    
    # Post-evolution snapshot
    git_commit(f"evolution: {mutations} mutations")
    
    print(f"\nEvolution complete: {mutations} mutations")

if __name__ == "__main__":
    run_evolution()
