#!/bin/bash
# orchestrate.sh - Fully automated parallel task execution
# Usage: orchestrate.sh "Implement user authentication with login, registration, and tests"
#
# This script:
# 1. Analyzes your task with Claude API
# 2. Splits it into non-conflicting subtasks
# 3. Creates git worktrees for each
# 4. Runs Claude Code in parallel (background)
# 5. Monitors progress
# 6. Merges results and creates PRs

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_BASE="${WORKTREE_BASE:-$HOME/worktrees}"
MAX_PARALLEL="${MAX_PARALLEL:-3}"
AUTO_MERGE="${AUTO_MERGE:-false}"
WAIT_FOR_COMPLETION="${WAIT_FOR_COMPLETION:-true}"

# Parse arguments
TASK=""
DRY_RUN=false
ANALYZE_ONLY=false
INTERACTIVE=false
NUM_WORKERS=2

while [[ $# -gt 0 ]]; do
    case $1 in
        --analyze|-a)
            ANALYZE_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --interactive|-i)
            INTERACTIVE=true
            shift
            ;;
        --workers|-w)
            NUM_WORKERS="$2"
            shift 2
            ;;
        --auto-merge)
            AUTO_MERGE=true
            shift
            ;;
        --no-wait)
            WAIT_FOR_COMPLETION=false
            shift
            ;;
        --help|-h)
            cat << 'EOF'
Usage: orchestrate.sh [options] "Your task description"

Fully automated parallel task execution:
1. Analyzes task for parallelization suitability
2. Splits task into non-conflicting subtasks (via Claude API)
3. Creates git worktrees for each subtask
4. Runs Claude Code in parallel
5. Monitors progress and merges results

Options:
  --analyze,-a      RECOMMENDED: Analyze task suitability without executing
  --dry-run         Show execution plan without running
  --interactive,-i  Run Claude Code interactively (attach to tmux)
  --workers,-w N    Number of parallel workers (default: 2)
  --auto-merge      Automatically merge completed branches
  --no-wait         Don't wait for completion (background mode)
  --help,-h         Show this help

Examples:
  orchestrate.sh --analyze "Add user authentication"     # Check suitability first
  orchestrate.sh "Add user authentication with tests"   # Full execution
  orchestrate.sh --workers 3 "Refactor the API layer"
  orchestrate.sh --dry-run "Implement new dashboard"

Environment:
  ANTHROPIC_API_KEY   Required for task splitting
  WORKTREE_BASE       Base directory for worktrees (default: ~/worktrees)
  MAX_PARALLEL        Maximum parallel workers (default: 3)
EOF
            exit 0
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
        *)
            TASK="$1"
            shift
            ;;
    esac
done

# Validate
if [ -z "$TASK" ]; then
    echo -e "${RED}Error: Task description required${NC}"
    echo "Usage: orchestrate.sh \"Your task description\""
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${YELLOW}Warning: ANTHROPIC_API_KEY not set${NC}"
    echo "Task splitting will use fallback heuristics instead of AI"
fi

# Check we're in a git repo
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo -e "${RED}Error: Not in a git repository${NC}"
    exit 1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
CURRENT_BRANCH=$(git branch --show-current)

# ═══════════════════════════════════════════════════════════════
# ANALYZE MODE: Provide detailed suitability report
# ═══════════════════════════════════════════════════════════════
if [ "$ANALYZE_ONLY" = true ]; then
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         PARALLELIZATION SUITABILITY ANALYSIS                 ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Repository: ${GREEN}$REPO_NAME${NC}"
    echo -e "Task:       ${YELLOW}$TASK${NC}"
    echo -e "Requested workers: ${GREEN}$NUM_WORKERS${NC}"
    echo ""

    # Run analysis
    echo -e "${CYAN}Analyzing task...${NC}"
    echo ""

    ANALYSIS=$(python3 "$SCRIPT_DIR/task-splitter.py" "$TASK" --output json 2>&1)

    # Parse and display analysis
    python3 << EOF
