#!/usr/bin/env python3
"""
Falsification Debugger - Main Entry Point

Systematically eliminate bug hypotheses through parallel falsification testing
using git worktrees. Based on Karl Popper's falsification principle.

Usage:
    python test_hypothesis.py --hypotheses "H1,H2,H3" --test-cmd "pytest tests/"
    python test_hypothesis.py --from-file hypotheses.json --test-cmd "npm test"
    python test_hypothesis.py --status  # Check ongoing session
    python test_hypothesis.py --cleanup  # Remove stale worktrees
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum
import subprocess
import concurrent.futures
import threading

# Add parent directory to path for shared modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import logging module
try:
    from logs import OrchestratorLogger, HypothesisTestLog, LogLevel, OperationType
    HAS_LOGGING = True
except ImportError:
    HAS_LOGGING = False


class ResultType(Enum):
    """Classification of hypothesis test results."""
    FALSIFIED = "FALSIFIED"       # Test passed, bug still present - hypothesis eliminated
    SURVIVED = "SURVIVED"         # Test failed, bug disappeared - hypothesis likely correct
    INCONCLUSIVE = "INCONCLUSIVE" # Timeout, error, setup failure
    BLOCKED = "BLOCKED"           # Depends on other hypothesis
    PENDING = "PENDING"           # Not yet tested


@dataclass
class Hypothesis:
    """A falsifiable hypothesis about a bug's root cause."""
    id: str
    description: str
    falsification_test: str = ""      # How to disprove this
    expected_if_false: str = ""       # What we expect if hypothesis is wrong
    probability: float = 0.5          # Prior probability (0.0-1.0)
    complexity: str = "medium"        # simple, medium, complex
    dependencies: List[str] = field(default_factory=list)

    def is_falsifiable(self) -> bool:
        """Check if hypothesis can be empirically tested."""
        return bool(self.falsification_test or self.description)

    def ranking_score(self, weights: Dict[str, float]) -> float:
        """Calculate ranking score for prioritization."""
        complexity_map = {"simple": 1.0, "medium": 0.5, "complex": 0.2}
        return (
            self.probability * weights.get("probability", 0.5) +
            complexity_map.get(self.complexity, 0.5) * weights.get("complexity", -0.2)
        )


@dataclass
class TestResult:
    """Result of testing a single hypothesis."""
    hypothesis_id: str
    result: ResultType
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    worktree_path: str
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            **asdict(self),
            "result": self.result.value
        }


@dataclass
class FalsificationConfig:
    """Configuration for falsification debugging session."""
    # Hypothesis Management
    max_hypotheses: int = 5
    min_hypotheses: int = 2
    require_falsifiability: bool = True

    # Test Execution
    test_timeout: int = 300          # 5 minutes
    min_test_time_for_parallel: int = 60
    test_command: str = "pytest"

    # Ranking Weights
    probability_weight: float = 0.5
    impact_weight: float = 0.3
    complexity_weight: float = -0.2

    # Overhead Timings (seconds)
    worktree_creation_time: float = 8.0
    session_startup_time: float = 5.0
    cleanup_time: float = 3.0

    # Paths
    project_root: str = ""
    output_dir: str = ""


class WorktreeManager:
    """Manages git worktree lifecycle for parallel testing."""

    def __init__(self, project_root: Path, config: FalsificationConfig):
        self.project_root = project_root
        self.config = config
        self.worktrees: Dict[str, Path] = {}
        self._lock = threading.Lock()

    def create_worktree(self, hypothesis_id: str) -> Path:
        """Create an isolated worktree for testing a hypothesis."""
        worktree_name = f"debug-{hypothesis_id}-{int(time.time())}"
        worktree_path = self.project_root.parent / worktree_name

        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()

            # Create worktree
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-d", current_branch],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True
            )

            with self._lock:
                self.worktrees[hypothesis_id] = worktree_path

            return worktree_path

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create worktree for {hypothesis_id}: {e.stderr}")

    def cleanup_worktree(self, hypothesis_id: str) -> bool:
        """Remove a worktree after testing."""
        with self._lock:
            worktree_path = self.worktrees.get(hypothesis_id)

        if not worktree_path or not worktree_path.exists():
            return False

        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True
            )

            with self._lock:
                del self.worktrees[hypothesis_id]

            return True

        except subprocess.CalledProcessError:
            # Fallback: manual removal
            import shutil
            try:
                shutil.rmtree(worktree_path)
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.project_root,
                    capture_output=True
                )
                return True
            except Exception:
                return False

    def cleanup_all(self):
        """Remove all worktrees created in this session."""
        for hypothesis_id in list(self.worktrees.keys()):
            self.cleanup_worktree(hypothesis_id)


