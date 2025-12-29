# Parallel Orchestrator

An intelligent task orchestration agent for Claude Code that enables parallel execution of complex multi-step operations with hypothesis testing and root cause analysis.

## Features

- **Parallel Task Execution**: Intelligently identifies and executes independent operations concurrently
- **Agent Matching**: Routes tasks to specialized agents based on complexity and requirements
- **Hypothesis Testing**: Systematic approach to debugging with parallel hypothesis validation
- **Task Splitting**: Automatic decomposition of complex tasks into parallelizable units

## Installation

### Quick Setup (Symlink)
```bash
# The agent is already symlinked to your ~/.claude/agents/
ln -s ~/parallel-orchestrator/agents/parallel-orchestrator.md ~/.claude/agents/parallel-orchestrator.md
```

### Usage
Call the parallel-orchestrator agent from any Claude Code project:
```
/parallel-orchestrator [task description]
```

## Structure

```
parallel-orchestrator/
├── agents/
│   └── parallel-orchestrator.md    # Main agent definition
├── scripts/
│   ├── task-splitter.py           # Task decomposition logic
│   └── falsification/             # Hypothesis testing framework
└── README.md
```

## Development

All changes should be made to files in this repository, which will automatically sync to `~/.claude/agents/` via symlink.

## License

MIT
