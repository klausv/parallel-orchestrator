#!/usr/bin/env python3
"""
Git Operations Abstraction

Shared utilities for git worktree management and operations.
Extracted from worktree_orchestrator.py and task-splitter.py.
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class GitOperationError(Exception):
    """Raised when git operation fails"""
    pass


def get_current_branch(repo_path: Path) -> str:
    """
    Get the current branch name.

    Args:
        repo_path: Path to git repository

    Returns:
        Current branch name

    Raises:
        GitOperationError: If unable to get current branch
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        logger.debug(f"Current branch: {branch}")
        return branch
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get current branch: {e.stderr}")
        raise GitOperationError(f"Failed to get current branch: {e.stderr}") from e


def create_worktree(repo_path: Path, worktree_path: Path, branch: Optional[str] = None) -> Path:
    """
    Create a git worktree.

    Args:
        repo_path: Path to main repository
        worktree_path: Path where worktree should be created
        branch: Optional branch to checkout (default: current branch in detached mode)

    Returns:
        Path to created worktree

    Raises:
        GitOperationError: If worktree creation fails
    """
    # Ensure worktree parent directory exists
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Skip if already exists
    if worktree_path.exists():
        logger.warning(f"Worktree already exists: {worktree_path}, reusing")
        return worktree_path

    try:
        if branch:
            # Create worktree with specific branch
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
        else:
            # Create worktree in detached mode from current branch
            current_branch = get_current_branch(repo_path)
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-d", current_branch],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )

        logger.info(f"Created worktree: {worktree_path}")
        return worktree_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create worktree: {e.stderr}")
        raise GitOperationError(f"Failed to create worktree: {e.stderr}") from e


def remove_worktree(repo_path: Path, worktree_path: Path, force: bool = False) -> None:
    """
    Remove a git worktree.

    Args:
        repo_path: Path to main repository
        worktree_path: Path to worktree to remove
        force: Force removal even if worktree has uncommitted changes

    Raises:
        GitOperationError: If worktree removal fails (non-fatal, logs warning)
    """
    if not worktree_path.exists():
        logger.debug(f"Worktree does not exist: {worktree_path}")
        return

    try:
        cmd = ["git", "worktree", "remove", str(worktree_path)]
        if force:
            cmd.append("--force")

        subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Removed worktree: {worktree_path}")

    except subprocess.CalledProcessError as e:
        # Non-fatal - just log warning and continue
        logger.warning(f"Failed to remove worktree {worktree_path}: {e.stderr}")


def reset_worktree(worktree_path: Path) -> None:
    """
    Reset worktree to clean state (discard all changes).

    Equivalent to: git checkout HEAD -- . && git clean -fd

    Args:
        worktree_path: Path to worktree to reset

    Raises:
        GitOperationError: If reset fails
    """
    try:
        # Discard all changes
        subprocess.run(
            ["git", "checkout", "HEAD", "--", "."],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=True
        )

        # Remove untracked files
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=True
        )

        logger.info(f"Reset worktree: {worktree_path}")

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to reset worktree: {e.stderr}")
        raise GitOperationError(f"Failed to reset worktree: {e.stderr}") from e


def list_worktrees(repo_path: Path) -> List[Dict[str, str]]:
    """
    List all worktrees for repository.

    Args:
        repo_path: Path to git repository

    Returns:
        List of worktree info dicts with 'path', 'branch', 'commit' keys

    Raises:
        GitOperationError: If listing fails
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        worktrees = []
        current = {}

        for line in result.stdout.strip().split('\n'):
            if not line:
                if current:
                    worktrees.append(current)
                    current = {}
                continue

            if line.startswith('worktree '):
                current['path'] = line.split(' ', 1)[1]
            elif line.startswith('branch '):
                current['branch'] = line.split(' ', 1)[1]
            elif line.startswith('HEAD '):
                current['commit'] = line.split(' ', 1)[1]

        # Add last worktree if exists
        if current:
            worktrees.append(current)

        logger.debug(f"Found {len(worktrees)} worktrees")
        return worktrees

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to list worktrees: {e.stderr}")
        raise GitOperationError(f"Failed to list worktrees: {e.stderr}") from e


def count_worktrees(repo_path: Path) -> int:
    """
    Count number of worktrees (simpler version for resource checks).

    Args:
        repo_path: Path to git repository

    Returns:
        Number of worktrees (including main repo)
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )

        # Each line is one worktree
        count = len([line for line in result.stdout.strip().split('\n') if line])
        logger.debug(f"Worktree count: {count}")
        return count

    except subprocess.CalledProcessError:
        logger.warning("Failed to count worktrees, assuming 0")
        return 0


@contextmanager
def WorktreeContext(repo_path: Path, worktree_path: Path, branch: Optional[str] = None,
                    cleanup: bool = True):
    """
    Context manager for temporary worktrees with guaranteed cleanup.

    Usage:
        with WorktreeContext(repo, worktree_dir / "temp") as wt_path:
            # Use worktree
            ...
        # Cleanup happens automatically

    Args:
        repo_path: Path to main repository
        worktree_path: Path for worktree
        branch: Optional branch to checkout
        cleanup: Whether to cleanup on exit (default: True)

    Yields:
        Path to created worktree
    """
    worktree = None
    try:
        worktree = create_worktree(repo_path, worktree_path, branch)
        yield worktree
    finally:
        if cleanup and worktree and worktree.exists():
            remove_worktree(repo_path, worktree, force=True)
