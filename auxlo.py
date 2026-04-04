"""Auxlo - Autonomous Agent Harness with Self-Evolution

Uses environment variables for API credentials:
- NVIDIA_API_KEY (required)
- NVIDIA_BASE_URL (defaults to NVIDIA endpoint)
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from openai import OpenAI

# ============================================================================
# CONFIGURATION (from environment)
# ============================================================================

MODEL = os.environ.get("AUXLO_MODEL", "stepfun-ai/step-3.5-flash")
BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("NVIDIA_API_KEY", "")

if not API_KEY:
    raise ValueError("NVIDIA_API_KEY environment variable is required")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# Evolution config
MAX_TURNS = 30
MAX_TOKENS = 2048
MAX_TOOL_OUTPUT = 2000
MEMORY_CAP = 20
WORKSPACE_ROOT = Path(os.environ.get("AUXLO_WORKSPACE", "/home/workspace/auxlo/auxlo_agent"))

# ============================================================================
# WORKSPACE
# ============================================================================

class Workspace:
    """Filesystem-based workspace for evolvable agent state."""
    
    def __init__(self, root: Path = WORKSPACE_ROOT):
        self.root = root
        self.prompts_dir = root / "prompts"
        self.skills_dir = root / "skills"
        self.memory_dir = root / "memory"
        
    def init(self):
        """Initialize workspace structure."""
        for d in [self.prompts_dir, self.skills_dir, self.memory_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        prompt_file = self.prompts_dir / "system.md"
        if not prompt_file.exists():
            prompt_file.write_text(DEFAULT_SYSTEM_PROMPT)
        
        memory_file = self.memory_dir / "episodic.jsonl"
        if not memory_file.exists():
            memory_file.write_text("")
        
        # Init git
        if not (self.root / ".git").exists():
            subprocess.run(["git", "init"], cwd=self.root, capture_output=True)
    
    def read_prompt(self) -> str:
        path = self.prompts_dir / "system.md"
        return path.read_text() if path.exists() else ""
    
    def write_prompt(self, content: str):
        (self.prompts_dir / "system.md").write_text(content)
    
    def list_skills(self) -> list:
        skills = []
        for d in self.skills_dir.glob("*"):
            if d.is_dir():
                f = d / "SKILL.md"
                if f.exists():
                    skills.append({"name": d.name, "content": f.read_text()})
        return skills
    
    def read_skill(self, name: str) -> str:
        path = self.skills_dir / name / "SKILL.md"
        return path.read_text() if path.exists() else ""
    
    def write_skill(self, name: str, content: str):
        d = self.skills_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(content)
    
    def delete_skill(self, name: str):
        import shutil
        d = self.skills_dir / name
        if d.exists():
            shutil.rmtree(d)
    
    def add_memory(self, entry: dict):
        f = self.memory_dir / "episodic.jsonl"
        f.open("a").write(json.dumps(entry) + "\n")
        # Prune if over cap
        lines = f.read_text().strip().split("\n")
        if len(lines) > MEMORY_CAP:
            f.write_text("\n".join(lines[-MEMORY_CAP:]) + "\n")
    
    def get_memory(self) -> list:
        f = self.memory_dir / "episodic.jsonl"
        if not f.exists():
            return []
        return [json.loads(l) for l in f.read_text().strip().split("\n") if l]
    
    def commit(self, msg: str, tag: str = None):
        subprocess.run(["git", "add", "."], cwd=self.root, capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=self.root, capture_output=True)
        if tag:
            subprocess.run(["git", "tag", "-a", tag, "-m", tag], cwd=self.root, capture_output=True)

# ============================================================================
# PROMPT & SKILLS
# ============================================================================

DEFAULT_SYSTEM_PROMPT = """You are a highly capable task-completion agent. You solve tasks by reading instructions, executing code, and producing output files.

## Your Tools
You have access to shell commands via the run_bash_command tool.

## Approach
1. Read /task/instruction.md to understand what's required.
2. Execute commands to complete the task.
3. Write output files to the exact paths specified.
4. Verify your output before finishing.
5. End with "Task completed successfully." when done.

