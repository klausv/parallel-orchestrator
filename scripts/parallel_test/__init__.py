"""
Falsification Debugger - Systematic Bug Debugging through Parallel Hypothesis Testing

Main components:
  - HypothesisManager: Hypothesis lifecycle and ranking
  - WorktreeOrchestrator: Git worktree management
  - TestExecutor: Parallel test execution
  - ResultsAnalyzer: Results analysis and reporting
"""

from .config import (
    Hypothesis,
    TestExecutionResult,
    FalsificationReport,
    FalsificationConfig,
    HypothesisStatus,
    TestResult
)

from .hypothesis_manager import HypothesisManager
from .worktree_orchestrator import WorktreeOrchestrator, WorktreeConfig
from .test_executor import TestExecutor
from .results_analyzer import ResultsAnalyzer
from . import utils

__version__ = "1.0.0"
__all__ = [
    "Hypothesis",
    "TestExecutionResult",
    "FalsificationReport",
    "FalsificationConfig",
    "HypothesisStatus",
    "TestResult",
    "HypothesisManager",
    "WorktreeOrchestrator",
    "WorktreeConfig",
    "TestExecutor",
    "ResultsAnalyzer",
    "utils"
]
