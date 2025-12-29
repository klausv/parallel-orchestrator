#!/usr/bin/env python3
"""
Test Execution Module

Executes tests in parallel worktrees with timeout enforcement
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from .config import Hypothesis, TestResult, TestExecutionResult, HypothesisStatus, FalsificationConfig

logger = logging.getLogger(__name__)


class TestExecutor:
    """Executes tests in parallel worktrees"""

    def __init__(self, config: Optional[FalsificationConfig] = None):
        """
        Initialize test executor

        Args:
            config: Optional FalsificationConfig instance
        """
        self.config = config or FalsificationConfig()
        self.timeout_seconds = self.config.test_timeout
        self.min_parallel_time = self.config.min_parallel_time

    def execute_parallel(self,
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
        logger.info(f"Starting parallel execution of {len(hypotheses)} tests")

        results = []

        # Use ThreadPoolExecutor for parallel execution
        with ThreadPoolExecutor(max_workers=min(len(hypotheses), self.config.max_concurrent_tests)) as executor:
            futures = {
                executor.submit(self.execute_single, hyp, worktrees[hyp.id]): hyp
                for hyp in hypotheses
            }

            for future in futures:
                try:
                    result = future.result(timeout=self.timeout_seconds)
                    results.append(result)
                except FutureTimeoutError:
                    hyp = futures[future]
                    logger.warning(f"Execution timed out: {hyp.id}")
                    results.append(TestExecutionResult(
                        hypothesis_id=hyp.id,
                        result=TestResult.TIMEOUT,
                        duration=self.timeout_seconds,
                        error_message=f"Test exceeded {self.timeout_seconds}s timeout",
                        exit_code=124
                    ))
                except Exception as e:
                    hyp = futures[future]
                    logger.error(f"Test execution error for {hyp.id}: {e}")
                    results.append(TestExecutionResult(
                        hypothesis_id=hyp.id,
                        result=TestResult.ERROR,
                        duration=0.0,
                        error_message=str(e),
                        exit_code=1
                    ))

        logger.info(f"Completed parallel execution: {len(results)} results")
        return results

    def execute_single(self, hypothesis: Hypothesis,
                      worktree: Path) -> TestExecutionResult:
        """
        Execute test for single hypothesis with timeout (FR3.2)

        Enforces timeout (FR3.3)

        Args:
            hypothesis: Hypothesis to test
            worktree: Path to worktree

        Returns:
            TestExecutionResult with outcome
        """
        logger.info(f"Executing test for hypothesis: {hypothesis.id}")

        start_time = time.time()

        # Create test script path
        test_script = worktree / ".falsification" / f"test_{hypothesis.id}.sh"

        if not test_script.exists():
            logger.error(f"Test script not found: {test_script}")
            return TestExecutionResult(
                hypothesis_id=hypothesis.id,
                result=TestResult.ERROR,
                duration=time.time() - start_time,
                error_message=f"Test script not found: {test_script}",
                exit_code=1
            )

        try:
            import subprocess

            # Run test script with timeout via shell
            result = subprocess.run(
                [str(test_script)],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )

            duration = time.time() - start_time
            exit_code = result.returncode

            # Classify result
            result_type = self._classify_test_result(exit_code)
            confidence = self._calculate_confidence(result_type, duration)

            logger.info(f"Test {hypothesis.id} completed: {result_type.value} (exit_code={exit_code}, duration={duration:.1f}s)")

            return TestExecutionResult(
                hypothesis_id=hypothesis.id,
                result=result_type,
                duration=duration,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=exit_code,
                worktree_path=str(worktree),
                metrics={"confidence": confidence}
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.warning(f"Test timed out after {duration:.1f}s: {hypothesis.id}")
            return TestExecutionResult(
                hypothesis_id=hypothesis.id,
                result=TestResult.TIMEOUT,
                duration=duration,
                error_message=f"Test exceeded {self.timeout_seconds}s timeout",
                exit_code=124
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Test execution error for {hypothesis.id}: {e}")
            return TestExecutionResult(
                hypothesis_id=hypothesis.id,
                result=TestResult.ERROR,
                duration=duration,
                error_message=str(e),
                exit_code=1,
                worktree_path=str(worktree)
            )

    def should_parallelize(self, hypotheses: List[Hypothesis]) -> bool:
        """
        Determine if parallelization is worth overhead (FR3.3)

        Rules:
            - At least one hypothesis has test_time >= min_parallel_time
            - Multiple hypotheses to test
            - Sufficient system resources

        Args:
            hypotheses: List of hypotheses to evaluate

        Returns:
            True if should parallelize
        """
        if len(hypotheses) <= 1:
            logger.info("Not parallelizing: only 1 hypothesis")
            return False

        # Check if any test is long enough
        max_test_time = max((h.estimated_test_time for h in hypotheses), default=0)
        if max_test_time < self.min_parallel_time:
            logger.info(f"Not parallelizing: max test time ({max_test_time}s) < threshold ({self.min_parallel_time}s)")
            return False

        logger.info(f"Parallelizing: {len(hypotheses)} tests with max time {max_test_time}s")
        return True

    def _classify_test_result(self, exit_code: int) -> TestResult:
        """
        Classify test result (FR3.4)

        Logic:
            - exit_code=0 → PASS (hypothesis falsified)
            - exit_code!=0 → FAIL (hypothesis supported)
            - exit_code=124 → TIMEOUT (handled separately)

        Args:
            exit_code: Process exit code

        Returns:
            TestResult classification
        """
        if exit_code == 0:
            return TestResult.PASS
        else:
            return TestResult.FAIL

    def _calculate_confidence(self, result: TestResult, duration: float) -> float:
        """
        Calculate confidence score for result

        Factors:
            - Test completion (100% = higher confidence)
            - Duration (more stable = higher confidence)

        Args:
            result: TestResult classification
            duration: Test duration in seconds

        Returns:
            Confidence score 0.0-1.0
        """
        if result == TestResult.TIMEOUT:
            return 0.3  # Low confidence for timeout
        elif result == TestResult.ERROR:
            return 0.2  # Very low confidence for error
        else:
            # Full tests get higher confidence
            # Adjust down if very fast (might be skipped tests)
            if duration < 5:
                return 0.6
            else:
                return 0.85
