#!/bin/bash
# merge-results.sh - Aggregate results from parallel branches with conflict detection
# Usage: merge-results.sh --branches "feature-a,feature-b" [--target main] [--dry-run]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
BRANCHES=""
TARGET_BRANCH="main"
DRY_RUN=false
CREATE_PRS=false
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/worktrees}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --branches|-b)
            BRANCHES="$2"
            shift 2
            ;;
        --target|-t)
            TARGET_BRANCH="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --create-prs)
            CREATE_PRS=true
            shift
            ;;
        --help|-h)
            echo "Usage: merge-results.sh --branches \"branch1,branch2\" [options]"
            echo ""
            echo "Options:"
            echo "  --branches, -b   Comma-separated list of branches to merge"
            echo "  --target, -t     Target branch (default: main)"
            echo "  --dry-run        Check for conflicts without merging"
            echo "  --create-prs     Create GitHub PRs instead of direct merge"
            echo "  --help, -h       Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate inputs
if [ -z "$BRANCHES" ]; then
    echo -e "${RED}Error: --branches is required${NC}"
    exit 1
fi

# Check for gh CLI if creating PRs
if [ "$CREATE_PRS" = true ]; then
    if ! command -v gh &> /dev/null; then
        echo -e "${RED}Error: GitHub CLI (gh) is required for --create-prs${NC}"
        echo "Install with: sudo apt install gh"
        exit 1
    fi
fi

# Parse branches
IFS=',' read -ra BRANCH_ARRAY <<< "$BRANCHES"

echo -e "${CYAN}=== Merge Results Analysis ===${NC}"
echo "Target branch: $TARGET_BRANCH"
echo "Branches to merge: ${BRANCH_ARRAY[*]}"
echo ""

# Get current branch
CURRENT_BRANCH=$(git branch --show-current)
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")

# Function to check conflicts between two branches
check_conflicts() {
    local branch1=$1
    local branch2=$2

    # Get files modified in each branch relative to target
    local files1=$(git diff --name-only "${TARGET_BRANCH}...${branch1}" 2>/dev/null | sort)
    local files2=$(git diff --name-only "${TARGET_BRANCH}...${branch2}" 2>/dev/null | sort)

    # Find overlapping files
    local overlap=$(comm -12 <(echo "$files1") <(echo "$files2"))

    if [ -n "$overlap" ]; then
        echo "$overlap"
        return 1
    fi
    return 0
}

# Function to get branch stats
get_branch_stats() {
    local branch=$1

    local commits=$(git rev-list --count "${TARGET_BRANCH}..${branch}" 2>/dev/null || echo "0")
    local files=$(git diff --name-only "${TARGET_BRANCH}...${branch}" 2>/dev/null | wc -l)
    local insertions=$(git diff --stat "${TARGET_BRANCH}...${branch}" 2>/dev/null | tail -1 | grep -oP '\d+(?= insertion)' || echo "0")
    local deletions=$(git diff --stat "${TARGET_BRANCH}...${branch}" 2>/dev/null | tail -1 | grep -oP '\d+(?= deletion)' || echo "0")

    echo "commits=$commits files=$files +$insertions -$deletions"
}

# Check each branch exists
echo -e "${CYAN}Checking branches...${NC}"
VALID_BRANCHES=()
for branch in "${BRANCH_ARRAY[@]}"; do
    if git show-ref --verify --quiet "refs/heads/$branch"; then
        stats=$(get_branch_stats "$branch")
        echo -e "  ${GREEN}$branch${NC} ($stats)"
        VALID_BRANCHES+=("$branch")
    else
        echo -e "  ${RED}$branch${NC} - branch not found"
    fi
done
echo ""

