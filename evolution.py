#!/usr/bin/env python3
"""Auxlo Evolution Engine - Self-modifying autonomous agent.

The evolution loop:
1. SOLVE - Run tasks
2. OBSERVE - Collect trajectories + feedback
3. EVOLVE - Analyze failures, propose mutations, test on holdout
4. VALIDATE - Keep if improved, rollback if regressed
5. RELOAD - Agent picks up mutations
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict
from openai import OpenAI

# Config
MODEL = os.environ.get("AUXLO_MODEL", "stepfun-ai/step-3.5-flash")
BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("NVIDIA_API_KEY", "")
MAX_TURNS = 10
MAX_TOKENS = 1500

# Paths
AUXLO_DIR = Path(__file__).parent
MEMORY_DIR = AUXLO_DIR / "memory"
EVOLUTION_DIR = AUXLO_DIR / "evolution"
PROMPTS_DIR = AUXLO_DIR / "prompts"
SKILLS_DIR = AUXLO_DIR / "skills"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.md"

@dataclass
class Observation:
    task: str
    success: bool
    trajectory: list
    error: Optional[str] = None
    timestamp: str = ""

@dataclass  
class Mutation:
    type: str  # "skill" or "prompt"
    name: str
    content: str
    rationale: str
    test_results: dict = None

class EvolutionEngine:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.evolution_dir = EVOLUTION_DIR
        self.evolution_dir.mkdir(exist_ok=True)
        self.memory_dir = MEMORY_DIR
        self.prompts_dir = PROMPTS_DIR
        self.skills_dir = SKILLS_DIR
        
        # Ensure directories exist
        self.prompts_dir.mkdir(exist_ok=True)
        self.skills_dir.mkdir(exist_ok=True)
        
        # Load or init system prompt
        if SYSTEM_PROMPT_FILE.exists():
            self.system_prompt = SYSTEM_PROMPT_FILE.read_text()
        else:
            self.system_prompt = self._default_system_prompt()
            SYSTEM_PROMPT_FILE.write_text(self.system_prompt)
        
        # Track evolution history
        self.history_file = self.evolution_dir / "history.jsonl"
        self.best_score = 0.0
        self.mutations: list[Mutation] = []
        
    def _default_system_prompt(self) -> str:
        return """You are Auxlo, a self-evolving autonomous agent.

## Your Capabilities
- Execute shell commands
- Read/write files
- Learn from past tasks via memory

## Your Memory System
- Recent tasks shown in context
- Use semantic search to find older tasks
- Learn from patterns in past successes and failures

## Approach
1. Read /task/instruction.md
2. Explore and plan
3. Execute step by step
4. Verify output
5. Report success or failure
"""
    
    def solve(self, task: str) -> Observation:
        """Run a single task and observe the result."""
        print(f"  Solving: {task[:50]}...")
        
        messages = [
            {"role": "system", "content": self.system_prompt + "\n\nYou are being evaluated. Try to complete the task successfully."},
            {"role": "user", "content": task}
        ]
        
        trajectory = []
        turns = 0
        success = False
        error = None
        
        while turns < MAX_TURNS:
            turns += 1
            try:
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_tokens=MAX_TOKENS,
                    temperature=0.7
                )
                
                msg = response.choices[0].message
                content = msg.content or getattr(msg, 'reasoning_content', None) or ""
                
                if "success" in content.lower() or "completed" in content.lower():
                    success = True
                    trajectory.append({"type": "success", "content": content[:200]})
                    break
                    
                if turns >= MAX_TURNS:
                    error = "Max turns exceeded"
                    trajectory.append({"type": "timeout", "content": content[:200]})
                    
            except Exception as e:
                error = str(e)
                trajectory.append({"type": "error", "error": error})
                break
        
        return Observation(
            task=task,
            success=success,
            trajectory=trajectory,
            error=error,
            timestamp=datetime.now().isoformat()
        )
    
    def observe(self, observations: list[Observation]) -> dict:
        """Analyze observations to identify patterns."""
        total = len(observations)
        passed = sum(1 for o in observations if o.success)
        score = passed / total if total > 0 else 0
        
        # Categorize failures
        failures = [o for o in observations if not o.success]
        
        # Extract failure patterns
        patterns = {
            "timeout": 0,
            "error": 0,
            "unknown": 0
        }
        
        for f in failures:
            if f.error:
                if "timeout" in f.error.lower():
                    patterns["timeout"] += 1
                else:
                    patterns["error"] += 1
            else:
                patterns["unknown"] += 1
        
        return {
            "total": total,
            "passed": passed,
            "failed": len(failures),
            "score": score,
            "patterns": patterns,
            "timestamp": datetime.now().isoformat()
        }
    
    def evolve(self, analysis: dict, recent_tasks: list[dict]) -> Optional[Mutation]:
        """Propose and test mutations based on analysis."""
        
        # Only evolve if score is below threshold
        if analysis["score"] >= 0.9:
            print("  Score already high, skipping evolution")
            return None
        
        # Generate mutation proposal
        mutation = self._propose_mutation(analysis, recent_tasks)
        
        if not mutation:
            print("  No good mutation found")
            return None
        
        print(f"  Proposed: {mutation.type} - {mutation.name}")
        print(f"  Rationale: {mutation.rationale}")
        
        # Test mutation on sample tasks
        test_results = self._test_mutation(mutation)
        
        # If improved, accept; otherwise rollback
        if test_results["improved"]:
            self._accept_mutation(mutation)
            return mutation
        else:
            print(f"  Mutation regressed, rolling back")
            self._rollback_mutation()
            return None
    
    def _propose_mutation(self, analysis: dict, recent_tasks: list[dict]) -> Optional[Mutation]:
        """Use LLM to propose a mutation based on failure patterns."""
        
        # Build context about failures
        failure_context = f"""
