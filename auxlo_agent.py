#!/usr/bin/env python3
"""Auxlo Agent - Self-aware autonomous agent with hybrid memory."""

import json
import os
import subprocess
import re
import hashlib
from datetime import datetime
from pathlib import Path
from openai import OpenAI

# ============================================================================
# CONFIG
# ============================================================================

MODEL = os.environ.get("AUXLO_MODEL", "stepfun-ai/step-3.5-flash")
BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
API_KEY = os.environ.get("NVIDIA_API_KEY", "")
SYSTEM_PROMPT = os.environ.get("AUXLO_SYSTEM_PROMPT", "")

AGENT_DIR = Path(__file__).parent
MEMORY_DIR = AGENT_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)
EPISODIC_FILE = MEMORY_DIR / "episodic.jsonl"
SUMMARIES_FILE = MEMORY_DIR / "summaries.txt"
INDEX_FILE = MEMORY_DIR / "index.jsonl"

MAX_RECENT_TASKS = 20
MAX_SUMMARY_LINES = 100
MAX_RETRIEVAL_RESULTS = 5

# ============================================================================
# OPENAI CLIENT
# ============================================================================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL) if API_KEY else None

# ============================================================================
# HYBRID MEMORY SYSTEM
# ============================================================================

def load_recent_tasks(n: int = MAX_RECENT_TASKS) -> list[dict]:
    """Tier 1: Load last n tasks with full detail."""
    if not EPISODIC_FILE.exists():
        return []
    
    tasks = []
    lines = EPISODIC_FILE.read_text().strip().split("\n")
    for line in reversed(lines):
        if line.strip():
            try:
                tasks.append(json.loads(line))
            except:
                pass
        if len(tasks) >= n:
            break
    return list(reversed(tasks))

def compress_task_to_summary(task: dict) -> str:
    """Compress a task into a single line summary."""
    task_text = task.get("task", "")[:100]
    success = "SUCCESS" if task.get("success") else "FAIL"
    result_preview = task.get("result", "")[:50].replace("\n", " ")
    
    # Extract key lessons
    lessons = []
    if not task.get("success"):
        if "permission" in result_preview.lower() or "denied" in result_preview.lower():
            lessons.append("Permission errors")
        if "timeout" in result_preview.lower():
            lessons.append("Timeout issues")
        if "not found" in result_preview.lower():
            lessons.append("Path not found")
    
    lesson_str = f" | {', '.join(lessons)}" if lessons else ""
    
    return f"{task.get('timestamp', '')[:10]} | {success} | {task_text}...{lesson_str}"

def load_summaries() -> list[str]:
    """Tier 2: Load compressed summaries of older tasks."""
    if not SUMMARIES_FILE.exists():
        return []
    
    lines = SUMMARIES_FILE.read_text().strip().split("\n")
    return [l for l in lines if l.strip()]

def save_summaries(summaries: list[str]):
    """Save summaries, capped at max lines."""
    if len(summaries) > MAX_SUMMARY_LINES:
        summaries = summaries[-MAX_SUMMARY_LINES:]
    SUMMARIES_FILE.write_text("\n".join(summaries) + "\n")

def add_to_summaries(task: dict):
    """Add a new task to the summaries file."""
    summary = compress_task_to_summary(task)
    summaries = load_summaries()
    summaries.append(summary)
    save_summaries(summaries)

def extract_indexable_content(task: dict) -> str:
    """Extract key content for semantic search."""
    parts = [
        task.get("task", ""),
        task.get("result", ""),
        "SUCCESS" if task.get("success") else "FAIL"
    ]
    return " | ".join(parts)

def load_index() -> list[dict]:
    """Tier 3: Load semantic search index."""
    if not INDEX_FILE.exists():
        return []
    
    index = []
    lines = INDEX_FILE.read_text().strip().split("\n")
    for line in lines:
        if line.strip():
            try:
                index.append(json.loads(line))
            except:
                pass
    return index

def save_index(index: list[dict]):
    """Save semantic search index."""
    INDEX_FILE.write_text("\n".join(json.dumps(i) for i in index) + "\n")

def generate_embedding(text: str) -> list[float]:
    """Generate embedding for text using the model."""
    if not client:
        # Fallback: simple hash-based "embedding"
        return [float(int(hashlib.md5(text.encode()).hexdigest()[:8], 16)) / 0xFFFFFFFF]
    
    try:
        response = client.embeddings.create(
            model="nvidia/nv-embed-qa-4",
            input=text
        )
        return response.data[0].embedding
    except:
        # Fallback for non-NVIDIA providers
        return [float(int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)) / 0xFFFFFFFF]

def cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def semantic_search(query: str, index: list[dict], top_k: int = MAX_RETRIEVAL_RESULTS) -> list[dict]:
    """Search index for relevant entries."""
    if not index:
        return []
    
    query_embedding = generate_embedding(query)
    
    results = []
    for item in index:
        content_emb = item.get("embedding", [])
        if content_emb:
            sim = cosine_sim(query_embedding, content_emb)
            results.append((sim, item))
    
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in results[:top_k]]

def add_to_index(task: dict):
    """Add a task to the semantic index."""
    index = load_index()
    
    content = extract_indexable_content(task)
    embedding = generate_embedding(content)
    
    # Create title from task
    task_text = task.get("task", "")[:50]
    title = re.sub(r"[^a-z0-9 ]", "", task_text.lower()).replace(" ", "_")[:30]
    
    entry = {
        "timestamp": task.get("timestamp", ""),
        "title": title,
        "content": content,
        "embedding": embedding,
        "success": task.get("success", False)
    }
    
    index.append(entry)
    
    # Cap index at 500 entries
    if len(index) > 500:
        index = index[-500:]
    
    save_index(index)

def sync_memory():
    """Sync episodic memory to summaries and index."""
    if not EPISODIC_FILE.exists():
        return
    
    all_tasks = []
    lines = EPISODIC_FILE.read_text().strip().split("\n")
    for line in lines:
        if line.strip():
            try:
                all_tasks.append(json.loads(line))
            except:
                pass
    
    # Update summaries (keep all compressed)
    existing_summaries = {s[:20] for s in load_summaries()}  # dedup by date
    
    # Only add tasks older than last 20
    old_tasks = all_tasks[:-MAX_RECENT_TASKS] if len(all_tasks) > MAX_RECENT_TASKS else []
    
    for task in old_tasks:
        summary = compress_task_to_summary(task)
        if summary[:20] not in existing_summaries:
            existing_summaries.add(summary[:20])
            summaries = load_summaries()
            summaries.append(summary)
            save_summaries(summaries)
            add_to_index(task)

# ============================================================================
# CONTEXT BUILDER
# ============================================================================

def build_context(query: str = "", max_tokens: int = 500) -> str:
    """Build context from hybrid memory for the agent.
    
    Includes:
    - Recent tasks (full detail, last 20)
    - Older task summaries (single lines)  
    - Semantic search matches (shows FULL detail if query matches index)
    
    This keeps context bounded while ensuring older memories can be retrieved.
    """
    lines = []
    lines.append("=== RECENT TASKS (Full Detail) ===")
    
    memories_dir = Path(MEMORY_DIR)
    episodic_file = memories_dir / "episodic.jsonl"
    summaries_file = memories_dir / "summaries.txt"
    index_file = memories_dir / "index.jsonl"
    
    # Tier 1: Recent 20 tasks (full detail)
    recent_count = 0
    if episodic_file.exists():
        with open(episodic_file) as f:
            lines_ = f.readlines()
            for line in lines_[-20:]:
                if line.strip():
                    entry = json.loads(line)
                    task = entry.get("task", "")[:100]
                    result = entry.get("result", "")[:80]
                    success = "PASS" if entry.get("success") else "FAIL"
                    lines.append(f"[{success}] {task}")
                    lines.append(f"  Result: {result}")
                    recent_count += 1
    
    lines.append(f"\n(Showing {recent_count} most recent tasks)\n")
    
    # Tier 2: Older task summaries (only if query is empty - avoid spam)
    if not query and summaries_file.exists():
        with open(summaries_file) as f:
            summary_lines = f.readlines()
            # Show last 50 summaries only
            for line in summary_lines[-50:]:
                if line.strip() and not any(line.startswith(x) for x in lines[-20:]):
                    lines.append(line.strip())
    
    # Tier 3: Semantic search - SHOW FULL DETAIL for matching entries
    if query and index_file.exists():
        query_lower = query.lower()
        with open(index_file) as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        content = entry.get("content", "").lower()
                        title = entry.get("title", "").lower()
                        
                        # Enhanced matching: substring + word overlap
                        query_words = set(query_lower.split())
                        content_words = set(content.split()) | set(title.split())
                        
                        # Check various matches
                        match = False
                        
                        # 1. Substring in content or title
                        if query_lower in content or query_lower in title:
                            match = True
                        
                        # 2. Each query word matches
                        for word in query_words:
                            if len(word) >= 3 and (word in content or word in title):
                                match = True
                                break
                        
                        # 3. Numeric query (e.g., "task_7" -> match "7")
                        for word in query_words:
                            if word.isdigit() and word in content:
                                match = True
                                break
                            # Handle task_X format
                            if '_' in word:
                                parts = word.split('_')
                                for p in parts:
                                    if p.isdigit() and p in content:
                                        match = True
                                        break
                        
                        if match:
                            # Found! Show full detail
                            lines.append(f"\n=== MEMORY MATCH ===")
                            lines.append(f"Title: {entry.get('title', '')}")
                            lines.append(f"Timestamp: {entry.get('timestamp', '')}")
                            lines.append(f"Success: {entry.get('success', False)}")
                            lines.append(f"Content: {entry.get('content', '')}")
                            
                    except json.JSONDecodeError:
                        continue
    
    return "\n".join(lines)

