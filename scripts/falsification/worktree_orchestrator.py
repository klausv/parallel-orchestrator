#!/usr/bin/env python3
"""
Worktree Orchestration Module

Manages git worktree lifecycle for parallel hypothesis testing
"""

import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from .config import Hypothesis, FalsificationConfig

logger = logging.getLogger(__name__)


@dataclass
class WorktreeConfig:
    """Configuration for worktree creation"""
    base_repo: Path
    worktree_dir: Path
    branch_prefix: str = "hyp"
    max_concurrent: int = 5


class WorktreeOrchestrator:
    """Manages git worktrees for parallel testing"""

    def __init__(self, config: WorktreeConfig, fals_config: Optional[FalsificationConfig] = None):
        """
        Initialize worktree orchestrator

        Args:
            config: WorktreeConfig instance
            fals_config: Optional FalsificationConfig for overhead calculations
        """
        self.config = config
        self.fals_config = fals_config or FalsificationConfig()
        self.active_worktrees: Dict[str, Path] = {}

    def create_worktrees(self, hypotheses: List[Hypothesis]) -> Dict[str, Path]:
        """
        Create isolated worktrees for each hypothesis (FR2.1)

        Args:
            hypotheses: List of hypotheses to test

        Returns:
            Mapping of hypothesis_id -> worktree_path
        """
        worktrees = {}

        # Get current branch
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.config.base_repo,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
            logger.info(f"Creating worktrees from branch: {current_branch}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get current branch: {e}")
            raise

        # Ensure worktree directory exists
        self.config.worktree_dir.mkdir(parents=True, exist_ok=True)

        # Create worktree for each hypothesis
        for hyp in hypotheses:
            worktree_name = f"{self.config.branch_prefix}-{hyp.id}"
            worktree_path = self.config.worktree_dir / worktree_name

            # Skip if already exists
            if worktree_path.exists():
                logger.warning(f"Worktree already exists: {worktree_path}, reusing")
                self.active_worktrees[hyp.id] = worktree_path
                worktrees[hyp.id] = worktree_path
                continue

            try:
                # Create worktree
                subprocess.run(
                    ["git", "worktree", "add", str(worktree_path), "-d", current_branch],
                    cwd=self.config.base_repo,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Created worktree: {worktree_path}")
                self.active_worktrees[hyp.id] = worktree_path
                worktrees[hyp.id] = worktree_path

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create worktree for {hyp.id}: {e.stderr}")
                raise

        return worktrees

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

            # Write hypothesis test script
            test_script = test_dir / f"test_{hypothesis.id}.sh"
            test_script_content = f"""#!/bin/bash
# Falsification test for hypothesis: {hypothesis.id}
# Description: {hypothesis.description}
# Test Strategy: {hypothesis.test_strategy}

set -e

echo "Testing hypothesis: {hypothesis.id}"
echo "Description: {hypothesis.description}"
echo "Test Strategy: {hypothesis.test_strategy}"
echo ""
echo "Expected Behavior: {hypothesis.expected_behavior}"
echo ""

# Run the test command
cd {worktree_path}
{hypothesis.test_strategy}

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

        Args:
            hypothesis_ids: List of hypothesis IDs to clean up
        """
        for hyp_id in hypothesis_ids:
            worktree_path = self.active_worktrees.get(hyp_id)
            if not worktree_path:
                logger.warning(f"Worktree not found for {hyp_id}")
                continue

            try:
                # Remove worktree
                subprocess.run(
                    ["git", "worktree", "remove", str(worktree_path)],
                    cwd=self.config.base_repo,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"Removed worktree: {worktree_path}")
                del self.active_worktrees[hyp_id]

            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to remove worktree {worktree_path}: {e.stderr}")
                # Don't raise, continue cleanup

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

    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.cleanup_all()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    def __repr__(self) -> str:
        """String representation"""
        return f"WorktreeOrchestrator(active={len(self.active_worktrees)})"