## Key rules
- Use python3 for running scripts
- Use shell commands for file operations
- Keep outputs concise - summarize long results
- Use timeout flag for long-running commands
"""

SKILL_TEMPLATES = {
    "timeout-handler": """---
name: timeout-handler
description: Handle command timeouts gracefully
---

# Timeout Handler

When commands timeout:
1. Try simpler/faster equivalent
2. Use timeout flag (timeout 10 command)
3. Check target exists before running
4. Report partial results if available
""",
    "permission-handler": """---
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
    "file-checker": """---
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

# ============================================================================
# TOOLS
# ============================================================================

tools = [
    {
        "type": "function",
        "function": {
            "name": "run_bash_command",
            "description": "Execute a shell command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 120}
                },
                "required": ["command"]
            }
        }
    }
]

def run_bash_command(command: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        out = result.stdout
        if result.stderr:
            out += f"\nSTDERR:\n{result.stderr}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"

def truncate_output(output: str, max_len: int = MAX_TOOL_OUTPUT) -> str:
    if len(output) > max_len:
        return output[:max_len] + f"\n... [truncated {len(output) - max_len} chars]"
    return output

def execute_tool(name: str, args: dict) -> str:
    if name == "run_bash_command":
        result = run_bash_command(args.get("command", ""), args.get("timeout", 120))
        return truncate_output(result)
    return f"Unknown tool: {name}"

# ============================================================================
# AGENT LOOP
# ============================================================================

def chat(messages: list, tools: list = None) -> dict:
    try:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools,
            max_tokens=MAX_TOKENS, temperature=0.7
        )
        return response
    except Exception as e:
        return {"error": str(e)}

def build_prompt(workspace: Workspace) -> str:
    """Build system prompt with skills and memory."""
    prompt = workspace.read_prompt() or DEFAULT_SYSTEM_PROMPT
    
    skills = workspace.list_skills()
    if skills:
        prompt += "\n\n## Available Skills\n"
        for s in skills[:10]:
            # Extract description from frontmatter
            content = s["content"]
            desc = content.split("description:")[1].split("---")[0].strip() if "description:" in content else s["name"]
            prompt += f"- {s['name']}: {desc}\n"
    
    memory = workspace.get_memory()
    if memory:
        prompt += "\n\n## Recent Memory\n"
        for entry in memory[-3:]:
            prompt += f"- {entry.get('summary', '')}\n"
    
    return prompt

def run_agent(instruction: str, workspace: Workspace = None) -> tuple:
    """Run agent loop and return (result, trajectory)."""
    if workspace is None:
        workspace = Workspace()
    
    system_prompt = build_prompt(workspace)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction}
    ]
    
    trajectory = []
    turns = 0
    
    while turns < MAX_TURNS:
        turns += 1
        response = chat(messages, tools=tools)
        
        if "error" in response:
            return f"API Error: {response['error']}", trajectory
        
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or getattr(msg, "reasoning_content", None) or ""
        
        step = {"turn": turns, "content": content[:500] if content else "(tool call)"}
        
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                step["tool"] = tool_name
                step["args"] = args
                
                result = execute_tool(tool_name, args)
                step["result"] = result[:500]
                
                messages.append({"role": "assistant", "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tool_name, "arguments": tc.function.arguments}}]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            
            trajectory.append(step)
        else:
            if content:
                return content, trajectory
    
    return "Max turns exceeded", trajectory

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Init workspace
    workspace = Workspace()
    workspace.init()
    
    # Read instruction
    instruction = "Say hello"
    if Path("/task/instruction.md").exists():
        instruction = Path("/task/instruction.md").read_text().strip()
    
    # Run agent
    result, trajectory = run_agent(instruction, workspace)
    print(result)
    
    # Log to memory
    success = "success" in result.lower() or "done" in result.lower()
    workspace.add_memory({
        "task": instruction[:200],
        "result": result[:500],
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Save trajectory
    Path("/logs").mkdir(exist_ok=True)
    Path("/logs/trajectory.json").write_text(json.dumps({
        "schema_version": "ATIF-v1.0",
        "agent": {"name": "auxlo", "version": "0.1.0"},
        "steps": trajectory,
        "total_turns": len(trajectory)
    }, indent=2))