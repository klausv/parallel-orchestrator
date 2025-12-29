# Falsification-Debugger Agent Architecture

## System Overview

The falsification-debugger agent systematically eliminates bug hypotheses through parallel falsification testing using git worktrees. It integrates with the existing parallel-orchestrator infrastructure and leverages specialized agents for hypothesis generation and quality validation.

---

## 1. Component Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                   FALSIFICATION-DEBUGGER AGENT                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────┐     ┌──────────────────┐                    │
│  │   Hypothesis   │────▶│   Hypothesis     │                    │
│  │   Management   │     │   Validator      │                    │
│  └────────────────┘     └──────────────────┘                    │
│         │                        │                               │
│         ▼                        ▼                               │
│  ┌────────────────┐     ┌──────────────────┐                    │
│  │  Sequential    │────▶│   Ranking        │                    │
│  │  Thinking MCP  │     │   Engine         │                    │
│  └────────────────┘     └──────────────────┘                    │
│                                  │                               │
│                                  ▼                               │
│                         ┌──────────────────┐                    │
│                         │  Top 5 Queue     │                    │
│                         │  (Priority)      │                    │
│                         └──────────────────┘                    │
│                                  │                               │
│         ┌────────────────────────┴────────────────────────┐     │
│         ▼                        ▼                        ▼     │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐ │
│  │  Worktree   │        │  Worktree   │        │  Worktree   │ │
│  │  Manager    │        │  Manager    │        │  Manager    │ │
│  └─────────────┘        └─────────────┘        └─────────────┘ │
│         │                        │                        │     │
│         ▼                        ▼                        ▼     │
│  ┌─────────────┐        ┌─────────────┐        ┌─────────────┐ │
│  │   Test      │        │   Test      │        │   Test      │ │
│  │  Executor   │        │  Executor   │        │  Executor   │ │
│  └─────────────┘        └─────────────┘        └─────────────┘ │
│         │                        │                        │     │
│         └────────────────────────┴────────────────────────┘     │
│                                  │                               │
│                                  ▼                               │
│                         ┌──────────────────┐                    │
│                         │   Results        │                    │
│                         │   Aggregator     │                    │
│                         └──────────────────┘                    │
│                                  │                               │
│                                  ▼                               │
│                         ┌──────────────────┐                    │
│                         │   Falsification  │                    │
│                         │   Report         │                    │
│                         └──────────────────┘                    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

EXTERNAL INTEGRATIONS:
┌────────────────────────┐    ┌────────────────────────┐
│  root-cause-analyst    │───▶│  Hypothesis Generation │
└────────────────────────┘    └────────────────────────┘

┌────────────────────────┐    ┌────────────────────────┐
│  parallel-orchestrator │───▶│  Worktree Management   │
└────────────────────────┘    └────────────────────────┘

┌────────────────────────┐    ┌────────────────────────┐
│  memory MCP            │───▶│  Session Persistence   │
└────────────────────────┘    └────────────────────────┘

┌────────────────────────┐    ┌────────────────────────┐
│  sequential-thinking   │───▶│  Ranking Logic         │
└────────────────────────┘    └────────────────────────┘

