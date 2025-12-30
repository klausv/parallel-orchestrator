#!/usr/bin/env python3
"""
Shared utilities for falsification debugger
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Use shared infrastructure for logging
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.logging_utils import setup_logging as _setup_logging

# Re-export setup_logging with same signature for backwards compatibility
def setup_logging(log_file: Optional[Path] = None, level: int = 20) -> None:
    """
    Setup logging configuration (delegates to shared infrastructure)

    Args:
        log_file: Optional file path for logging
        level: Logging level (default: INFO/20)
    """
    _setup_logging(level=level, log_file=log_file)


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """
    Load JSON from file

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON content as dictionary
    """
    with open(file_path, 'r') as f:
        return json.load(f)


def save_json_file(file_path: Path, data: Dict[str, Any], pretty: bool = True) -> None:
    """
    Save data to JSON file

    Args:
        file_path: Path to save JSON to
        data: Data to save
        pretty: Whether to pretty-print JSON
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2 if pretty else None)


def estimate_parallelization_speedup(task_times: List[float],
                                    num_workers: int = 2) -> Dict[str, float]:
    """
    Estimate parallelization speedup

    Args:
        task_times: List of estimated task times in seconds
        num_workers: Number of parallel workers

    Returns:
        Dictionary with speedup metrics
    """
    if not task_times:
        return {"sequential": 0, "parallel": 0, "speedup": 1.0}

    sequential_time = sum(task_times)
    critical_path = max(task_times)
    parallel_time = critical_path + (len(task_times) / num_workers) * 5  # Rough overhead

    speedup = sequential_time / parallel_time if parallel_time > 0 else 1.0

    return {
        "sequential": sequential_time,
        "parallel": parallel_time,
        "speedup": speedup,
        "time_saved": sequential_time - parallel_time,
        "critical_path": critical_path
    }


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def calculate_test_complexity_score(description: str,
                                   num_files: int = 1) -> float:
    """
    Estimate test complexity score based on description

    Args:
        description: Test description
        num_files: Number of files involved

    Returns:
        Complexity score 0.0-1.0
    """
    score = 0.0

    # Keywords indicating complexity
    complex_keywords = [
        "concurrent", "parallel", "race", "async", "distributed",
        "database", "network", "timeout", "edge case"
    ]

    for keyword in complex_keywords:
        if keyword.lower() in description.lower():
            score += 0.15

    # Adjust by number of files
    score += num_files * 0.05

    return min(score, 1.0)


def validate_hypothesis_testability(description: str,
                                   test_strategy: str,
                                   expected_behavior: str) -> tuple[bool, List[str]]:
    """
    Validate if hypothesis is testable

    Args:
        description: Hypothesis description
        test_strategy: How to test the hypothesis
        expected_behavior: Expected behavior if hypothesis is false

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    if not description or len(description) < 10:
        issues.append("Description too short or missing")

    if not test_strategy or len(test_strategy) < 10:
        issues.append("Test strategy too vague or missing")

    if not expected_behavior:
        issues.append("Expected behavior not specified")

    # Check for common patterns
    if "?" in test_strategy:
        issues.append("Test strategy contains questions (unclear)")

    if test_strategy.lower() == "test it":
        issues.append("Test strategy is too vague")

    return len(issues) == 0, issues


def create_session_report(session_id: str,
                         results: Dict[str, Any]) -> str:
    """
    Create formatted session report

    Args:
        session_id: Session identifier
        results: Results dictionary

    Returns:
        Formatted report string
    """
    report = f"""
═══════════════════════════════════════════════════════════
FALSIFICATION SESSION REPORT
═══════════════════════════════════════════════════════════

Session ID: {session_id}
Timestamp: {datetime.now().isoformat()}

Results:
  - Falsified:    {results.get('falsified', 0)}
  - Supported:    {results.get('supported', 0)}
  - Inconclusive: {results.get('inconclusive', 0)}

Confidence: {results.get('confidence', 0):.2%}

Recommended Action:
  {results.get('recommended_action', 'N/A')}

Next Steps:
"""

    for i, step in enumerate(results.get('next_steps', []), 1):
        report += f"  {i}. {step}\n"

    report += "\n═══════════════════════════════════════════════════════════\n"

    return report