if [ ${#VALID_BRANCHES[@]} -eq 0 ]; then
    echo -e "${RED}No valid branches found${NC}"
    exit 1
fi

# Check for conflicts between all branch pairs
echo -e "${CYAN}Checking for conflicts...${NC}"
HAS_CONFLICTS=false
declare -A CONFLICT_MAP

for ((i=0; i<${#VALID_BRANCHES[@]}; i++)); do
    for ((j=i+1; j<${#VALID_BRANCHES[@]}; j++)); do
        branch1="${VALID_BRANCHES[$i]}"
        branch2="${VALID_BRANCHES[$j]}"

        overlap=$(check_conflicts "$branch1" "$branch2" || true)

        if [ -n "$overlap" ]; then
            HAS_CONFLICTS=true
            echo -e "  ${RED}Conflict${NC}: $branch1 <-> $branch2"
            echo "$overlap" | while read -r file; do
                echo -e "    - $file"
            done
            CONFLICT_MAP["$branch1,$branch2"]="$overlap"
        else
            echo -e "  ${GREEN}OK${NC}: $branch1 <-> $branch2"
        fi
    done
done
echo ""

# Check for conflicts with target branch
echo -e "${CYAN}Checking against $TARGET_BRANCH...${NC}"
for branch in "${VALID_BRANCHES[@]}"; do
    # Try a test merge
    git checkout -q "$TARGET_BRANCH"

    if git merge --no-commit --no-ff "$branch" 2>/dev/null; then
        echo -e "  ${GREEN}OK${NC}: $branch can merge cleanly"
        git merge --abort 2>/dev/null || true
    else
        echo -e "  ${YELLOW}Warning${NC}: $branch may have conflicts with $TARGET_BRANCH"
        git merge --abort 2>/dev/null || true
    fi
done

# Return to original branch
git checkout -q "$CURRENT_BRANCH" 2>/dev/null || git checkout -q "$TARGET_BRANCH"
echo ""

# If dry run, stop here
if [ "$DRY_RUN" = true ]; then
    echo -e "${CYAN}=== Dry Run Complete ===${NC}"
    if [ "$HAS_CONFLICTS" = true ]; then
        echo -e "${YELLOW}Conflicts detected between some branches.${NC}"
        echo "Review the overlapping files and resolve before merging."
    else
        echo -e "${GREEN}No conflicts detected. Safe to merge.${NC}"
    fi
    exit 0
fi

# If conflicts exist, warn and suggest resolution
if [ "$HAS_CONFLICTS" = true ]; then
    echo -e "${YELLOW}=== Conflicts Detected ===${NC}"
    echo "Some branches modify the same files. Options:"
    echo "  1. Merge branches sequentially (recommended order below)"
    echo "  2. Manually resolve conflicts"
    echo "  3. Re-split the task to avoid conflicts"
    echo ""

    # Suggest merge order (fewest conflicts first)
    echo "Suggested merge order:"
    for branch in "${VALID_BRANCHES[@]}"; do
        echo "  git merge $branch"
    done
    echo ""

    read -p "Continue with sequential merge? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Perform merge or create PRs
if [ "$CREATE_PRS" = true ]; then
    echo -e "${CYAN}=== Creating Pull Requests ===${NC}"

    for branch in "${VALID_BRANCHES[@]}"; do
        echo -e "Creating PR for ${GREEN}$branch${NC}..."

        # Push branch if not already pushed
        git push -u origin "$branch" 2>/dev/null || true

        # Create PR
        gh pr create \
            --base "$TARGET_BRANCH" \
            --head "$branch" \
            --title "AI Task: $branch" \
            --body "Automated PR from parallel task execution.

## Changes
$(git log --oneline "${TARGET_BRANCH}..${branch}" | head -10)

---
Created by parallel-orchestrator" \
            2>/dev/null || echo "  PR may already exist"
    done
else
    echo -e "${CYAN}=== Merging Branches ===${NC}"

    git checkout "$TARGET_BRANCH"

    for branch in "${VALID_BRANCHES[@]}"; do
        echo -e "Merging ${GREEN}$branch${NC}..."

        if git merge --no-ff "$branch" -m "Merge parallel task: $branch"; then
            echo -e "  ${GREEN}Success${NC}"
        else
            echo -e "  ${RED}Merge failed${NC}"
            echo "Resolve conflicts and run: git merge --continue"
            exit 1
        fi
    done
fi

echo ""
echo -e "${GREEN}=== Merge Complete ===${NC}"

# Cleanup worktrees
echo ""
read -p "Remove worktrees for merged branches? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    for branch in "${VALID_BRANCHES[@]}"; do
        WORKTREE_PATH="$WORKTREE_BASE/${REPO_NAME}-${branch}"
        if [ -d "$WORKTREE_PATH" ]; then
            echo "Removing worktree: $WORKTREE_PATH"
            git worktree remove "$WORKTREE_PATH" --force 2>/dev/null || true
        fi
    done

    # Prune worktree references
    git worktree prune
fi

echo ""
echo -e "${GREEN}Done!${NC}"