class TestExecutor:
    """Executes falsification tests in parallel across worktrees."""

    def __init__(self, config: FalsificationConfig, worktree_manager: WorktreeManager):
        self.config = config
        self.worktree_manager = worktree_manager
        self.results: Dict[str, TestResult] = {}

    def execute_test(self, hypothesis: Hypothesis) -> TestResult:
        """Execute a single falsification test in an isolated worktree."""
        start_time = time.time()
        worktree_path = None

        try:
            # Create isolated worktree
            worktree_path = self.worktree_manager.create_worktree(hypothesis.id)

            # Prepare test command
            test_cmd = hypothesis.falsification_test or self.config.test_command

            # Execute test with timeout
            result = subprocess.run(
                test_cmd,
                shell=True,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=self.config.test_timeout
            )

            duration = time.time() - start_time

            # Classify result based on exit code
            # FALSIFIED: test passed (exit 0) means hypothesis is wrong
            # SURVIVED: test failed (exit != 0) means hypothesis might be correct
            if result.returncode == 0:
                result_type = ResultType.FALSIFIED
            else:
                result_type = ResultType.SURVIVED

            return TestResult(
                hypothesis_id=hypothesis.id,
                result=result_type,
                exit_code=result.returncode,
                stdout=result.stdout[-2000:],  # Limit output size
                stderr=result.stderr[-2000:],
                duration_seconds=duration,
                worktree_path=str(worktree_path) if worktree_path else ""
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                hypothesis_id=hypothesis.id,
                result=ResultType.INCONCLUSIVE,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                worktree_path=str(worktree_path) if worktree_path else "",
                error_message=f"Test timed out after {self.config.test_timeout}s"
            )

        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                hypothesis_id=hypothesis.id,
                result=ResultType.INCONCLUSIVE,
                exit_code=-1,
                stdout="",
                stderr="",
                duration_seconds=duration,
                worktree_path=str(worktree_path) if worktree_path else "",
                error_message=str(e)
            )

        finally:
            # Cleanup worktree
            if worktree_path:
                self.worktree_manager.cleanup_worktree(hypothesis.id)

    def execute_parallel(self, hypotheses: List[Hypothesis]) -> List[TestResult]:
        """Execute all hypothesis tests in parallel."""
        results = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(hypotheses), self.config.max_hypotheses)
        ) as executor:
            future_to_hypothesis = {
                executor.submit(self.execute_test, h): h
                for h in hypotheses
            }

            for future in concurrent.futures.as_completed(future_to_hypothesis):
                hypothesis = future_to_hypothesis[future]
                try:
                    result = future.result()
                    results.append(result)
                    self.results[hypothesis.id] = result
                except Exception as e:
                    results.append(TestResult(
                        hypothesis_id=hypothesis.id,
                        result=ResultType.INCONCLUSIVE,
                        exit_code=-1,
                        stdout="",
                        stderr="",
                        duration_seconds=0,
                        worktree_path="",
                        error_message=str(e)
                    ))

        return results

    def execute_sequential(self, hypotheses: List[Hypothesis]) -> List[TestResult]:
        """Execute hypothesis tests sequentially (for quick tests)."""
        results = []
        for hypothesis in hypotheses:
            result = self.execute_test(hypothesis)
            results.append(result)
            self.results[hypothesis.id] = result
        return results