┌────────────────────────┐    ┌────────────────────────┐
│  quality-engineer      │───▶│  Test Validation       │
└────────────────────────┘    └────────────────────────┘
```

---

## 2. Data Flow for Typical Debugging Session

```
SESSION START
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 1. INITIALIZATION                                        │
├──────────────────────────────────────────────────────────┤
│ • list_memories() → Check for existing session           │
│ • read_memory("falsification_session") → Resume state    │
│ • User provides bug description                          │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 2. HYPOTHESIS GENERATION (Delegated to RCA)             │
├──────────────────────────────────────────────────────────┤
│ • Delegate to root-cause-analyst agent                   │
│ • Input: Bug description, error logs, stack traces       │
│ • Output: Initial hypothesis pool (unlimited)            │
│ • Store: write_memory("hypothesis_pool", pool)           │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 3. HYPOTHESIS VALIDATION & RANKING                       │
├──────────────────────────────────────────────────────────┤
│ For each hypothesis:                                     │
│   • Validate structure (FR1.1)                           │
│   • Check testability (FR1.2)                            │
│   • Use sequential-thinking MCP for ranking (FR1.3)      │
│     - Factors: probability, impact, test complexity      │
│   • Limit to top 5 (FR1.4)                               │
│ Store: write_memory("ranked_hypotheses", top5)           │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 4. PARALLELIZATION DECISION                              │
├──────────────────────────────────────────────────────────┤
│ • Estimate test time per hypothesis (FR3.3)              │
│ • IF any test >= 60s AND count > 1:                      │
│   ├─▶ Parallelize (create worktrees)                     │
│ • ELSE:                                                  │
│   └─▶ Sequential execution (single worktree)             │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 5. WORKTREE CREATION (FR2.1, FR2.2)                     │
├──────────────────────────────────────────────────────────┤
│ For each hypothesis (parallel branch):                   │
│   • setup-worktree.sh hyp-1 hyp-2 hyp-3 hyp-4 hyp-5      │
│   • Copy test scripts to each worktree                   │
│   • Setup isolated test environment                      │
│ Store: write_memory("worktrees", worktree_paths)         │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 6. PARALLEL TEST EXECUTION (FR3.1, FR3.2)               │
├──────────────────────────────────────────────────────────┤
│ • Launch test_hypothesis.py in each worktree             │
│ • Monitor progress with timeout enforcement              │
│ • Capture:                                               │
│   - stdout/stderr                                        │
│   - Test results (PASS/FAIL/TIMEOUT)                     │
│   - Performance metrics                                  │
│   - Coverage data (if available)                         │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 7. RESULTS AGGREGATION (FR3.4)                          │
├──────────────────────────────────────────────────────────┤
│ For each hypothesis:                                     │
│   • Classify result:                                     │
│     - FALSIFIED (test passed without bug)                │
│     - SUPPORTED (test reproduced bug)                    │
│     - INCONCLUSIVE (timeout/error/partial)               │
│   • Calculate confidence score                           │
│ Store: write_memory("test_results", results)             │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 8. ANALYSIS & NEXT ACTION (FR4.1, FR4.2)                │
├──────────────────────────────────────────────────────────┤
│ • Generate falsification report                          │
│ • Determine next action:                                 │
│   - IF 1 hypothesis SUPPORTED: Focus on fix              │
│   - IF >1 SUPPORTED: Refine hypotheses                   │
│   - IF all FALSIFIED: Generate new hypotheses (→ RCA)    │
│   - IF mix: Investigate inconclusive cases               │
│ • Store session state: write_memory("session_summary")   │
└──────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 9. CLEANUP (FR2.3)                                       │
├──────────────────────────────────────────────────────────┤
│ • Delete worktrees: cleanup-worktrees.sh hyp-*           │
│ • Archive test artifacts                                 │
│ • Update memory with final state                         │
└──────────────────────────────────────────────────────────┘
    │
    ▼
