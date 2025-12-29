# Parallel-Test Quick Start Guide

## What Is This?

The **Parallel-Test** tool is a systematic bug debugging system that:

1. **Generates hypotheses** about root causes (delegates to `/sc:root-cause`)
2. **Tests hypotheses in parallel** using git worktrees
3. **Identifies the actual root cause** through elimination
4. **Analyzes the code** and implements the fix (delegates to `/sc:analyze`, `/sc:troubleshoot`, `/sc:design`, `/sc:implement`)

Complete workflow: **Identify Bug** → **Hypothesis Testing** → **Analysis** → **Implementation** → **Fix Verified**

---

## Installation & Setup

### Prerequisites
- Python 3.8+
- Git
- YAML support: `pip install pyyaml`

### Verify Installation
```bash
cd ~/klauspython/parallel-orchestrator

# Check structure
ls scripts/falsification/
ls config/falsification_config.yaml
cat ~/.claude/agents/falsification-debugger.md
```

---

## Usage

### Simple Bug Debugging

```bash
/parallel-test "Your bug description"
```

**Example**:
```bash
/parallel-test "API returns 500 errors randomly under high load"
```

### With Options

**Analyze without running tests**:
```bash
/parallel-test --analyze-only "Bug description"
```

**Force sequential (no parallelization)**:
```bash
/parallel-test --no-parallel "Bug description"
```

**Limit hypotheses tested**:
```bash
/parallel-test --max-hypotheses 3 "Bug description"
```

**Verbose logging**:
```bash
/parallel-test --verbose "Bug description"
```

---

## Example Session

### Input
```bash
python scripts/falsification/test_hypothesis.py \
  "Auth service randomly rejects valid sessions"
```

### Output (6 Phases)

#### Phase 1: Generate Hypotheses
```
[Phase 1] Generating hypotheses with /sc:root-cause...
(Would delegate to: /sc:root-cause)
✓ Generated 3 hypotheses
```

#### Phase 2: Rank Hypotheses
```
[Phase 2] Ranking hypotheses...
✓ Top 3 hypotheses for testing:
  1. Token expiration check has race condition
     Probability: 85.0%, Impact: 90.0%
  2. Cache invalidation issue
     Probability: 72.0%, Impact: 70.0%
  3. Database transaction isolation problem
     Probability: 68.0%, Impact: 80.0%
```

#### Phase 3: Create Worktrees
```
[Phase 3] Creating git worktrees...
✓ Created 3 worktrees
✓ Test environments configured
```

#### Phase 4: Execute Tests
```
[Phase 4] Executing tests...
Executing tests in parallel...
✓ Test execution complete
```

#### Phase 5: Analyze Results
```
[Phase 5] Analyzing results...
======================================================================
FALSIFICATION REPORT
======================================================================
Falsified (Eliminated):
  ✗ Cache invalidation issue

Supported (Likely Root Cause):
  ✓ Token expiration check has race condition

Inconclusive (Needs Investigation):
  ? Database transaction isolation problem

Confidence: 92%
```

#### Phase 6: Next Actions
```
[Phase 6] Determining next actions...

Supported Hypothesis(es):
  ✓ Token expiration check has race condition

Recommended Actions:
  1. /sc:analyze   - Analyze root cause context
  2. /sc:troubleshoot - Diagnose error patterns
  3. /sc:design    - Design fix architecture
  4. /sc:implement - Implement the solution
```

---

## Workflow: From Bug to Fix

### Step 1: Identify Root Cause
```bash
python scripts/falsification/test_hypothesis.py \
  "Your bug description"
```

**Output**: Hypothesis test results showing which root cause is likely

### Step 2: Analyze the Code
Once you know the root cause:
```
/sc:analyze
Focus on: [Root cause from step 1]
File: [Affected file]
```

### Step 3: Design the Fix
```
/sc:design
Problem: [Root cause]
Current: [Current behavior]
Proposed: [Your fix approach]
```

### Step 4: Implement the Solution
```
/sc:implement
Fix: [Your fix description]
File: [File to modify]
Tests: [Test file]
```

### Step 5: Verify
- Run your test suite
- Verify the bug is fixed
- Check for regressions

---

## Configuration

### Default Settings
The system comes with sensible defaults in `config/falsification_config.yaml`:

- **Max hypotheses**: 5
- **Test timeout**: 5 minutes
- **Parallelization threshold**: 60 seconds
- **All SuperClaude agents enabled**

### Customize Settings
Edit `config/falsification_config.yaml`:

```yaml
hypothesis_management:
  max_concurrent: 3  # Reduce to 3 hypotheses

test_execution:
  default_timeout: 600  # Increase to 10 minutes
  min_parallel_time: 30  # Parallelize for tests >= 30s

agent_integration:
  root_cause_analyst:
    enabled: true  # Enable RCA agent
```

