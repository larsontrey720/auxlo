# Auxlo

> Self-evolving autonomous agent that improves itself. Add tasks, let it run, watch it get smarter.

Auxlo is an autonomous agent engineering framework built by [Auxlo](https://auxlo.xyz).

## Quick Start

```bash
# Clone
git clone https://github.com/larsontrey720/auxlo.git
cd auxlo

# Configure (optional - uses env vars by default)
auxlo config --api-key your-api-key
auxlo config --model stepfun-ai/step-3.5-flash

# Add tasks and run
auxlo add "Write a Python script that prints hello"
auxlo run

# Check results
auxlo status
auxlo logs
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `auxlo add "task description"` | Add a new task to the benchmark |
| `auxlo run` | Run the evolution loop on all tasks |
| `auxlo status` | Show current config, tasks, and last run |
| `auxlo config` | Show current configuration |
| `auxlo config --model <model>` | Change the model |
| `auxlo config --base-url <url>` | Change the API base URL |
| `auxlo config --api-key <key>` | Set the API key |
| `auxlo config --list-models` | Show available preset models |
| `auxlo logs` | Show recent evolution logs |

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     EVOLUTION LOOP                            │
│                                                              │
│   ┌─────────┐    ┌───────────┐    ┌──────────┐              │
│   │  Solve  │───▶│  Observe  │───▶│  Evolve  │              │
│   │ (agent) │    │ (collect) │    │ (mutate) │              │
│   └────▲─────┘    └───────────┘    └────┬─────┘              │
│        │                                │                    │
│   reads from                      writes to                  │
│        │                                │                    │
│   ┌────┴────────────────────────────────▼─────┐              │
│   │              WORKSPACE (FS)               │              │
│   │  prompts/  skills/  memory/  evolution/   │              │
│   └──────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

1. **Solve** -- Agent processes tasks using available tools
2. **Observe** -- Collect trajectories and results into memory
3. **Evolve** -- Analyze failures, auto-seed skills, mutate workspace

## Project Structure

```
auxlo/
├── __main__.py          # CLI entry point (auxlo command)
├── .auxlo_config.json   # Saved configuration
├── .env                 # Environment variables
├── auxlo_agent/         # Agent workspace (auto-created)
│   ├── prompts/         # System prompts
│   ├── skills/          # Evolved skills (SKILL.md files)
│   └── memory/           # Episodic memory (JSONL)
├── tasks/               # Benchmark tasks
│   └── *.md             # Task descriptions
├── scripts/
│   └── evolve.sh        # Evolution loop script
└── results.tsv          # Run history
```

## Configuration

### Environment Variables (Recommended)

```bash
export NVIDIA_API_KEY="your-nvidia-api-key"
export NVIDIA_BASE_URL="https://integrate.api.nvidia.com/v1"
export AUXLO_MODEL="stepfun-ai/step-3.5-flash"
```

### Or use the CLI

```bash
# Set API key
auxlo config --api-key your-api-key

# Change model
auxlo config --model anthropic/claude-3-5-sonnet-20241022

# Use a different base URL
auxlo config --base-url https://api.anthropic.com/v1
```

### Available Preset Models

- **NVIDIA:** `stepfun-ai/step-3.5-flash` (default)
- **Anthropic:** `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`
- **OpenAI:** `gpt-4o`, `gpt-4o-mini`
- **Google:** `gemini-2.0-flash`, `gemini-1.5-pro`

## Task Format

Tasks are simple markdown files in the `tasks/` directory:

```markdown
# Task

Write a Python script at /tmp/hello.py that prints "Hello from Auxlo!"
```

## Evolved Skills

Auxlo auto-generates skills based on failure patterns. Skills are stored in `auxlo_agent/skills/` as `SKILL.md` files:

```markdown
---
name: error-handler
description: TRIGGER when a command fails with timeout or permission error
---

# Error Handler Skill

When a command times out or fails:
1. Check if the command can be optimized
2. Add appropriate timeout values
3. Verify permissions
4. Retry with fallbacks
```

## Git Versioning

Every evolution cycle is automatically committed:

```bash
git log --oneline
# evo-3: Auto-seeded timeout-handler skill
# evo-2: Improved file operation skills
# evo-1: Initial workspace setup
```

Rollback if needed:

```bash
git reset --hard evo-2  # Go back to previous version
```

## Persistence

Auxlo stores state in:
- `auxlo_agent/memory/episodic.jsonl` -- Task history
- `auxlo_agent/skills/` -- Evolved skills
- `auxlo_agent/prompts/` -- Current prompts
- `results.tsv` -- Run scores

## Requirements

- Python 3.12+
- `uv` package manager
- API key for your LLM provider

## License

MIT