SESSION END OR ITERATE
```

---

## 3. File Structure

### 3.1 Agent Definition

```
~/.claude/agents/falsification-debugger.md
```

**Purpose**: Agent behavioral definition and integration points

### 3.2 Python Scripts

```
~/klauspython/parallel-orchestrator/scripts/
├── falsification/
│   ├── __init__.py
│   ├── hypothesis_manager.py      # FR1: Hypothesis Management
│   ├── worktree_orchestrator.py   # FR2: Worktree Orchestration
│   ├── test_executor.py           # FR3: Test Execution
│   ├── results_analyzer.py        # FR4: Results Analysis
│   ├── config.py                  # Configuration dataclasses
│   └── utils.py                   # Shared utilities
├── test_hypothesis.py             # Main entry point
└── cleanup-worktrees.sh           # Worktree cleanup script
```

### 3.3 Configuration Files

```
~/klauspython/parallel-orchestrator/config/
└── falsification_config.yaml
```

---

## 4. Key Functions and Signatures

### 4.1 hypothesis_manager.py

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

class HypothesisStatus(Enum):
    PENDING = "pending"
    TESTING = "testing"
    FALSIFIED = "falsified"
    SUPPORTED = "supported"
    INCONCLUSIVE = "inconclusive"

@dataclass
class Hypothesis:
    """Represents a single bug hypothesis"""
    id: str                          # Unique identifier
    description: str                 # Human-readable description
    test_strategy: str               # How to test this hypothesis
    expected_behavior: str           # What should happen if false
    estimated_test_time: float       # Seconds
    probability: float               # 0.0-1.0 initial likelihood
    impact: float                    # 0.0-1.0 severity if true
    test_complexity: float           # 0.0-1.0 difficulty to test
    status: HypothesisStatus
    test_results: Optional[Dict] = None
    confidence_score: Optional[float] = None

class HypothesisManager:
    """Manages hypothesis lifecycle and ranking (FR1)"""

    def __init__(self, max_hypotheses: int = 5):
        self.max_hypotheses = max_hypotheses
        self.pool: List[Hypothesis] = []

    def accept_hypothesis(self, hypothesis: Hypothesis) -> bool:
        """
        Accept a new hypothesis into the pool (FR1.1)

        Returns:
            True if accepted, False if rejected (validation failed)
        """
        pass

    def validate_hypothesis(self, hypothesis: Hypothesis) -> bool:
        """
        Validate hypothesis structure and testability (FR1.2)

        Checks:
            - Required fields present
            - Test strategy is concrete
            - Expected behavior is measurable
            - Estimated test time > 0
        """
        pass

    def rank_hypotheses(self, sequential_thinking_mcp) -> List[Hypothesis]:
        """
        Rank hypotheses using sequential-thinking MCP (FR1.3)

        Ranking criteria:
            - Probability of being root cause
            - Impact if true (severity)
            - Test complexity (prefer simpler tests)

        Formula: score = (probability * 0.5) + (impact * 0.3) - (complexity * 0.2)

        Returns:
            Sorted list (highest score first)
        """
        pass

    def limit_to_top_k(self, k: int = 5) -> List[Hypothesis]:
        """
        Limit pool to top K hypotheses (FR1.4)

        Default: k=5 (configurable)
        """
        pass

    def update_status(self, hypothesis_id: str, status: HypothesisStatus,
                     results: Optional[Dict] = None) -> None:
        """Update hypothesis status after test execution"""
        pass

    def get_next_for_testing(self) -> Optional[Hypothesis]:
        """Get next untested hypothesis in priority order"""
        pass
```

### 4.2 worktree_orchestrator.py

```python
from typing import List, Dict
from pathlib import Path

@dataclass
class WorktreeConfig:
    """Configuration for worktree creation"""
    base_repo: Path
    worktree_dir: Path
    branch_prefix: str = "hyp"
    max_concurrent: int = 5

class WorktreeOrchestrator:
    """Manages git worktrees for parallel testing (FR2)"""

    def __init__(self, config: WorktreeConfig):
        self.config = config
        self.active_worktrees: Dict[str, Path] = {}

    def create_worktrees(self, hypotheses: List[Hypothesis]) -> Dict[str, Path]:
        """
        Create isolated worktrees for each hypothesis (FR2.1)

        Uses: ~/klauspython/parallel-orchestrator/scripts/setup-worktree.sh

        Args:
            hypotheses: List of hypotheses to test

        Returns:
            Mapping of hypothesis_id -> worktree_path
        """
        pass

    def setup_test_environment(self, worktree_path: Path,
                              hypothesis: Hypothesis) -> bool:
        """
        Setup test environment in worktree (FR2.2)

        Steps:
            1. Copy test scripts
            2. Install dependencies (if needed)
            3. Create test configuration
            4. Initialize logging

        Returns:
            True if setup successful
        """
        pass

    def cleanup_worktrees(self, hypothesis_ids: List[str]) -> None:
        """
        Remove worktrees after testing (FR2.3)

        Uses: cleanup-worktrees.sh

        Args:
            hypothesis_ids: List of hypothesis IDs to clean up
        """
        pass

    def get_worktree_path(self, hypothesis_id: str) -> Optional[Path]:
        """Get worktree path for hypothesis"""
        pass

    def list_active_worktrees(self) -> List[str]:
        """List all active worktree branches"""
        pass
```

