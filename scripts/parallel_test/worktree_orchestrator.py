#!/usr/bin/env python3
"""
Worktree Orchestration Module

Manages git worktree lifecycle for parallel hypothesis testing
"""

import logging
import shlex
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from .config import Hypothesis, FalsificationConfig
from .worktree_pool import WorktreePool

# Use shared infrastructure
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.git_utils import get_current_branch, create_worktree, remove_worktree

logger = logging.getLogger(__name__)


@dataclass
class WorktreeConfig:
    """Configuration for worktree creation"""
    base_repo: Path
    worktree_dir: Path
    branch_prefix: str = "hyp"
    max_concurrent: int = 5
    use_pool: bool = True  # Enable pooling by default for performance
    pool_size: int = 10  # Maximum worktrees in pool


class WorktreeOrchestrator:
    """
    Manages git worktrees for parallel testing.

    Supports two modes:
        1. Pooled mode (use_pool=True): Reuses worktrees across sessions (15x faster)
        2. Direct mode (use_pool=False): Creates/destroys worktrees each time (legacy)

    Performance comparison:
        - Pooled mode (first session): ~16s per worktree
        - Pooled mode (subsequent): ~0.5s per worktree (32x speedup)
        - Direct mode: ~16s per worktree (always)

    Supports context manager protocol for guaranteed cleanup:
        with WorktreeOrchestrator(config) as orchestrator:
            worktrees = orchestrator.create_worktrees(hypotheses)
            # ... run tests ...
        # Cleanup happens automatically
    """

    def __init__(
        self,
        config: WorktreeConfig,
        fals_config: Optional[FalsificationConfig] = None,
        use_pool: Optional[bool] = None
    ):
        """
        Initialize worktree orchestrator

        Args:
            config: WorktreeConfig instance
            fals_config: Optional FalsificationConfig for overhead calculations
            use_pool: Override config.use_pool setting (default: use config value)
        """
        self.config = config
        self.fals_config = fals_config or FalsificationConfig()
        self.active_worktrees: Dict[str, Path] = {}
        self._entered = False

        # Pooling configuration
        self.use_pool = use_pool if use_pool is not None else config.use_pool

        # Initialize pool if enabled
        self._pool: Optional[WorktreePool] = None
        if self.use_pool:
            pool_dir = config.worktree_dir / "pool"
            self._pool = WorktreePool(
                base_repo=config.base_repo,
                pool_dir=pool_dir,
                max_size=config.pool_size,
                auto_load=True
            )
            logger.info(f"Initialized worktree pool: {self._pool}")
        else:
            logger.info("Worktree pooling disabled - using direct mode")

    def __enter__(self):
        """Context manager entry - returns self for worktree operations"""
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - guarantees worktree cleanup"""
        if self.use_pool and self._pool:
            # Release all worktrees back to pool
            for hyp_id in list(self.active_worktrees.keys()):
                self._pool.release(hyp_id)
                logger.info(f"Released worktree for {hyp_id} back to pool")
            # Persist pool state for next session
            self._pool.persist_state()
        else:
            # Direct mode: cleanup worktrees completely
            self.cleanup_all()

        self._entered = False
        return False  # Don't suppress exceptions

    def create_worktrees(self, hypotheses: List[Hypothesis]) -> Dict[str, Path]:
        """
        Create isolated worktrees for each hypothesis (FR2.1)

        Uses pool if enabled (fast reuse) or creates directly (slower).

        Args:
            hypotheses: List of hypotheses to test

        Returns:
            Mapping of hypothesis_id -> worktree_path
        """
        worktrees = {}

        if self.use_pool and self._pool:
            # Pooled mode: acquire from pool (reuses existing worktrees)
            logger.info(f"Using pooled worktrees for {len(hypotheses)} hypotheses")

            for hyp in hypotheses:
                try:
                    worktree_path = self._pool.acquire(hyp.id)
                    self.active_worktrees[hyp.id] = worktree_path
                    worktrees[hyp.id] = worktree_path
                    logger.info(f"Acquired worktree for {hyp.id}: {worktree_path}")

                except RuntimeError as e:
                    logger.error(f"Pool exhausted for {hyp.id}: {e}")
                    # Fall back to direct creation
                    logger.warning("Falling back to direct worktree creation")
                    worktree_path = self._create_worktree_direct(hyp.id)
                    if worktree_path:
                        self.active_worktrees[hyp.id] = worktree_path
                        worktrees[hyp.id] = worktree_path

        else:
            # Direct mode: create new worktrees (legacy behavior)
            logger.info(f"Creating {len(hypotheses)} worktrees directly (pooling disabled)")

            for hyp in hypotheses:
                worktree_path = self._create_worktree_direct(hyp.id)
                if worktree_path:
                    self.active_worktrees[hyp.id] = worktree_path
                    worktrees[hyp.id] = worktree_path

        return worktrees

    def _create_worktree_direct(self, hypothesis_id: str) -> Optional[Path]:
        """
        Create a worktree directly without using the pool

        Args:
            hypothesis_id: ID of hypothesis

        Returns:
            Path to created worktree or None on failure
        """
        # Create worktree
        worktree_name = f"{self.config.branch_prefix}-{hypothesis_id}"
        worktree_path = self.config.worktree_dir / worktree_name

        try:
            # Use shared git_utils function
            create_worktree(self.config.base_repo, worktree_path)
            return worktree_path

        except Exception as e:
            logger.error(f"Failed to create worktree for {hypothesis_id}: {e}")
            return None

    def setup_test_environment(self, worktree_path: Path, hypothesis: Hypothesis) -> bool:
        """
        Setup test environment in worktree (FR2.2)

        Steps:
            1. Create test script
            2. Install dependencies (if needed)
            3. Create test configuration
            4. Initialize logging

        Args:
            worktree_path: Path to worktree
            hypothesis: Hypothesis being tested

        Returns:
            True if setup successful
        """
        try:
            # Create test directory if it doesn't exist
            test_dir = worktree_path / ".falsification"
            test_dir.mkdir(exist_ok=True)

            # Write hypothesis test script with proper shell escaping
            test_script = test_dir / f"test_{hypothesis.id}.sh"

            # Escape all user-provided strings for shell safety
            safe_id = shlex.quote(hypothesis.id)
            safe_description = shlex.quote(hypothesis.description)
            safe_strategy = shlex.quote(hypothesis.test_strategy)
            safe_expected = shlex.quote(hypothesis.expected_behavior)
            safe_worktree = shlex.quote(str(worktree_path))

            test_script_content = f"""#!/bin/bash