class ResultsAnalyzer:
    """Analyzes test results and generates recommendations."""

    def __init__(self, config: FalsificationConfig):
        self.config = config

    def analyze(self, hypotheses: List[Hypothesis], results: List[TestResult]) -> Dict[str, Any]:
        """Analyze results and determine next action."""
        results_by_id = {r.hypothesis_id: r for r in results}

        falsified = [h for h in hypotheses if results_by_id.get(h.id, TestResult(h.id, ResultType.PENDING, 0, "", "", 0, "")).result == ResultType.FALSIFIED]
        survived = [h for h in hypotheses if results_by_id.get(h.id, TestResult(h.id, ResultType.PENDING, 0, "", "", 0, "")).result == ResultType.SURVIVED]
        inconclusive = [h for h in hypotheses if results_by_id.get(h.id, TestResult(h.id, ResultType.PENDING, 0, "", "", 0, "")).result == ResultType.INCONCLUSIVE]

        # Calculate timing stats
        total_duration = sum(r.duration_seconds for r in results)
        max_duration = max((r.duration_seconds for r in results), default=0)

        # Determine next action
        if len(survived) == 1:
            next_action = "ROOT_CAUSE_FOUND"
            recommendation = f"Focus investigation on: {survived[0].description}"
        elif len(survived) > 1:
            next_action = "ITERATE"
            recommendation = f"Refine tests for {len(survived)} surviving hypotheses"
        elif len(inconclusive) > 0 and len(survived) == 0:
            next_action = "INVESTIGATE_INCONCLUSIVE"
            recommendation = f"Resolve {len(inconclusive)} inconclusive tests before continuing"
        else:
            next_action = "REGENERATE"
            recommendation = "All hypotheses falsified - generate new hypotheses with RCA"

        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_hypotheses": len(hypotheses),
                "falsified": len(falsified),
                "survived": len(survived),
                "inconclusive": len(inconclusive)
            },
            "timing": {
                "total_duration": total_duration,
                "max_duration": max_duration,
                "estimated_sequential": total_duration,
                "actual_parallel": max_duration + (len(hypotheses) * self.config.worktree_creation_time),
                "speedup": total_duration / max(max_duration, 1)
            },
            "next_action": next_action,
            "recommendation": recommendation,
            "surviving_hypotheses": [{"id": h.id, "description": h.description} for h in survived],
            "falsified_hypotheses": [{"id": h.id, "description": h.description} for h in falsified],
            "inconclusive_hypotheses": [{"id": h.id, "description": h.description, "error": results_by_id.get(h.id, TestResult(h.id, ResultType.PENDING, 0, "", "", 0, "")).error_message} for h in inconclusive],
            "detailed_results": [r.to_dict() for r in results]
        }

    def generate_report(self, analysis: Dict[str, Any], hypotheses: List[Hypothesis]) -> str:
        """Generate human-readable report."""
        lines = [
            "=" * 60,
            "FALSIFICATION DEBUGGING REPORT",
            "=" * 60,
            "",
            f"Session: {analysis['timestamp']}",
            f"Iteration: 1",
            "",
            "HYPOTHESES TESTED:",
            "-" * 60,
        ]

        # Result symbols
        symbols = {
            "FALSIFIED": "FALSIFIED",
            "SURVIVED": "SURVIVED",
            "INCONCLUSIVE": "INCONCLUSIVE",
            "PENDING": "PENDING"
        }

        # Build results table
        for result in analysis["detailed_results"]:
            h = next((h for h in hypotheses if h.id == result["hypothesis_id"]), None)
            if h:
                status = symbols.get(result["result"], "?")
                duration = f"{result['duration_seconds']:.1f}s"
                lines.append(f"  [{result['hypothesis_id']}] {h.description[:40]:<40} | {status:<12} | {duration}")

        lines.extend([
            "",
            "PARALLELIZATION STATS:",
            f"  Sequential time: {analysis['timing']['estimated_sequential']:.1f}s (estimated)",
            f"  Parallel time: {analysis['timing']['actual_parallel']:.1f}s (actual)",
            f"  Speedup: {analysis['timing']['speedup']:.1f}x",
            "",
            "NEXT STEPS:",
            f"  Action: {analysis['next_action']}",
            f"  Recommendation: {analysis['recommendation']}",
            "",
        ])

        if analysis["surviving_hypotheses"]:
            lines.append("SURVIVING HYPOTHESES (investigate further):")
            for h in analysis["surviving_hypotheses"]:
                lines.append(f"  - [{h['id']}] {h['description']}")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)


def parse_hypotheses(input_str: str) -> List[Hypothesis]:
    """Parse hypothesis input from string or file."""
    hypotheses = []

    # Check if it's a file path
    if os.path.isfile(input_str):
        with open(input_str) as f:
            data = json.load(f)
            for i, item in enumerate(data):
                if isinstance(item, str):
                    hypotheses.append(Hypothesis(id=f"H{i+1}", description=item))
                elif isinstance(item, dict):
                    hypotheses.append(Hypothesis(
                        id=item.get("id", f"H{i+1}"),
                        description=item.get("description", ""),
                        falsification_test=item.get("test", ""),
                        probability=item.get("probability", 0.5)
                    ))
    else:
        # Parse comma-separated or newline-separated hypotheses
        parts = [p.strip() for p in input_str.replace("\n", ",").split(",") if p.strip()]
        for i, part in enumerate(parts):
            hypotheses.append(Hypothesis(id=f"H{i+1}", description=part))

    return hypotheses