### 4.3 test_executor.py

```python
import asyncio
from typing import Dict, Optional
from enum import Enum

class TestResult(Enum):
    PASS = "pass"           # Test passed (hypothesis falsified)
    FAIL = "fail"           # Test failed (hypothesis supported)
    TIMEOUT = "timeout"     # Test exceeded time limit
    ERROR = "error"         # Test crashed/error

@dataclass
class TestExecutionResult:
    """Results from a single hypothesis test"""
    hypothesis_id: str
    result: TestResult
    duration: float                    # Seconds
    stdout: str
    stderr: str
    exit_code: int
    metrics: Dict[str, float]          # Performance metrics
    confidence_score: float            # 0.0-1.0

class TestExecutor:
    """Executes tests in parallel worktrees (FR3)"""

    def __init__(self, timeout_seconds: int = 300,
                 min_parallel_time: int = 60):
        self.timeout_seconds = timeout_seconds
        self.min_parallel_time = min_parallel_time

    async def execute_parallel(self,
                              hypotheses: List[Hypothesis],
                              worktrees: Dict[str, Path]) -> List[TestExecutionResult]:
        """
        Execute tests in parallel across worktrees (FR3.1)

        Args:
            hypotheses: List of hypotheses to test
            worktrees: Mapping of hypothesis_id -> worktree_path

        Returns:
            List of test results
        """
        pass

    async def execute_single(self, hypothesis: Hypothesis,
                           worktree: Path) -> TestExecutionResult:
        """
        Execute test for single hypothesis with timeout (FR3.2)

        Enforces timeout (FR3.3)
        """
        pass

    def should_parallelize(self, hypotheses: List[Hypothesis]) -> bool:
        """
        Determine if parallelization is worth overhead (FR3.3)

        Rules:
            - At least one hypothesis has test_time >= min_parallel_time
            - Multiple hypotheses to test
            - Sufficient system resources

        Returns:
            True if should parallelize
        """
        pass

    def classify_result(self, result: TestExecutionResult) -> HypothesisStatus:
        """
        Classify test result into hypothesis status (FR3.4)

        Logic:
            - PASS + exit_code=0 → FALSIFIED (hypothesis eliminated)
            - FAIL + exit_code!=0 → SUPPORTED (hypothesis likely)
            - TIMEOUT → INCONCLUSIVE
            - ERROR → INCONCLUSIVE
        """
        pass

    def calculate_confidence(self, result: TestExecutionResult) -> float:
        """
        Calculate confidence score for result (FR3.4)

        Factors:
            - Test completion (100% = higher confidence)
            - Consistency of results
            - Coverage metrics (if available)

        Returns:
            Confidence score 0.0-1.0
        """
        pass
```

### 4.4 results_analyzer.py

```python
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class FalsificationReport:
    """Final report after hypothesis testing"""
    session_id: str
    bug_description: str
    total_hypotheses: int
    falsified: List[Hypothesis]
    supported: List[Hypothesis]
    inconclusive: List[Hypothesis]
    recommended_action: str
    next_steps: List[str]
    confidence: float

class ResultsAnalyzer:
    """Analyzes test results and generates reports (FR4)"""

    def __init__(self):
        self.results: List[TestExecutionResult] = []

    def generate_report(self, hypotheses: List[Hypothesis],
                       results: List[TestExecutionResult]) -> FalsificationReport:
        """
        Generate falsification report (FR4.1)

        Report includes:
            - Summary of falsified/supported/inconclusive
            - Confidence scores
            - Recommended next action
            - Test artifacts and logs
        """
        pass

    def determine_next_action(self, report: FalsificationReport) -> str:
        """
        Determine recommended next action (FR4.2)

        Decision tree:
            - 1 supported, rest falsified → "Focus on implementing fix"
            - >1 supported → "Refine hypotheses to isolate root cause"
            - All falsified → "Generate new hypotheses (RCA)"
            - Mix with inconclusive → "Investigate inconclusive cases"
        """
        pass

    def persist_session(self, report: FalsificationReport,
                       memory_mcp) -> None:
        """
        Save session state to memory MCP (FR4.3)

        Stores:
            - Hypothesis pool
            - Test results
            - Report summary
            - Next action
        """
        pass

    def resume_session(self, session_id: str,
                      memory_mcp) -> Optional[FalsificationReport]:
        """
        Resume previous session from memory (FR4.3)
        """
        pass
```