# Falsification test for hypothesis: {safe_id}
# Description: {safe_description}
# Test Strategy: {safe_strategy}

set -e

echo "Testing hypothesis:" {safe_id}
echo "Description:" {safe_description}
echo "Test Strategy:" {safe_strategy}
echo ""
echo "Expected Behavior:" {safe_expected}
echo ""

# Run the test command
cd {safe_worktree}
# NOTE: test_strategy is executed as a command - ensure it's trusted input
eval {safe_strategy}

# Exit code indicates test result
exit $?
"""
            test_script.write_text(test_script_content)
            test_script.chmod(0o755)
            logger.info(f"Created test script: {test_script}")

            # Create configuration file
            config_file = test_dir / f"config_{hypothesis.id}.json"
            config_content = f"""{{
  "hypothesis_id": "{hypothesis.id}",
  "description": "{hypothesis.description}",
  "test_strategy": "{hypothesis.test_strategy}",
  "expected_behavior": "{hypothesis.expected_behavior}",
  "estimated_test_time": {hypothesis.estimated_test_time},
  "probability": {hypothesis.probability},
  "impact": {hypothesis.impact},
  "test_complexity": {hypothesis.test_complexity}
}}
"""
            config_file.write_text(config_content)
            logger.info(f"Created config file: {config_file}")

            logger.info(f"Test environment setup complete for {hypothesis.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            return False

    def cleanup_worktrees(self, hypothesis_ids: List[str]) -> None:
        """
        Remove worktrees after testing (FR2.3)

        Behavior depends on mode:
            - Pooled: Releases worktrees back to pool (fast)
            - Direct: Removes worktrees completely (slow)

        Args:
            hypothesis_ids: List of hypothesis IDs to clean up
        """
        if self.use_pool and self._pool:
            # Pooled mode: release back to pool
            for hyp_id in hypothesis_ids:
                if hyp_id in self.active_worktrees:
                    self._pool.release(hyp_id)
                    del self.active_worktrees[hyp_id]
                    logger.info(f"Released worktree for {hyp_id} to pool")
        else:
            # Direct mode: remove worktrees
            for hyp_id in hypothesis_ids:
                worktree_path = self.active_worktrees.get(hyp_id)
                if not worktree_path:
                    logger.warning(f"Worktree not found for {hyp_id}")
                    continue

                # Use shared git_utils function (handles errors gracefully)
                remove_worktree(self.config.base_repo, worktree_path)
                del self.active_worktrees[hyp_id]

    def get_worktree_path(self, hypothesis_id: str) -> Optional[Path]:
        """
        Get worktree path for hypothesis

        Args:
            hypothesis_id: ID of hypothesis

        Returns:
            Path to worktree or None if not found
        """
        return self.active_worktrees.get(hypothesis_id)

    def list_active_worktrees(self) -> List[str]:
        """
        List all active worktree branches

        Returns:
            List of hypothesis IDs with active worktrees
        """
        return list(self.active_worktrees.keys())

    def cleanup_all(self) -> None:
        """Cleanup all active worktrees"""
        hyp_ids = list(self.active_worktrees.keys())
        self.cleanup_worktrees(hyp_ids)

    def get_pool_stats(self) -> Optional[Dict]:
        """
        Get worktree pool statistics (if pooling enabled)

        Returns:
            Dictionary with pool metrics or None if pooling disabled
        """
        if self.use_pool and self._pool:
            return self._pool.get_stats()
        return None

    def cleanup_pool(self) -> None:
        """
        Completely cleanup the worktree pool

        Warning: This removes ALL pooled worktrees permanently
        """
        if self.use_pool and self._pool:
            self._pool.cleanup_all()
            logger.info("Cleaned up entire worktree pool")
        else:
            logger.warning("Pooling not enabled, nothing to cleanup")

    def __del__(self):
        """
        Fallback cleanup on deletion.

        WARNING: __del__ is unreliable - prefer using context manager (with statement).
        This is only a safety net for cases where context manager wasn't used.
        """
        if self.active_worktrees and not self._entered:
            logger.warning("WorktreeOrchestrator not used as context manager - cleanup may be incomplete")
            try:
                if self.use_pool and self._pool:
                    # Release to pool
                    for hyp_id in list(self.active_worktrees.keys()):
                        self._pool.release(hyp_id)
                    self._pool.persist_state()
                else:
                    # Direct cleanup
                    self.cleanup_all()
            except Exception as e:
                logger.warning(f"Error during fallback cleanup: {e}")

    def __repr__(self) -> str:
        """String representation"""
        mode = "pooled" if self.use_pool else "direct"
        return f"WorktreeOrchestrator(active={len(self.active_worktrees)}, mode={mode})"
