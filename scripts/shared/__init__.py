#!/usr/bin/env python3
"""
Shared Infrastructure Module

Common utilities for git operations, subprocess execution, and logging.
Used by both orchestrator and parallel_test systems.

Usage:
    from shared.git_utils import create_worktree, WorktreeContext
    from shared.subprocess_utils import run_command, CommandResult
    from shared.logging_utils import setup_logging, get_logger

Author: Extracted from parallel-orchestrator codebase
Date: 2025-12-30
"""

# Git utilities
from .git_utils import (
    get_current_branch,
    create_worktree,
    remove_worktree,
    reset_worktree,
    list_worktrees,
    count_worktrees,
    WorktreeContext,
    GitOperationError
)

# Subprocess utilities
from .subprocess_utils import (
    run_command,
    run_command_async,
    run_script,
    run_shell_script,
    CommandResult,
    CommandRunner
)

# Logging utilities
from .logging_utils import (
    setup_logging,
    get_logger,
    ProgressLogger,
    LogSection,
    log_exception,
    configure_third_party_loggers,
    Colors,
    ColoredFormatter
)

__all__ = [
    # Git
    'get_current_branch',
    'create_worktree',
    'remove_worktree',
    'reset_worktree',
    'list_worktrees',
    'count_worktrees',
    'WorktreeContext',
    'GitOperationError',

    # Subprocess
    'run_command',
    'run_command_async',
    'run_script',
    'run_shell_script',
    'CommandResult',
    'CommandRunner',

    # Logging
    'setup_logging',
    'get_logger',
    'ProgressLogger',
    'LogSection',
    'log_exception',
    'configure_third_party_loggers',
    'Colors',
    'ColoredFormatter',
]

__version__ = '1.0.0'