### 4.5 Main Entry Point: test_hypothesis.py

```python
#!/usr/bin/env python3
"""
Main entry point for falsification debugging workflow
"""

import argparse
import asyncio
from pathlib import Path
from typing import List

from falsification.hypothesis_manager import HypothesisManager, Hypothesis
from falsification.worktree_orchestrator import WorktreeOrchestrator, WorktreeConfig
from falsification.test_executor import TestExecutor
from falsification.results_analyzer import ResultsAnalyzer, FalsificationReport
from falsification.config import FalsificationConfig

async def main():
    parser = argparse.ArgumentParser(
        description="Falsification-based debugging with parallel testing"
    )
    parser.add_argument("--session-id", help="Resume existing session")
    parser.add_argument("--bug-description", help="Bug description")
    parser.add_argument("--hypotheses-file", help="JSON file with hypotheses")
    parser.add_argument("--max-hypotheses", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-parallel", action="store_true",
                       help="Force sequential execution")

    args = parser.parse_args()

    # Initialize components
    config = FalsificationConfig.from_yaml("config/falsification_config.yaml")

    hypothesis_manager = HypothesisManager(max_hypotheses=args.max_hypotheses)
    worktree_orchestrator = WorktreeOrchestrator(WorktreeConfig(
        base_repo=Path.cwd(),
        worktree_dir=Path.cwd().parent / "worktrees"
    ))
    test_executor = TestExecutor(timeout_seconds=args.timeout)
    results_analyzer = ResultsAnalyzer()

    # Load or generate hypotheses
    if args.hypotheses_file:
        hypotheses = load_hypotheses_from_file(args.hypotheses_file)
    else:
        # Delegate to root-cause-analyst
        print("Delegating hypothesis generation to root-cause-analyst...")
        hypotheses = await generate_hypotheses_with_rca(args.bug_description)

    # Accept and rank hypotheses
    for hyp in hypotheses:
        hypothesis_manager.accept_hypothesis(hyp)

    ranked = hypothesis_manager.rank_hypotheses(sequential_thinking_mcp=None)
    top_k = hypothesis_manager.limit_to_top_k(k=args.max_hypotheses)

    print(f"Testing top {len(top_k)} hypotheses:")
    for i, hyp in enumerate(top_k, 1):
        print(f"  {i}. {hyp.description} (score: {hyp.probability:.2f})")

    # Create worktrees
    worktrees = worktree_orchestrator.create_worktrees(top_k)

    for hyp_id, path in worktrees.items():
        hyp = next(h for h in top_k if h.id == hyp_id)
        worktree_orchestrator.setup_test_environment(path, hyp)

    # Execute tests
    if args.no_parallel or not test_executor.should_parallelize(top_k):
        print("Executing tests sequentially...")
        results = []
        for hyp in top_k:
            result = await test_executor.execute_single(
                hyp, worktrees[hyp.id]
            )
            results.append(result)
    else:
        print("Executing tests in parallel...")
        results = await test_executor.execute_parallel(top_k, worktrees)

    # Analyze results
    report = results_analyzer.generate_report(top_k, results)

    print("\n" + "="*60)
    print("FALSIFICATION REPORT")
    print("="*60)
    print(f"Falsified:     {len(report.falsified)} hypotheses")
    print(f"Supported:     {len(report.supported)} hypotheses")
    print(f"Inconclusive:  {len(report.inconclusive)} hypotheses")
    print(f"\nRecommended Action: {report.recommended_action}")
    print("\nNext Steps:")
    for step in report.next_steps:
        print(f"  - {step}")

    # Persist session
    results_analyzer.persist_session(report, memory_mcp=None)

    # Cleanup
    worktree_orchestrator.cleanup_worktrees(list(worktrees.keys()))

    return report

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5. Configuration Schema

### 5.1 falsification_config.yaml

```yaml
# Falsification Debugger Configuration