import json
import sys

try:
    data = json.loads('''$ANALYSIS''')
except:
    print("Could not parse analysis. Raw output:")
    print('''$ANALYSIS''')
    sys.exit(1)

# Header
print("═" * 60)
print("PARALLELIZATION ANALYSIS REPORT")
print("═" * 60)
print()

# Overall verdict
can_parallel = data.get('can_parallelize', True)
conflict_risk = data.get('conflict_risk', 'UNKNOWN')
validation = data.get('validation', {})

if validation.get('valid', True) == False:
    print("🔴 VERDICT: NOT SUITABLE FOR PARALLELIZATION")
    print("   Reason: File conflicts detected between subtasks")
elif conflict_risk == 'HIGH':
    print("🟡 VERDICT: HIGH RISK - Proceed with caution")
elif conflict_risk == 'MEDIUM':
    print("🟡 VERDICT: MEDIUM RISK - Review subtasks carefully")
elif can_parallel:
    print("🟢 VERDICT: SUITABLE FOR PARALLELIZATION")
else:
    reason = data.get('reason_if_not', 'Unknown')
    print(f"🔴 VERDICT: NOT PARALLELIZABLE - {reason}")

print()

# Analysis
if 'analysis' in data:
    print("📋 ANALYSIS:")
    print(f"   {data['analysis']}")
    print()

# Subtasks
subtasks = data.get('subtasks', [])
if subtasks:
    print(f"📦 PROPOSED SUBTASKS ({len(subtasks)}):")
    for i, st in enumerate(subtasks, 1):
        name = st.get('name', 'unknown')
        desc = st.get('description', 'No description')
        complexity = st.get('estimated_complexity', 'unknown')
        files_mod = st.get('files_to_modify', [])
        files_create = st.get('files_to_create', [])

        print(f"   {i}. {name}")
        print(f"      Description: {desc}")
        print(f"      Complexity: {complexity}")
        if files_mod:
            print(f"      Files to modify: {', '.join(files_mod[:5])}")
        if files_create:
            print(f"      Files to create: {', '.join(files_create[:5])}")
        print()

# File ownership map
file_ownership = data.get('file_ownership', {})
if file_ownership:
    print("📁 FILE OWNERSHIP (no overlaps = safe):")
    for file, owner in list(file_ownership.items())[:10]:
        print(f"   {file} → {owner}")
    if len(file_ownership) > 10:
        print(f"   ... and {len(file_ownership) - 10} more files")
    print()

# Conflicts
if not validation.get('valid', True):
    conflicts = data.get('conflict_details', [])
    print("⚠️  FILE CONFLICTS DETECTED:")
    for c in conflicts:
        print(f"   🔴 {c['file']}: {c['subtask1']} vs {c['subtask2']}")
    print()

potential = data.get('potential_conflicts', [])
if potential:
    print("⚠️  POTENTIAL ISSUES:")
    for p in potential:
        print(f"   - {p}")
    print()

# Merge strategy
merge_order = data.get('merge_order', [])
if merge_order:
    print("🔀 RECOMMENDED MERGE ORDER:")
    print(f"   {' → '.join(merge_order)}")
    print()

# Integration notes
notes = data.get('integration_notes', '')
if notes:
    print("📝 INTEGRATION NOTES:")
    print(f"   {notes}")
    print()

# Recommendations
print("═" * 60)
print("RECOMMENDATIONS")
print("═" * 60)

if validation.get('valid', True) and can_parallel and conflict_risk != 'HIGH':
    print("✅ This task is suitable for parallel execution.")
    print()
    print("To execute:")
    print(f"   orchestrate.sh \"{'''$TASK'''[:50]}...\"")
    print()
    print("Or with more workers:")
    print(f"   orchestrate.sh --workers 3 \"{'''$TASK'''[:50]}...\"")
