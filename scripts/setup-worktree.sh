#!/bin/bash
# setup-worktree.sh - Create git worktrees for parallel development
# Usage: setup-worktree.sh feature-a feature-b feature-c

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the current repo name
REPO_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)

if [ -z "$REPO_NAME" ]; then
    echo -e "${RED}Error: Not in a git repository${NC}"
    exit 1
fi

# Default worktree base directory (in WSL home, not /mnt/c for performance)
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/worktrees}"

# Create base directory if it doesn't exist
mkdir -p "$WORKTREE_BASE"

# Check if any branch names were provided
if [ $# -eq 0 ]; then
    echo "Usage: setup-worktree.sh <branch1> [branch2] [branch3] ..."
    echo ""
    echo "Examples:"
    echo "  setup-worktree.sh feature-auth"
    echo "  setup-worktree.sh feature-a feature-b feature-c"
    echo ""
    echo "Environment variables:"
    echo "  WORKTREE_BASE - Base directory for worktrees (default: ~/worktrees)"
    exit 1
fi

echo -e "${GREEN}Setting up worktrees for repo: $REPO_NAME${NC}"
echo "Base directory: $WORKTREE_BASE"
echo ""

# Process each branch name
for BRANCH in "$@"; do
    WORKTREE_PATH="$WORKTREE_BASE/${REPO_NAME}-${BRANCH}"

    # Check if worktree already exists
    if [ -d "$WORKTREE_PATH" ]; then
        echo -e "${YELLOW}Worktree already exists: $WORKTREE_PATH${NC}"
        continue
    fi

    # Check if branch already exists
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
        echo -e "${YELLOW}Branch $BRANCH exists, creating worktree...${NC}"
        git worktree add "$WORKTREE_PATH" "$BRANCH"
    else
        echo -e "${GREEN}Creating new branch $BRANCH with worktree...${NC}"
        git worktree add -b "$BRANCH" "$WORKTREE_PATH"
    fi

    echo -e "${GREEN}Created: $WORKTREE_PATH${NC}"
done

echo ""
echo -e "${GREEN}Worktree setup complete!${NC}"
echo ""
echo "List all worktrees:"
git worktree list
echo ""
echo "To run Claude Code in each worktree:"
for BRANCH in "$@"; do
    WORKTREE_PATH="$WORKTREE_BASE/${REPO_NAME}-${BRANCH}"
    echo "  cd $WORKTREE_PATH && claude"
done
