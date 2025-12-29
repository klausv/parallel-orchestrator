# Parallel Orchestrator

Cross-project infrastructure for running parallel AI agent tasks with Claude Code.

An intelligent task orchestration agent that enables parallel execution of complex multi-step operations with hypothesis testing and root cause analysis.

## Features

- **Git Worktrees**: Run multiple Claude Code sessions in parallel on the same repo
- **Docker Sandbox**: Containerized execution for isolation
- **GitHub Actions**: Cloud-based parallel task execution
- **Mobile Control**: Trigger workflows via Android (GitHub Mobile + Tasker)
- **Task Splitting**: AI-powered conflict-free task decomposition
- **Parallel Task Execution**: Intelligently identifies and executes independent operations concurrently
- **Agent Matching**: Routes tasks to specialized agents based on complexity and requirements
- **Hypothesis Testing**: Systematic approach to debugging with parallel hypothesis validation

## Quick Start

### Local Parallel Development

```bash
# Install worktree CLI (run in WSL)
npm install -g @johnlindquist/worktree

# From any project directory
cd ~/your-project

# Create parallel worktrees
wt new feature-a
wt new feature-b

# Run Claude Code in each (separate terminals)
cd ../your-project-feature-a && claude
cd ../your-project-feature-b && claude
```

### Using the Scripts

```bash
# Add to PATH (add to ~/.bashrc)
export PATH="$PATH:$HOME/klauspython/parallel-orchestrator/scripts"

# Create worktrees for parallel tasks
setup-worktree.sh feature-a feature-b feature-c

# Run Claude Code in parallel (uses tmux)
run-parallel.sh --tasks "feature-a,feature-b"

# Split a complex task into parallel subtasks
python3 task-splitter.py "Implement user authentication with tests"
```

### Cloud Execution (GitHub Actions)

1. Copy `workflows/parallel-tasks.yml` to your project's `.github/workflows/`
2. Add `ANTHROPIC_API_KEY` to repository secrets
3. Trigger via GitHub Mobile or Tasker

Diagram: see `docs/parallel-tasks-diagram.md`.

## Directory Structure

```text
parallel-orchestrator/
├── scripts/
│   ├── setup-worktree.sh    # Create worktrees for parallel tasks
│   ├── run-parallel.sh      # Launch parallel Claude sessions
│   ├── task-splitter.py     # AI-powered task decomposition
│   └── merge-results.sh     # Aggregate branch results
├── workflows/
│   └── parallel-tasks.yml   # GitHub Actions template
├── android/
│   └── tasker-config.md     # Tasker setup instructions
├── templates/
│   ├── .claude-project.json # Template project config
│   └── worktree-config.yaml # Default worktree settings
└── docs/
    └── usage.md             # Detailed usage guide
```

## Requirements

- WSL (Ubuntu)
- Node.js (for worktree CLI)
- Docker (optional, for sandbox mode)
- GitHub CLI (`gh`)
- tmux (for parallel session management)

## Installation

```bash
# Clone or create the orchestrator project
cd ~/klauspython/parallel-orchestrator

# Install dependencies
npm install -g @johnlindquist/worktree
sudo apt install tmux gh

# Add scripts to PATH
echo 'export PATH="$PATH:$HOME/klauspython/parallel-orchestrator/scripts"' >> ~/.bashrc
source ~/.bashrc
```

## Mobile Control (Android)

See `android/tasker-config.md` for setting up voice control via Google Assistant + Tasker.

### Claude Code Agent

The parallel-orchestrator agent is symlinked to `~/.claude/agents/` for global availability:

```bash
# Call from any project
/parallel-orchestrator [task description]
```

The agent definition is version-controlled in this repository at `agents/parallel-orchestrator.md`.

## License

MIT