else:
    print("❌ This task is NOT recommended for parallel execution.")
    print()
    print("Options:")
    print("   1. Run sequentially:")
    print(f"      claude \"{'''$TASK'''[:50]}...\"")
    print()
    print("   2. Manually restructure the task to avoid file conflicts")
    print()
    print("   3. Split into separate independent tasks")

print()
EOF

    exit 0
fi

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           PARALLEL ORCHESTRATOR - AUTOMATED MODE             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Repository: ${GREEN}$REPO_NAME${NC}"
echo -e "Branch:     ${GREEN}$CURRENT_BRANCH${NC}"
echo -e "Task:       ${YELLOW}$TASK${NC}"
echo -e "Workers:    ${GREEN}$NUM_WORKERS${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 1: Analyze and Split Task (WITH CONFLICT VALIDATION)
# ═══════════════════════════════════════════════════════════════
echo -e "${CYAN}[1/5] Analyzing task and creating subtasks...${NC}"

# Run task splitter and capture output
SPLIT_OUTPUT=$(python3 "$SCRIPT_DIR/task-splitter.py" "$TASK" --output json 2>&1)
SPLIT_STDERR=$(python3 "$SCRIPT_DIR/task-splitter.py" "$TASK" --output json 2>&1 >/dev/null || true)