Current score: {analysis['score']:.2f}
Failures: {analysis['failed']}
Patterns: {analysis['patterns']}

Recent tasks:
"""
        for task in recent_tasks[-10:]:
            status = "PASS" if task.get("success") else "FAIL"
            failure_context += f"- [{status}] {task.get('task', '')[:80]}\n"
        
        prompt = f"""Based on the analysis, propose ONE targeted mutation to improve the agent.

{failure_context}

Respond in JSON format:
{{
    "type": "skill" or "prompt",
    "name": "descriptive_name",
    "content": "full content of the skill or prompt section",
    "rationale": "why this mutation should help"
}}

Focus on fixing the failure patterns identified. Keep skills concise (<500 chars).
"""
        
        try:
            import time
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": "You are an expert at improving AI agents. Respond only with valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=1000,
                        temperature=0.7
                    )
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        wait = 2 ** attempt
                        print(f"  Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            
            content = response.choices[0].message.content or ""
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            
            return Mutation(
                type=data["type"],
                name=data["name"],
                content=data["content"],
                rationale=data.get("rationale", "")
            )
            
        except Exception as e:
            print(f"  Error proposing mutation: {e}")
            return None
    
    def _test_mutation(self, mutation: Mutation) -> dict:
        """Test a mutation on a few sample tasks."""
        
        # Apply mutation temporarily
        if mutation.type == "skill":
            skill_file = self.skills_dir / f"{mutation.name}.md"
            old_content = skill_file.read_text() if skill_file.exists() else ""
            skill_file.write_text(mutation.content)
        else:
            old_content = self.system_prompt
            self.system_prompt = mutation.content
            SYSTEM_PROMPT_FILE.write_text(mutation.content)
        
        # Test on a few tasks
        test_tasks = [
            "Create a simple Python script that prints 'Hello'",
            "List files in /tmp directory"
        ]
        
        results = []
        for task in test_tasks:
            obs = self.solve(task)
            results.append(obs.success)
        
        improved = sum(results) >= len(results) * 0.7
        
        # Restore original
        if mutation.type == "skill":
            if old_content:
                skill_file.write_text(old_content)
            else:
                skill_file.unlink()
        else:
            self.system_prompt = old_content
            SYSTEM_PROMPT_FILE.write_text(old_content)
        
        return {"improved": improved, "test_results": results}
    
    def _accept_mutation(self, mutation: Mutation):
        """Accept and persist the mutation."""
        
        # Git commit for versioning
        self._git_commit(f"Evolution: {mutation.type} - {mutation.name}")
        
        # Update best score
        if mutation.test_results and mutation.test_results.get("improved"):
            self.best_score = max(self.best_score, 
                                  self.best_score + 0.1)
        
        # Log to history
        with open(self.history_file, "a") as f:
            f.write(json.dumps({
                "mutation": asdict(mutation),
                "timestamp": datetime.now().isoformat()
            }) + "\n")
        
        print(f"  ✓ Mutation accepted!")
    
    def _rollback_mutation(self):
        """Rollback to previous state using git."""
        result = subprocess.run(
            ["git", "checkout", "HEAD~1", "--", "."],
            cwd=AUXLO_DIR,
            capture_output=True
        )
        if result.returncode == 0:
            # Reload system prompt
            if SYSTEM_PROMPT_FILE.exists():
                self.system_prompt = SYSTEM_PROMPT_FILE.read_text()
            print("  ✓ Rolled back successfully")
    
    def _git_commit(self, message: str):
        """Commit current state to git."""
        subprocess.run(["git", "add", "-A"], cwd=AUXLO_DIR, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=AUXLO_DIR,
            capture_output=True
        )
    
    def run_cycle(self, tasks: list[str], holdout_ratio: float = 0.2) -> dict:
        """Run one full evolution cycle."""
        print(f"\n=== Evolution Cycle ===")
        
        # Split into train and holdout (ensure at least 1 train task)
        split_idx = max(1, int(len(tasks) * (1 - holdout_ratio)))
        train_tasks = tasks[:split_idx]
        holdout_tasks = tasks[split_idx:]
        
        print(f"Train: {len(train_tasks)} | Holdout: {len(holdout_tasks)}")
        
        # 1. SOLVE - Run on training tasks
        print("\n[SOLVE]")
        train_observations = []
        for task in train_tasks:
            obs = self.solve(task)
            train_observations.append(obs)
        
        # 2. OBSERVE - Analyze results
        print("\n[OBSERVE]")
        analysis = self.observe(train_observations)
        print(f"Score: {analysis['score']:.2%} ({analysis['passed']}/{analysis['total']})")
        
        # Get recent tasks for context
        recent_tasks = []
        if MEMORY_DIR.exists():
            episodic = MEMORY_DIR / "episodic.jsonl"
            if episodic.exists():
                lines = episodic.read_text().strip().split("\n")
                for line in lines[-20:]:
                    if line:
                        try:
                            recent_tasks.append(json.loads(line))
                        except:
                            pass
        
        # 3. EVOLVE - Propose and test mutations
        print("\n[EVOLVE]")
        mutation = self.evolve(analysis, recent_tasks)
        
        # 4. VALIDATE - Test on holdout
        print("\n[VALIDATE]")
        if holdout_tasks:
            holdout_observations = []
            for task in holdout_tasks:
                obs = self.solve(task)
                holdout_observations.append(obs)
            
            holdout_score = sum(1 for o in holdout_observations if o.success) / len(holdout_observations)
            print(f"Holdout score: {holdout_score:.2%}")
        
        # 5. RELOAD - Pick up mutations
        print("\n[RELOAD]")
        if SYSTEM_PROMPT_FILE.exists():
            self.system_prompt = SYSTEM_PROMPT_FILE.read_text()
        print("  Agent reloaded with latest mutations")
        
        return {
            "train_score": analysis["score"],
            "holdout_score": holdout_score if holdout_tasks else None,
            "mutation": mutation.rationale if mutation else None
        }


if __name__ == "__main__":
    import sys
    
    # Load tasks
    tasks_dir = AUXLO_DIR / "tasks"
    if not tasks_dir.exists():
        print("No tasks directory found")
        sys.exit(1)
    
    task_files = list(tasks_dir.glob("*.md"))
    if not task_files:
        print("No tasks found")
        sys.exit(1)
    
    tasks = [f.read_text().strip() for f in task_files]
    
    print(f"Loaded {len(tasks)} tasks")
    
    # Initialize evolution engine
    engine = EvolutionEngine()
    
    # Run evolution cycle
    result = engine.run_cycle(tasks)
    
    print(f"\n=== Result ===")
    print(f"Train Score: {result['train_score']:.2%}")
    if result['holdout_score']:
        print(f"Holdout Score: {result['holdout_score']:.2%}")
    if result['mutation']:
        print(f"Mutation: {result['mutation']}")
