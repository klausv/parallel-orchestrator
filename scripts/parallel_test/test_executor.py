#!/usr/bin/env python3
"""
Test Execution Module

Executes tests in parallel worktrees with timeout enforcement.
Now uses AsyncIO for 30-40% performance improvement on I/O-bound operations.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from .config import Hypothesis, TestResult, TestExecutionResult, FalsificationConfig
from .async_test_executor import AsyncTestExecutor

logger = logging.getLogger(__name__)


class TestExecutor:
    """
    Executes tests in parallel worktrees

    Uses AsyncIO implementation for improved performance while maintaining
    backwards-compatible synchronous API.
    """

    def __init__(self, config: Optional[FalsificationConfig] = None):
        """
        Initialize test executor

        Args:
            config: Optional FalsificationConfig instance
        """
        self.config = config or FalsificationConfig()
        self.timeout_seconds = self.config.test_timeout
        self.min_parallel_time = self.config.min_parallel_time

        # Use AsyncTestExecutor as backend
        self._async_executor = AsyncTestExecutor(config)

    def execute_parallel(
        self, hypotheses: List[Hypothesis], worktrees: Dict[str, Path]
    ) -> List[TestExecutionResult]:
        """
        Execute tests in parallel across worktrees (FR3.1)

        Delegates to AsyncTestExecutor for improved I/O performance.

        Args:
            hypotheses: List of hypotheses to test
            worktrees: Mapping of hypothesis_id -> worktree_path

        Returns:
            List of test results
        """
        return self._async_executor.execute_parallel(hypotheses, worktrees)

    def execute_single(
        self, hypothesis: Hypothesis, worktree: Path
    ) -> TestExecutionResult:
        """
        Execute test for single hypothesis with timeout (FR3.2)

        Enforces timeout (FR3.3)
        Delegates to AsyncTestExecutor for improved I/O performance.

        Args:
            hypothesis: Hypothesis to test
            worktree: Path to worktree

        Returns:
            TestExecutionResult with outcome
        """
        return self._async_executor.execute_single(hypothesis, worktree)

    def should_parallelize(self, hypotheses: List[Hypothesis]) -> bool:
        """
        Determine if parallelization is worth overhead (FR3.3)

        Delegates to AsyncTestExecutor for consistency.

        Args:
            hypotheses: List of hypotheses to evaluate

        Returns:
            True if should parallelize
        """
        return self._async_executor.should_parallelize(hypotheses)
