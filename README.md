# Auxlo

> Like autoresearch but for agent engineering. Give an AI agent a task, let it build and iterate on an agent harness autonomously overnight. It modifies the system prompt, tools, agent configuration, and orchestration, runs the benchmark, checks the score, keeps or discards the change, and repeats.

Auxlo is an autonomous agent engineering framework built by [Auxlo](https://auxlo.xyz).

## How it works

The repo has a few files and directories that matter:

- **`auxlo.py`** -- the entire harness under test in a single file. It contains
  config, tool definitions, agent registry, routing/orchestration, and the
  Harbor adapter boundary. The adapter section is explicitly marked as fixed;
  the rest is the primary edit surface for the meta-agent.
- **`program.md`** -- instructions for the meta-agent + the directive (what
  kind of agent to build). **This file is edited by the human**.
- **`tasks/`** -- evaluation tasks in
  [harbor](https://github.com/laude-institute/harbor) format. In a clean
  baseline branch, benchmark payloads may be omitted and added in
  benchmark-specific branches.
- **`.agent/`** -- optional workspace artifacts for reusable instructions,
  notes, prompts, or skills.

The metric is total **score** produced by the benchmark's task test suites. The
meta-agent hill-climbs on this score.

## Quick start

**Requirements:** Docker, Python 3.12+

```bash
# Install dependencies
cd auxlo
uv sync

# Build the base image
docker build -f Dockerfile.base -t auxlo-base .

# Run a single task
rm -rf jobs; mkdir -p jobs && uv run harbor run -p tasks/ --task-name "<task-name>" -l 1 -n 1 --agent-import-path auxlo:Auxlo -o jobs --job-name latest > run.log 2>&1

# Run all tasks in parallel (-n = concurrency, default 4)
rm -rf jobs; mkdir -p jobs && uv run harbor run -p tasks/ -n 100 --agent-import-path auxlo:Auxlo -o jobs --job-name latest > run.log 2>&1
```

## Running the meta-agent

Point your coding agent at the repo and prompt:

```
Read program.md and let's kick off a new experiment!
```

The meta-agent will read the directive, inspect the current harness, run the
benchmark, diagnose failures, modify `auxlo.py`, and iterate.

## Project structure

```
auxlo.py                       -- single-file harness under test
  editable harness section     -- prompt, registries, tools, routing
  fixed adapter section      -- Harbor integration + trajectory serialization
program.md                     -- meta-agent instructions + directive
pyproject.toml                 -- Python dependencies
Dockerfile.base                -- container image for task execution
docs/                          -- harness design patterns, SDK docs
.agent/                       -- reusable context for the meta-agent
tasks/                        -- benchmark tasks in Harbor format
scripts/                      -- utility scripts
```

## Task format

```
tasks/my-task/
  task.toml           -- config (timeouts, metadata)
  instruction.md      -- prompt sent to the agent
  tests/
    test.sh           -- entry point, writes /logs/reward.txt
    test.py           -- verification (deterministic or LLM-as-judge)
  environment/
    Dockerfile        -- task container (FROM auxlo-base)
  files/              -- reference files mounted into container
```

Tests write a score (0.0-1.0) to the verifier logs. The meta-agent hill-climbs
on this.

## Design choices

- **Program the meta-agent, not the harness directly.** The human steers the
  loop through `program.md`, while the meta-agent edits `auxlo.py`.
- **Single-file, registry-driven harness.** The implementation lives in one
  file for simplicity, but agent and tool registration stay structured so the
  harness can still evolve cleanly.
- **Docker isolation.** The agent runs in a container. It cannot damage the host.
- **Score-driven.** Every experiment produces a numeric score. Keep if better,
  discard if not. Same loop as autoresearch.
- **Harbor-compatible tasks.** Tasks use the same format as harbor benchmarks,
  so the same harness can be evaluated on different datasets.

## Cleanup

Docker images and containers accumulate across runs. Clean up regularly:

```bash
# Harbor cached task images + task cache
uv run harbor cache clean -f

# Full Docker nuke (all unused images, build cache, etc.)
docker system prune -a -f

# Lighter: just dead containers
docker container prune -f
```

## Improving performance with skills

You can equip the agent with Agent Skills for Context Engineering and context7
skills to improve performance. Add skills to the `.agent/` directory.