hypothesis_management:
  max_concurrent: 5           # Maximum hypotheses to test simultaneously
  ranking_weights:
    probability: 0.5          # Weight for likelihood score
    impact: 0.3               # Weight for severity score
    complexity: -0.2          # Weight for test complexity (negative = prefer simple)

  validation_rules:
    require_test_strategy: true
    require_expected_behavior: true
    min_test_time: 1.0        # Minimum seconds for valid test

worktree_orchestration:
  base_dir: "../worktrees"    # Relative to project root
  branch_prefix: "hyp"        # Branches: hyp-1, hyp-2, ...
  auto_cleanup: true          # Cleanup after testing
  preserve_on_error: true     # Keep worktrees if tests fail

test_execution:
  default_timeout: 300        # Seconds (5 minutes)
  min_parallel_time: 60       # Only parallelize if test >= 60s
  capture_stdout: true
  capture_stderr: true
  collect_metrics: true

  overhead:
    worktree_creation: 8.0    # Seconds
    environment_setup: 5.0    # Seconds
    cleanup: 3.0              # Seconds

results_analysis:
  confidence_threshold: 0.7   # Minimum confidence for definitive result
  session_persistence: true   # Use memory MCP
  report_format: "markdown"   # markdown | json | text

  classification_rules:
    falsified:
      exit_code: 0
      min_confidence: 0.7
    supported:
      exit_code: [1, 2]       # Non-zero indicates bug reproduced
      min_confidence: 0.7
    inconclusive:
      conditions:
        - timeout
        - error
        - confidence < 0.7

integration:
  root_cause_analyst:
    enabled: true
    agent_path: "~/.claude/agents/root-cause-analyst.md"

  parallel_orchestrator:
    enabled: true
    scripts_path: "~/klauspython/parallel-orchestrator/scripts"

  memory_mcp:
    enabled: true
    session_prefix: "falsification"

  sequential_thinking_mcp:
    enabled: true
    use_for_ranking: true

  quality_engineer:
    enabled: true
    validate_tests: true
```

---

## 6. Integration Protocol with Other Agents

### 6.1 Integration with root-cause-analyst

**Purpose**: Generate initial hypothesis pool

**Protocol**:
```python
# falsification-debugger invokes RCA
async def generate_hypotheses_with_rca(bug_description: str) -> List[Hypothesis]:
    """
    Delegate hypothesis generation to root-cause-analyst

    Input:
        - Bug description
        - Error logs
        - Stack traces
        - Reproduction steps

    Output:
        - List[Hypothesis] (unlimited)

    Communication:
        - Use MCP or direct agent invocation
        - RCA returns structured hypothesis objects
    """
    # Implementation using agent delegation
    pass
```

**Data Contract**:
```json
{
  "request": {
    "agent": "root-cause-analyst",
    "command": "/rca:analyze",
    "input": {
      "bug_description": "...",
      "error_logs": "...",
      "stack_traces": "..."
    }
  },
  "response": {
    "hypotheses": [
      {
        "id": "hyp-001",
        "description": "Race condition in auth middleware",
        "test_strategy": "Run concurrent login tests",
        "expected_behavior": "All logins succeed without conflicts",
        "probability": 0.75,
        "impact": 0.9,
        "test_complexity": 0.6
      }
    ]
  }
}
```

### 6.2 Integration with parallel-orchestrator

**Purpose**: Leverage existing worktree infrastructure

**Protocol**:
```bash
# Use existing scripts
~/klauspython/parallel-orchestrator/scripts/setup-worktree.sh hyp-1 hyp-2 hyp-3

