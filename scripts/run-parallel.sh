#!/bin/bash
# run-parallel.sh - Launch parallel Claude Code sessions using tmux
# Usage: run-parallel.sh --tasks "feature-a,feature-b" [--project /path/to/project]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
TASKS=""
PROJECT_DIR="$(pwd)"
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/worktrees}"
SESSION_PREFIX="claude-parallel"
PROMPT=""
USE_DOCKER=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tasks|-t)
            TASKS="$2"
            shift 2
            ;;
        --project|-p)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --prompt)
            PROMPT="$2"
            shift 2
            ;;
        --docker)
            USE_DOCKER=true
            shift
            ;;
        --help|-h)
            echo "Usage: run-parallel.sh --tasks \"task1,task2,task3\" [options]"
            echo ""
            echo "Options:"
            echo "  --tasks, -t     Comma-separated list of task/branch names"
            echo "  --project, -p   Project directory (default: current directory)"
            echo "  --prompt        Initial prompt to send to Claude"
            echo "  --docker        Use Docker sandbox instead of native Claude"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Examples:"
            echo "  run-parallel.sh --tasks \"feature-a,feature-b\""
            echo "  run-parallel.sh --tasks \"auth,api,tests\" --project ~/myproject"
            echo "  run-parallel.sh --tasks \"task1,task2\" --prompt \"Fix all lint errors\""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate inputs
if [ -z "$TASKS" ]; then
    echo -e "${RED}Error: --tasks is required${NC}"
    echo "Usage: run-parallel.sh --tasks \"task1,task2,task3\""
    exit 1
fi

# Check for tmux
if ! command -v tmux &> /dev/null; then
    echo -e "${RED}Error: tmux is not installed${NC}"
    echo "Install with: sudo apt install tmux"
    exit 1
fi

# Get repo name
cd "$PROJECT_DIR"
REPO_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)

if [ -z "$REPO_NAME" ]; then
    echo -e "${RED}Error: $PROJECT_DIR is not a git repository${NC}"
    exit 1
fi

# Parse tasks into array
IFS=',' read -ra TASK_ARRAY <<< "$TASKS"

echo -e "${GREEN}Starting parallel Claude sessions${NC}"
echo "Project: $REPO_NAME"
echo "Tasks: ${TASK_ARRAY[*]}"
echo "Worktree base: $WORKTREE_BASE"
echo ""

# Create or attach to main tmux session
MAIN_SESSION="${SESSION_PREFIX}-${REPO_NAME}"

# Kill existing session if it exists
tmux kill-session -t "$MAIN_SESSION" 2>/dev/null || true

# Create new session with first task
FIRST_TASK="${TASK_ARRAY[0]}"
FIRST_WORKTREE="$WORKTREE_BASE/${REPO_NAME}-${FIRST_TASK}"

# Ensure worktree exists
if [ ! -d "$FIRST_WORKTREE" ]; then
    echo -e "${YELLOW}Creating worktree for $FIRST_TASK...${NC}"
    cd "$PROJECT_DIR"
    if git show-ref --verify --quiet "refs/heads/$FIRST_TASK"; then
        git worktree add "$FIRST_WORKTREE" "$FIRST_TASK"
    else
        git worktree add -b "$FIRST_TASK" "$FIRST_WORKTREE"
    fi
fi

# Build Claude command
if [ "$USE_DOCKER" = true ]; then
    CLAUDE_CMD="docker sandbox run -w \"$FIRST_WORKTREE\" claude"
else
    CLAUDE_CMD="claude"
fi

if [ -n "$PROMPT" ]; then
    CLAUDE_CMD="$CLAUDE_CMD \"$PROMPT\""
fi

# Create tmux session with first window
tmux new-session -d -s "$MAIN_SESSION" -n "$FIRST_TASK" -c "$FIRST_WORKTREE"
tmux send-keys -t "$MAIN_SESSION:$FIRST_TASK" "$CLAUDE_CMD" C-m

echo -e "${GREEN}Started: $FIRST_TASK${NC}"

# Create additional windows for remaining tasks
for ((i=1; i<${#TASK_ARRAY[@]}; i++)); do
    TASK="${TASK_ARRAY[$i]}"
    WORKTREE="$WORKTREE_BASE/${REPO_NAME}-${TASK}"

    # Ensure worktree exists
    if [ ! -d "$WORKTREE" ]; then
        echo -e "${YELLOW}Creating worktree for $TASK...${NC}"
        cd "$PROJECT_DIR"
        if git show-ref --verify --quiet "refs/heads/$TASK"; then
            git worktree add "$WORKTREE" "$TASK"
        else
            git worktree add -b "$TASK" "$WORKTREE"
        fi
    fi

    # Build Claude command for this task
    if [ "$USE_DOCKER" = true ]; then
        CLAUDE_CMD="docker sandbox run -w \"$WORKTREE\" claude"
    else
        CLAUDE_CMD="claude"
    fi

    if [ -n "$PROMPT" ]; then
        CLAUDE_CMD="$CLAUDE_CMD \"$PROMPT\""
    fi

    # Create new window
    tmux new-window -t "$MAIN_SESSION" -n "$TASK" -c "$WORKTREE"
    tmux send-keys -t "$MAIN_SESSION:$TASK" "$CLAUDE_CMD" C-m

    echo -e "${GREEN}Started: $TASK${NC}"
done

echo ""
echo -e "${CYAN}All sessions started!${NC}"
echo ""
echo "Attach to session:  tmux attach -t $MAIN_SESSION"
echo "List windows:       tmux list-windows -t $MAIN_SESSION"
echo "Switch windows:     Ctrl+b n (next) / Ctrl+b p (previous)"
echo "Kill session:       tmux kill-session -t $MAIN_SESSION"
echo ""
echo -e "${YELLOW}Attaching to session...${NC}"

# Attach to the session
tmux attach -t "$MAIN_SESSION"