---

## Understanding the Output

### Report Classifications

**Falsified (✗)**
- Hypothesis **eliminated** from consideration
- Test passed, bug still exists
- This is NOT the root cause

**Supported (✓)**
- Hypothesis **likely to be correct**
- Test failed, bug disappeared
- This IS probably the root cause

**Inconclusive (?)**
- Test **timed out, errored, or unclear**
- Needs further investigation
- Try: adjusting test strategy, increasing timeout

### Confidence Score
- **0-50%**: Low confidence, needs refinement
- **50-75%**: Moderate confidence, likely correct
- **75-100%**: High confidence, probable root cause

---

## Troubleshooting

### "All hypotheses falsified"
→ The root cause isn't in the generated hypotheses
→ Solution:
  1. Run `/sc:root-cause` with more context
  2. Add error logs and stack traces
  3. Generate new hypotheses with refined bug description

### "Tests timing out"
→ Tests are taking too long
→ Solution:
  ```bash
  python scripts/falsification/test_hypothesis.py \
    --timeout 600 \  # Increase to 10 minutes
    "Bug description"
  ```

### "Worktree creation failed"
→ Git issue with current repo
→ Solution:
  1. Check `git status` - repository must be clean
  2. Ensure main branch exists
  3. Free up disk space
  4. Check git configuration

### "Can't find test scripts"
→ Tests weren't created properly
→ Solution:
  1. Check that test files exist
  2. Verify test strategy is correct
  3. Ensure test command works locally

---

## Key Concepts

### Hypothesis
A testable claim about a potential bug root cause

**Example hypothesis**:
- **Description**: "Race condition in session validation"
- **Test Strategy**: Run 100 concurrent login attempts
- **Expected Behavior**: All logins succeed without conflicts
- **Probability**: 85% likely to be the root cause
- **Impact**: 90% severity if true

### Falsification
Testing to **disprove** rather than prove (Karl Popper's principle)

- If test **passes**: Hypothesis is **falsified** (eliminated)
- If test **fails**: Hypothesis is **supported** (likely)
- Eliminates unlikely candidates through evidence

### Worktree
Isolated copy of repository for safe testing

- Each hypothesis tested in separate worktree
- No interference between concurrent tests
- Clean environment for each test
- Easy cleanup after testing

### Parallelization
Running multiple tests simultaneously

- 5 tests @ 60s each = 300s sequential
- Same tests in parallel = ~75s (4x faster!)
- Only parallelizes if benefit > overhead

---

## Best Practices

✅ **DO**
- Provide detailed bug descriptions (symptoms, frequency, environment)
- Include error logs and stack traces when available
- Start with `--analyze-only` to review hypotheses before testing
- Review inconclusive results - they might indicate issues
- Use verbose logging for debugging

❌ **DON'T**
- Use vague bug descriptions ("something is broken")
- Run without understanding the reported results
- Ignore inconclusive results
- Assume the top-ranked hypothesis is always correct
- Skip the fix design phase (/sc:design)

---

## Advanced Usage

### Resume a Session
```bash
python scripts/falsification/test_hypothesis.py \
  --session-id falsification_20250101_120000
```

### Export Results
```bash
# JSON export
python scripts/falsification/test_hypothesis.py \
  --export json \
  "Bug description"

# Markdown report
python scripts/falsification/test_hypothesis.py \
  --export markdown \
  "Bug description"
```

### Custom Hypothesis File
```bash
python scripts/falsification/test_hypothesis.py \
  --hypotheses-file hypotheses.json \
  "Bug description"
```

---

## Next Steps

1. **Run your first session**:
   ```bash
   /parallel-test "Describe a bug you need to debug"
   ```

2. **Review the results** and supported hypotheses

3. **Use SuperClaude agents** to analyze and implement the fix:
   ```
   /sc:analyze      # Analyze root cause
   /sc:troubleshoot # Diagnose error patterns
   /sc:design       # Design the fix
   /sc:implement    # Implement the solution
   ```

4. **Verify the fix** works and doesn't break anything

---

## Documentation

- **Complete Architecture**: `docs/falsification-debugger-architecture.md`
- **Agent Definition**: `~/.claude/agents/falsification-debugger.md`
- **Configuration**: `config/falsification_config.yaml`
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md`

---

## Questions?

Refer to:
1. **Agent Help**: `/falsify --help`
2. **Architecture Docs**: Read the architecture.md file
3. **Config Guide**: Review falsification_config.yaml
4. **Examples**: See IMPLEMENTATION_SUMMARY.md

**Happy debugging! 🐛**