# Worktree orchestrator wraps these scripts
worktree_orchestrator.create_worktrees(hypotheses)
```

**Shared Resources**:
- `setup-worktree.sh` - Worktree creation
- `cleanup-worktrees.sh` - Worktree removal (to be created)
- Overhead configuration (reuse from parallel-orchestrator)

### 6.3 Integration with memory MCP

**Purpose**: Session persistence and state management

**Protocol**:
```python
# Save session state
memory_mcp.write_memory(
    key="falsification_session_001",
    value={
        "bug_description": "...",
        "hypotheses": [...],
        "results": [...],
        "next_action": "..."
    }
)

# Resume session
session_data = memory_mcp.read_memory("falsification_session_001")
```

**Memory Keys**:
- `falsification_session_{id}` - Full session state
- `falsification_hypotheses_{id}` - Hypothesis pool
- `falsification_results_{id}` - Test results
- `falsification_report_{id}` - Final report

### 6.4 Integration with sequential-thinking MCP

**Purpose**: Structured reasoning for hypothesis ranking

**Protocol**:
```python
# Use sequential-thinking for ranking logic
ranking_prompt = f"""
Rank these hypotheses for debugging priority:
{json.dumps(hypotheses, indent=2)}

Criteria:
1. Probability of being root cause (0.0-1.0)
2. Impact if true (severity 0.0-1.0)
3. Test complexity (0.0-1.0, lower is better)

Formula: score = (probability * 0.5) + (impact * 0.3) - (complexity * 0.2)

Return ranked list with scores.
"""

ranked = await sequential_thinking_mcp.think(ranking_prompt)
```

### 6.5 Integration with quality-engineer

**Purpose**: Validate test quality and coverage

**Protocol**:
```python
# After test execution, validate with quality-engineer
for result in test_results:
    quality_report = await quality_engineer.validate_test(
        test_file=result.test_file,
        coverage_data=result.coverage,
        assertions=result.assertions
    )

    if quality_report.quality_score < 0.7:
        result.status = HypothesisStatus.INCONCLUSIVE
        result.notes = "Low test quality, results uncertain"
```

---

## 7. Usage Examples

### Example 1: New Debugging Session

```bash
# User provides bug description
User: "The API returns 500 errors randomly under load"

# falsification-debugger activates
/falsify "API returns 500 errors randomly under load"

# Agent workflow:
1. Delegate to root-cause-analyst
   → Generates 8 hypotheses

2. Validate and rank
   → Top 5 selected:
     1. Database connection pool exhaustion (0.85)
     2. Race condition in cache layer (0.78)
     3. Memory leak in request handler (0.72)
     4. Timeout in external API calls (0.65)
     5. Incorrect error handling in middleware (0.58)

3. Create worktrees
   → hyp-1, hyp-2, hyp-3, hyp-4, hyp-5

4. Execute tests in parallel (estimated 3 min each)
   → Parallel execution: ~3.5 min total vs ~15 min sequential

5. Results:
   - FALSIFIED: hyp-3, hyp-4, hyp-5
   - SUPPORTED: hyp-1 (confidence 0.92)
   - SUPPORTED: hyp-2 (confidence 0.73)

6. Report:
   Recommended Action: "Refine hypotheses - investigate hyp-1 and hyp-2"
   Next Steps:
     - Create test to isolate DB connection vs cache race
     - Monitor connection pool metrics under load
     - Add logging to cache access patterns
```

### Example 2: Resume Session

```bash
# Resume previous session
/falsify --resume session_001

# Agent loads from memory:
- Previous hypotheses
- Test results
- Last action