def main():
    parser = argparse.ArgumentParser(
        description="Falsification Debugger - Eliminate bug hypotheses through parallel testing"
    )
    parser.add_argument("--hypotheses", "-H", type=str, help="Comma-separated hypotheses or path to JSON file")
    parser.add_argument("--test-cmd", "-t", type=str, default="pytest", help="Test command to run")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout per test in seconds")
    parser.add_argument("--max-hypotheses", type=int, default=5, help="Maximum parallel hypotheses")
    parser.add_argument("--sequential", action="store_true", help="Force sequential execution")
    parser.add_argument("--output", "-o", type=str, help="Output report path")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--cleanup", action="store_true", help="Clean up stale worktrees")
    parser.add_argument("--status", action="store_true", help="Show status of ongoing session")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-log", action="store_true", help="Disable logging to files")

    args = parser.parse_args()

    # Get project root (current git repository)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        project_root = Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository")
        sys.exit(1)

    # Initialize logger
    logger = None
    if HAS_LOGGING and not args.no_log:
        logger = OrchestratorLogger(project_root)
        logger.log(LogLevel.INFO, OperationType.HYPOTHESIS_TEST,
                   "Starting hypothesis testing session")

    # Handle cleanup
    if args.cleanup:
        print("Cleaning up stale worktrees...")
        subprocess.run(["git", "worktree", "prune"], cwd=project_root)
        # Find and remove debug worktrees
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=project_root,
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if line.startswith("worktree ") and "debug-" in line:
                path = line.split(" ", 1)[1]
                print(f"  Removing: {path}")
                subprocess.run(["git", "worktree", "remove", "--force", path], cwd=project_root)
        print("Cleanup complete")
        sys.exit(0)

    # Handle status check
    if args.status:
        print("Checking for active debugging sessions...")
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=project_root,
            capture_output=True, text=True
        )
        debug_worktrees = [l for l in result.stdout.split("\n") if "debug-" in l]
        if debug_worktrees:
            print(f"Active worktrees: {len(debug_worktrees)}")
            for wt in debug_worktrees:
                print(f"  {wt}")
        else:
            print("No active debugging sessions")
        sys.exit(0)

    # Require hypotheses for testing
    if not args.hypotheses:
        print("Error: --hypotheses required")
        print("Usage: python test_hypothesis.py --hypotheses 'H1: desc, H2: desc' --test-cmd 'pytest'")
        sys.exit(1)

    # Parse hypotheses
    hypotheses = parse_hypotheses(args.hypotheses)
    if not hypotheses:
        print("Error: No valid hypotheses found")
        sys.exit(1)

    # Limit hypotheses
    if len(hypotheses) > args.max_hypotheses:
        print(f"Warning: Limiting to {args.max_hypotheses} hypotheses (from {len(hypotheses)})")
        hypotheses = hypotheses[:args.max_hypotheses]

    print(f"Testing {len(hypotheses)} hypotheses...")
    for h in hypotheses:
        print(f"  [{h.id}] {h.description}")
    print()

    # Configure
    config = FalsificationConfig(
        test_command=args.test_cmd,
        test_timeout=args.timeout,
        max_hypotheses=args.max_hypotheses,
        project_root=str(project_root)
    )

    # Initialize components
    worktree_manager = WorktreeManager(project_root, config)
    executor = TestExecutor(config, worktree_manager)
    analyzer = ResultsAnalyzer(config)

    try:
        # Execute tests
        if args.sequential or len(hypotheses) < config.min_hypotheses:
            print("Executing sequentially...")
            results = executor.execute_sequential(hypotheses)
        else:
            print(f"Executing in parallel ({len(hypotheses)} worktrees)...")
            results = executor.execute_parallel(hypotheses)

        # Analyze results
        analysis = analyzer.analyze(hypotheses, results)

        # Log the hypothesis test session
        if logger:
            timing = analysis.get("timing", {})
            falsified = [r for r in results if r.result_type == ResultType.FALSIFIED]
            survived = [r for r in results if r.result_type == ResultType.SURVIVED]
            inconclusive = [r for r in results if r.result_type == ResultType.INCONCLUSIVE]

            logger.log_hypothesis_test(HypothesisTestLog(
                session_id=logger.session_id,
                timestamp=datetime.now().isoformat(),
                hypotheses_tested=len(hypotheses),
                hypotheses_falsified=len(falsified),
                hypotheses_survived=len(survived),
                hypotheses_inconclusive=len(inconclusive),
                total_duration_seconds=timing.get("total_duration", 0),
                parallel_duration_seconds=timing.get("max_duration", 0),
                speedup_factor=timing.get("speedup", 1.0),
                next_action=analysis.get("next_action", "UNKNOWN"),
                recommendation=analysis.get("recommendation", ""),
                detailed_results=[r.to_dict() for r in results]
            ))

            # Save reports
            json_path, md_path = logger.save_reports()
            print(f"\n📊 Session logged: {logger.session_id}")
            print(f"   JSON: {json_path}")
            print(f"   Markdown: {md_path}")

        # Generate output
        if args.json:
            output = json.dumps(analysis, indent=2)
        else:
            output = analyzer.generate_report(analysis, hypotheses)

        # Write or print output
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Report written to: {args.output}")
        else:
            print(output)

        # Exit code based on result
        if analysis["next_action"] == "ROOT_CAUSE_FOUND":
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted - cleaning up worktrees...")
        worktree_manager.cleanup_all()
        sys.exit(130)

    except Exception as e:
        print(f"Error: {e}")
        worktree_manager.cleanup_all()
        sys.exit(1)


if __name__ == "__main__":
    main()
