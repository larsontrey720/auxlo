#!/usr/bin/env python3
"""Auxlo Agent - Self-aware autonomous agent with memory and skills."""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI

# ============================================================================
# CONFIGURATION
# ============================================================================

def get_config():
    """Load config from .auxlo_config.json or env vars."""
    config_path = Path(__file__).parent / ".auxlo_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {
        "model": os.environ.get("AUXLO_MODEL", "stepfun-ai/step-3.5-flash"),
        "base_url": os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        "api_key": os.environ.get("NVIDIA_API_KEY", ""),
    }

# ============================================================================
# WORKSPACE MANAGEMENT
# ============================================================================

class Workspace:
    """Manages the agent's persistent workspace."""
    
    def __init__(self, root=None):
        self.root = root or Path(__file__).parent / "auxlo_agent"
        self.prompts_dir = self.root / "prompts"
        self.skills_dir = self.root / "skills"
        self.memory_dir = self.root / "memory"
        self.memory_file = self.memory_dir / "episodic.jsonl"
        
        # Create directories
        for d in [self.prompts_dir, self.skills_dir, self.memory_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    def read_memory(self, limit=50):
        """Read recent memory entries."""
        if not self.memory_file.exists():
            return []
        lines = self.memory_file.read_text().strip().split("\n")
        entries = [json.loads(l) for l in lines if l.strip()]
        return entries[-limit:]
    
    def write_memory(self, entry):
        """Write a memory entry."""
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.memory_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def read_skills(self):
        """Read all skills."""
        skills = []
        for skill_file in self.skills_dir.glob("*/SKILL.md"):
            name = skill_file.parent.name
            content = skill_file.read_text()
            skills.append({"name": name, "content": content})
        return skills
    
    def read_system_prompt(self):
        """Read the system prompt."""
        prompt_file = self.prompts_dir / "system.md"
        if prompt_file.exists():
            return prompt_file.read_text()
        return None
    
    def write_system_prompt(self, content):
        """Write the system prompt."""
        prompt_file = self.prompts_dir / "system.md"
        prompt_file.write_text(content)

# ============================================================================
# SELF-AWARE AGENT
# ============================================================================

class SelfAwareAgent:
    """Agent with full awareness of its history and capabilities."""
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.workspace = Workspace()
        self.client = OpenAI(
            api_key=self.config["api_key"],
            base_url=self.config["base_url"]
        )
    
    def build_system_prompt(self):
        """Build a system prompt with full self-awareness."""
        parts = []
        
        # Base instructions
        parts.append("""You are a highly capable task-completion agent. You solve tasks by reading instructions, executing code, and producing output files.

## Your Tools
You have access to shell commands via the run_bash_command tool.

## Approach
1. Read /task/instruction.md to understand what's required.
2. Execute commands to complete the task.
3. Write output files to the exact paths specified.
4. Verify your output before finishing.
5. End with "Task completed successfully." when done.
""")
        
        # Add previous task memory
        memory = self.workspace.read_memory()
        if memory:
            parts.append("\n## Previous Task History")
            parts.append("Recent task outcomes that inform your approach:")
            for entry in memory[-10:]:
                status = "✓" if entry.get("success") else "✗"
                task = entry.get("task", "unknown")[:60]
                error = entry.get("error", "")[:100]
                parts.append(f"- {status} {task} | {error}")
        
        # Add evolved skills
        skills = self.workspace.read_skills()
        if skills:
            parts.append(f"\n## Evolved Skills ({len(skills)} available)")
            for skill in skills[:10]:
                # Extract description from frontmatter
                content = skill["content"]
                desc_match = content.split("---")[1] if "---" in content else ""
                desc = ""
                if "description:" in desc_match:
                    desc = desc_match.split("description:")[1].split("\n")[0].strip()
                parts.append(f"- **{skill['name']}**: {desc or 'Custom skill'}")
        
        return "\n".join(parts)
    
    def solve(self, task_instruction):
        """Solve a single task with full awareness."""
        # Store task start
        task_entry = {
            "task": task_instruction[:100],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": ""
        }
        
        try:
            # Build aware system prompt
            system_prompt = self.build_system_prompt()
            
            # Read instruction
            if os.path.exists("/task/instruction.md"):
                with open("/task/instruction.md") as f:
                    task_instruction = f.read().strip()
            
            # Run agent loop
            result = self.run_loop(system_prompt, task_instruction)
            
            # Record success
            task_entry["success"] = True
            task_entry["result"] = result[:500]
            
        except Exception as e:
            task_entry["success"] = False
            task_entry["error"] = str(e)[:200]
        
        # Write to memory
        self.workspace.write_memory(task_entry)
        
        return task_entry
    
    def run_loop(self, system_prompt, task_instruction):
        """Run the agent loop with tool calling."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_instruction}
        ]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "run_bash_command",
                "description": "Execute a shell command and return stdout/stderr",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute"}
                    },
                    "required": ["command"]
                }
            }
        }]
        
        for turn in range(30):
            response = self.client.chat.completions.create(
                model=self.config["model"],
                messages=messages,
                tools=tools,
                max_tokens=2048,
                temperature=0.7
            )
            
            msg = response.choices[0].message
            content = msg.content or getattr(msg, 'reasoning_content', None) or ""
            
            # Handle tool calls
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    
                    # Execute
                    result = subprocess.run(
                        args["command"], shell=True, capture_output=True, text=True, timeout=120
                    )
                    output = result.stdout + (f"\nSTDERR: {result.stderr}" if result.stderr else "")
                    
                    # Truncate if long
                    if len(output) > 2000:
                        output = output[:2000] + f"\n... [truncated]"
                    
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tool_name, "arguments": tc.function.arguments}}]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": output
                    })
            else:
                return content
        
        return "Max turns exceeded"

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    agent = SelfAwareAgent()
    result = agent.solve("")
    print(json.dumps(result, indent=2))