# ============================================================================
# TASK MEMORY
# ============================================================================

def log_task(task: str, result: str, success: bool, error: str = ""):
    """Log a completed task to episodic memory."""
    entry = {
        "task": task,
        "result": result,
        "success": success,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(EPISODIC_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    # Sync to summaries and index
    add_to_summaries(entry)
    add_to_index(entry)

# ============================================================================
# AGENT
# ============================================================================

def chat(messages: list, tools: list = None, max_tokens: int = 2048) -> dict:
    """Call the API."""
    if not client:
        return {"error": "No API client configured"}
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=0.7
        )
        return response
    except Exception as e:
        return {"error": str(e)}

def run_agent_loop(task: str) -> dict:
    """Run the agent on a task with full memory awareness."""
    # Build memory context
    memory_context = build_context(task)
    
    # Full system prompt with memory
    system = f"""You are a highly capable task-completion agent.

{memory_context}

## Approach
1. Review your task history above
2. Learn from past successes and failures
3. Execute the task efficiently
4. Report results clearly

## Output Format
End with:
- SUCCESS: [what you did] or
- FAIL: [why it failed]"""

    if SYSTEM_PROMPT:
        system = SYSTEM_PROMPT + "\n\n" + memory_context

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task}
    ]
    
    tools = [{
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
    }]
    
    trajectory = []
    turns = 0
    max_turns = 30
    
    while turns < max_turns:
        turns += 1
        response = chat(messages, tools=tools)
        
        if "error" in response:
            return {"success": False, "error": response["error"], "result": ""}
        
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or getattr(msg, "reasoning_content", None) or ""
        
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments)
                
                # Execute tool
                try:
                    result = subprocess.run(
                        args["command"],
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=args.get("timeout", 120)
                    )
                    tool_result = result.stdout + result.stderr if result.stderr else result.stdout
                    if len(tool_result) > 2000:
                        tool_result = tool_result[:2000] + f"\n... [{len(tool_result)-2000} chars truncated]"
                except subprocess.TimeoutExpired:
                    tool_result = "ERROR: Command timed out"
                except Exception as e:
                    tool_result = f"ERROR: {e}"
                
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tool_name, "arguments": tc.function.arguments}}]
                })
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
                trajectory.append({"tool": tool_name, "args": args, "result": tool_result})
        else:
            trajectory.append({"response": content})
            # Determine success
            success = "SUCCESS" in content or "Task completed" in content
            log_task(task, content, success)
            return {"success": success, "result": content, "trajectory": trajectory}
    
    log_task(task, "Max turns exceeded", False)
    return {"success": False, "error": "Max turns exceeded", "result": "", "trajectory": trajectory}

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    
    task = ""
    if len(sys.argv) > 1:
        task = sys.argv[1]
    elif Path("/task/instruction.md").exists():
        task = Path("/task/instruction.md").read_text().strip()
    
    if not task:
        print(json.dumps({"error": "No task provided"}))
        sys.exit(1)
    
    started = datetime.now().isoformat()
    result = run_agent_loop(task)
    
    output = {
        "task": task,
        "started_at": started,
        "success": result.get("success", False),
        "error": result.get("error", ""),
        "result": result.get("result", ""),
        "timestamp": datetime.now().isoformat()
    }
    
    print(json.dumps(output, indent=2))