# Check for validation failures (CRITICAL)
if echo "$SPLIT_OUTPUT" | grep -q '"validation_failed": true'; then
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  CONFLICT DETECTED - CANNOT PARALLELIZE SAFELY${NC}"
    echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "The proposed task split would cause merge conflicts:"
    echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for conflict in data.get('conflict_details', []):
        print(f\"  - {conflict['file']}: {conflict['subtask1']} vs {conflict['subtask2']}\")
except: pass
"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo "  1. Run the task sequentially (single Claude session)"
    echo "  2. Manually split the task into non-conflicting parts"
    echo "  3. Restructure the task to avoid shared file modifications"
    echo ""
    echo "To run sequentially instead:"
    echo "  cd $REPO_ROOT && claude \"$TASK\""
    exit 1
fi

# Check conflict risk level
CONFLICT_RISK=$(echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('conflict_risk', 'UNKNOWN'))
except: print('UNKNOWN')
")

if [ "$CONFLICT_RISK" = "HIGH" ]; then
    echo -e "${RED}WARNING: High conflict risk detected!${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
elif [ "$CONFLICT_RISK" = "MEDIUM" ]; then
    echo -e "${YELLOW}Note: Medium conflict risk - review subtasks carefully${NC}"
fi

# Check if task can be parallelized
CAN_PARALLELIZE=$(echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print('true' if data.get('can_parallelize', True) else 'false')
except: print('true')
")

if [ "$CAN_PARALLELIZE" = "false" ]; then
    REASON=$(echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('reason_if_not', 'Task cannot be safely parallelized'))
except: print('Task cannot be safely parallelized')
")
    echo -e "${YELLOW}Task cannot be parallelized: $REASON${NC}"
    echo ""
    echo "Running sequentially instead..."
    cd "$REPO_ROOT" && claude "$TASK"
    exit 0
fi

# Parse subtasks from output
if echo "$SPLIT_OUTPUT" | grep -q '"subtasks"'; then
    # Get subtasks with their file assignments for verification
    SUBTASK_INFO=$(echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
subtasks = data.get('subtasks', [])
for st in subtasks[:$NUM_WORKERS]:
    name = st.get('name', 'task')
    files = st.get('files_to_modify', []) + st.get('files_to_create', [])
    print(f\"{name}|{','.join(files[:5])}\")
")

    SUBTASKS=$(echo "$SPLIT_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
subtasks = data.get('subtasks', [])
for st in subtasks[:$NUM_WORKERS]:
    print(st.get('name', 'task'))
")
else
    # Fallback: create generic subtasks
    echo -e "${YELLOW}Using fallback task splitting${NC}"
    SUBTASKS=$(for i in $(seq 1 $NUM_WORKERS); do echo "subtask-$i"; done)
fi

# Convert to array
readarray -t SUBTASK_ARRAY <<< "$SUBTASKS"

echo -e "  Subtasks created: ${GREEN}${#SUBTASK_ARRAY[@]}${NC}"
echo -e "  Conflict risk: ${GREEN}$CONFLICT_RISK${NC}"

# Show file assignments
if [ -n "$SUBTASK_INFO" ]; then
    echo ""
    echo -e "  ${CYAN}File ownership:${NC}"
    echo "$SUBTASK_INFO" | while IFS='|' read -r name files; do
        echo -e "    ${GREEN}$name${NC}: $files"
    done
fi
echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY RUN] Would create worktrees and run Claude for each subtask${NC}"
    echo ""
    echo "Proposed subtasks:"
    for st in "${SUBTASK_ARRAY[@]}"; do
        echo "  - $st"
    done
    exit 0
fi

# ═══════════════════════════════════════════════════════════════
# STEP 2: Create Worktrees
# ═══════════════════════════════════════════════════════════════
echo -e "${CYAN}[2/5] Creating git worktrees...${NC}"

mkdir -p "$WORKTREE_BASE"

for subtask in "${SUBTASK_ARRAY[@]}"; do
    WORKTREE_PATH="$WORKTREE_BASE/${REPO_NAME}-${subtask}"

    if [ -d "$WORKTREE_PATH" ]; then
        echo -e "  ${YELLOW}Exists${NC}: $subtask"
    else
        if git show-ref --verify --quiet "refs/heads/$subtask"; then
            git worktree add "$WORKTREE_PATH" "$subtask" 2>/dev/null
        else
            git worktree add -b "$subtask" "$WORKTREE_PATH" 2>/dev/null
        fi
        echo -e "  ${GREEN}Created${NC}: $subtask → $WORKTREE_PATH"
    fi
done
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 3: Run Claude Code in Parallel
# ═══════════════════════════════════════════════════════════════
echo -e "${CYAN}[3/5] Starting parallel Claude Code sessions...${NC}"

SESSION_NAME="orchestrator-$$"
PIDS=()
LOG_DIR="/tmp/orchestrator-$$"
mkdir -p "$LOG_DIR"

# Get prompts for each subtask
get_subtask_prompt() {
    local subtask=$1
    local full_prompt="You are working on subtask '$subtask' of the larger task: $TASK

Focus ONLY on your subtask. Do not modify files that other subtasks might touch.

Your subtask: $subtask

Complete this subtask fully, including any necessary tests.
When done, make sure all changes are saved."
    echo "$full_prompt"
}

for subtask in "${SUBTASK_ARRAY[@]}"; do
    WORKTREE_PATH="$WORKTREE_BASE/${REPO_NAME}-${subtask}"
    LOG_FILE="$LOG_DIR/${subtask}.log"
    PROMPT=$(get_subtask_prompt "$subtask")

    echo -e "  Starting ${GREEN}$subtask${NC}..."

    # Run Claude Code in background with the prompt
    (
        cd "$WORKTREE_PATH"
        echo "=== Claude Code session for $subtask ===" > "$LOG_FILE"
        echo "Started: $(date)" >> "$LOG_FILE"
        echo "Prompt: $PROMPT" >> "$LOG_FILE"
        echo "---" >> "$LOG_FILE"

        # Run Claude with prompt, capturing output
        claude --dangerously-skip-permissions "$PROMPT" >> "$LOG_FILE" 2>&1

        # Commit changes if any
        if [ -n "$(git status --porcelain)" ]; then
            git add -A
            git commit -m "AI: Complete subtask $subtask

Part of: $TASK
Automated by parallel-orchestrator" >> "$LOG_FILE" 2>&1
        fi

        echo "---" >> "$LOG_FILE"
        echo "Completed: $(date)" >> "$LOG_FILE"
    ) &

    PIDS+=($!)
done

echo -e "  ${GREEN}${#PIDS[@]} Claude sessions started${NC}"
echo ""

# ═══════════════════════════════════════════════════════════════
# STEP 4: Monitor Progress
# ═══════════════════════════════════════════════════════════════
if [ "$WAIT_FOR_COMPLETION" = true ]; then
    echo -e "${CYAN}[4/5] Monitoring progress...${NC}"
    echo "  Log directory: $LOG_DIR"
    echo ""

    # Wait for all processes
    FAILED=()
    SUCCEEDED=()

    for i in "${!PIDS[@]}"; do
        pid=${PIDS[$i]}
        subtask=${SUBTASK_ARRAY[$i]}

        echo -ne "  Waiting for ${YELLOW}$subtask${NC}..."

        if wait $pid; then
            echo -e " ${GREEN}Done${NC}"
            SUCCEEDED+=("$subtask")
        else
            echo -e " ${RED}Failed${NC}"
            FAILED+=("$subtask")
        fi
    done

    echo ""
    echo -e "  ${GREEN}Succeeded${NC}: ${#SUCCEEDED[@]}"
    echo -e "  ${RED}Failed${NC}: ${#FAILED[@]}"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: Merge Results
    # ═══════════════════════════════════════════════════════════════
    if [ ${#SUCCEEDED[@]} -gt 0 ]; then
        echo -e "${CYAN}[5/5] Merging results...${NC}"

        # Check for conflicts first
        cd "$REPO_ROOT"

        BRANCHES_TO_MERGE=$(IFS=,; echo "${SUCCEEDED[*]}")

        echo "  Checking for conflicts..."
        CONFLICT_CHECK=$("$SCRIPT_DIR/merge-results.sh" --branches "$BRANCHES_TO_MERGE" --dry-run 2>&1 || true)

        if echo "$CONFLICT_CHECK" | grep -q "Conflict"; then
            echo -e "  ${YELLOW}Potential conflicts detected${NC}"
            echo "$CONFLICT_CHECK" | grep -A2 "Conflict"
            echo ""

            if [ "$AUTO_MERGE" = true ]; then
                echo -e "  ${YELLOW}Creating PRs instead of direct merge...${NC}"
                "$SCRIPT_DIR/merge-results.sh" --branches "$BRANCHES_TO_MERGE" --create-prs
            else
                echo "  Run manually: merge-results.sh --branches \"$BRANCHES_TO_MERGE\""
            fi
        else
            echo -e "  ${GREEN}No conflicts detected${NC}"

            if [ "$AUTO_MERGE" = true ]; then
                "$SCRIPT_DIR/merge-results.sh" --branches "$BRANCHES_TO_MERGE"
            else
                echo "  To merge: merge-results.sh --branches \"$BRANCHES_TO_MERGE\""
                echo "  To create PRs: merge-results.sh --branches \"$BRANCHES_TO_MERGE\" --create-prs"
            fi
        fi
    fi
else
    echo -e "${CYAN}[4/5] Running in background mode${NC}"
    echo "  Sessions running with PIDs: ${PIDS[*]}"
    echo "  Logs: $LOG_DIR"
    echo ""
    echo "  To monitor: tail -f $LOG_DIR/*.log"
    echo "  To check status: ps -p ${PIDS[*]} 2>/dev/null || echo 'All completed'"
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    ORCHESTRATION COMPLETE                    ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Summary:"
echo "  Task: $TASK"
echo "  Subtasks: ${#SUBTASK_ARRAY[@]}"
echo "  Worktrees: $WORKTREE_BASE/${REPO_NAME}-*"
echo "  Logs: $LOG_DIR"
echo ""
echo "Next steps:"
echo "  1. Review changes: git diff $CURRENT_BRANCH...<subtask-branch>"
echo "  2. Merge results: merge-results.sh --branches \"${SUBTASK_ARRAY[*]// /,}\""
echo "  3. Cleanup: git worktree prune"