# Continue investigation with refined hypotheses
```

---

## 8. Performance Characteristics

### Time Complexity

| Operation | Sequential | Parallel | Speedup |
|-----------|-----------|----------|---------|
| 5 hypotheses @ 60s each | 300s (5 min) | ~75s (1.25 min) | 4x |
| 5 hypotheses @ 180s each | 900s (15 min) | ~195s (3.25 min) | 4.6x |
| 3 hypotheses @ 30s each | 90s (1.5 min) | 90s (sequential better) | 1x |

### Resource Usage

- **Disk**: ~50MB per worktree (depends on repo size)
- **Memory**: ~200MB per test process
- **CPU**: Scales with number of hypotheses (up to 5 concurrent)

### Overhead Breakdown

```
Total Overhead = Worktree_Creation + Setup + Testing + Cleanup

For 5 hypotheses:
  Worktree Creation: 5 × 8s = 40s
  Environment Setup: 5 × 5s = 25s
  Testing: max(test_times) = ~60-180s
  Cleanup: 5 × 3s = 15s

  Overhead: 80s (40+25+15)
  Break-even: Test time > 20s per hypothesis
```

---

## 9. Error Handling and Edge Cases

### Edge Case 1: All Hypotheses Falsified

```python
if len(report.supported) == 0:
    next_action = "All hypotheses falsified - generate new hypotheses"
    # Delegate back to root-cause-analyst with refined context
    new_hypotheses = await rca.refine_hypotheses(
        bug_description=original_bug,
        falsified_hypotheses=report.falsified,
        additional_context=test_logs
    )
```

### Edge Case 2: Timeout on All Tests

```python
if all(r.result == TestResult.TIMEOUT for r in results):
    next_action = "All tests timed out - increase timeout or simplify tests"
    # Adjust timeout and retry
    test_executor.timeout_seconds *= 2
```

### Edge Case 3: Worktree Creation Failure

```python
try:
    worktrees = worktree_orchestrator.create_worktrees(hypotheses)
except WorktreeCreationError as e:
    # Fallback to sequential execution
    logger.warning(f"Worktree creation failed: {e}. Falling back to sequential.")
    worktrees = {"main": Path.cwd()}  # Use main repo
```

### Edge Case 4: Single Hypothesis

```python
if len(hypotheses) == 1:
    # Skip parallelization overhead
    result = await test_executor.execute_single(hypotheses[0], Path.cwd())
```

---

## 10. Future Enhancements

### Phase 2 Features
- **Adaptive Testing**: Dynamically adjust test strategies based on results
- **Hypothesis Refinement**: Auto-generate sub-hypotheses from supported ones
- **Coverage-Guided Testing**: Use coverage data to prioritize hypotheses
- **Machine Learning**: Learn from historical falsification patterns

### Phase 3 Features
- **Distributed Execution**: Run tests across multiple machines
- **Real-time Monitoring**: Live dashboard of test progress
- **Integration with CI/CD**: Automated falsification in pipelines
- **Hypothesis Templates**: Pre-built templates for common bug patterns

---

## 11. Success Metrics

### Key Performance Indicators (KPIs)

1. **Time to Root Cause**: Average time from bug report to root cause identification
   - Target: < 30 minutes for 80% of bugs

2. **Hypothesis Accuracy**: % of top-ranked hypotheses that are supported
   - Target: > 70% accuracy for top-1 hypothesis

3. **Parallelization Efficiency**: Actual speedup vs theoretical
   - Target: > 75% of theoretical speedup

4. **False Positive Rate**: % of falsified hypotheses that were actually root cause
   - Target: < 5%

5. **Session Completion Rate**: % of sessions that reach definitive conclusion
   - Target: > 85%

---

## Summary

This architecture provides:

1. **Systematic falsification** through parallel hypothesis testing
2. **Efficient resource usage** with overhead-aware parallelization
3. **Seamless integration** with existing parallel-orchestrator infrastructure
4. **Session persistence** via memory MCP
5. **Agent collaboration** (RCA, quality-engineer, sequential-thinking)
6. **Production-ready** error handling and edge case management

The design prioritizes:
- **Evidence-based debugging** over speculation
- **Parallelization** when overhead is justified
- **Integration** with existing tools and agents
- **Flexibility** for future enhancements
