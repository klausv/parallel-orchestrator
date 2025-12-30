#!/usr/bin/env python3
"""
Parallel Orchestrator Logging System

Comprehensive logging for task splitting, agent allocation, timing metrics,
and hypothesis testing results. Enables performance analysis and improvement.

Usage:
    from logs import OrchestratorLogger, TaskSplitDecision, AgentAllocation

    logger = OrchestratorLogger(Path.cwd())
    with logger.time_operation("task_split"):
        # ... splitting logic
    logger.log_task_split(decision)
    logger.save_reports()
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import time
import os


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class LogLevel(Enum):
    """Log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    METRIC = "METRIC"


class OperationType(Enum):
    """Types of operations being logged."""
    TASK_SPLIT = "task_split"
    AGENT_ALLOCATION = "agent_allocation"
    WORKTREE_OPERATION = "worktree_operation"
    HYPOTHESIS_TEST = "hypothesis_test"
    MERGE_OPERATION = "merge_operation"
    OVERHEAD_CALCULATION = "overhead_calculation"
    COMPLEXITY_ANALYSIS = "complexity_analysis"
    VALIDATION = "validation"
    SESSION = "session"


# ============================================================================
# DATA CLASSES FOR STRUCTURED LOGGING
# ============================================================================

@dataclass
class TimingMetric:
    """Records timing for a single operation."""
    operation: str
    start_time: float
    end_time: float
    duration_seconds: float
    overhead_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSplitDecision:
    """Records a task splitting decision with full reasoning."""
    task_description: str
    timestamp: str
    recommended_splits: int
    actual_splits: int
    complexity_score: float
    estimated_sequential_minutes: float
    estimated_parallel_minutes: float
    efficiency_gain_percent: float
    is_worth_parallelizing: bool
    reasoning: str
    subtasks: List[Dict[str, Any]] = field(default_factory=list)
    file_ownership: Dict[str, str] = field(default_factory=dict)
    conflict_risk: str = "UNKNOWN"
    validation_passed: bool = True


@dataclass
class AgentAllocation:
    """Records agent assignment for a subtask."""
    subtask_name: str
    agent_type: str
    skill_command: str
    confidence: float
    rationale: str
    files_assigned: List[str] = field(default_factory=list)
    estimated_complexity: str = "MEDIUM"
    estimated_minutes: float = 0.0


@dataclass
class HypothesisTestLog:
    """Records a hypothesis testing session."""
    session_id: str
    timestamp: str
    hypotheses_tested: int
    hypotheses_falsified: int
    hypotheses_survived: int
    hypotheses_inconclusive: int
    total_duration_seconds: float
    parallel_duration_seconds: float
    speedup_factor: float
    next_action: str
    recommendation: str
    detailed_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class WorktreeOperation:
    """Records a git worktree operation."""
    operation: str  # create, cleanup
    worktree_path: str
    branch_name: str
    timestamp: str
    duration_seconds: float
    success: bool
    error_message: str = ""


# ============================================================================
# MAIN LOGGER CLASS
# ============================================================================

class OrchestratorLogger:
    """Central logging facility for parallel-orchestrator.

    Creates structured logs for task splitting, agent allocation,
    hypothesis testing, and timing metrics. Generates both JSON
    and Markdown reports for analysis.

    Example:
        logger = OrchestratorLogger(Path("/project"))

        with logger.time_operation("complexity_analysis"):
            result = analyze_complexity()

        logger.log_task_split(TaskSplitDecision(...))
        logger.save_reports()
    """

    def __init__(self, project_root: Path, session_id: Optional[str] = None):
        """Initialize logger for a session.

        Args:
            project_root: Root directory of the project being orchestrated
            session_id: Optional custom session ID (defaults to timestamp)
        """
        self.project_root = Path(project_root)
        self.logs_dir = self.project_root / "logs"
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create logs directory structure
        self._ensure_directories()

        # Session-specific log file (JSONL format)
        self.session_log_path = self.logs_dir / "sessions" / f"{self.session_id}.jsonl"

        # In-memory storage for current session
        self.entries: List[Dict[str, Any]] = []
        self.timings: List[TimingMetric] = []
        self.task_splits: List[TaskSplitDecision] = []
        self.agent_allocations: List[AgentAllocation] = []
        self.hypothesis_tests: List[HypothesisTestLog] = []
        self.worktree_ops: List[WorktreeOperation] = []

        self._start_time = time.time()
        self._log_session_start()

    def _ensure_directories(self):
        """Create logs directory structure if it doesn't exist."""
        self.logs_dir.mkdir(exist_ok=True)
        (self.logs_dir / "sessions").mkdir(exist_ok=True)
        (self.logs_dir / "reports").mkdir(exist_ok=True)
        (self.logs_dir / "shell").mkdir(exist_ok=True)

        # Add .gitkeep to preserve empty directories
        for subdir in ["sessions", "reports", "shell"]:
            gitkeep = self.logs_dir / subdir / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()

    def _log_session_start(self):
        """Log session initialization."""
        self.log(
            LogLevel.INFO,
            OperationType.SESSION,
            f"Session started: {self.session_id}",
            {
                "project_root": str(self.project_root),
                "start_time": datetime.now().isoformat()
            }
        )

    # -------------------------------------------------------------------------
    # Core Logging Methods
    # -------------------------------------------------------------------------

    def log(self, level: LogLevel, operation: OperationType, message: str,
            data: Optional[Dict[str, Any]] = None):
        """Log a structured entry.

        Args:
            level: Log severity level
            operation: Type of operation being logged
            message: Human-readable log message
            data: Optional structured data to include
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "level": level.value,
            "operation": operation.value,
            "message": message,
            "data": data or {}
        }
        self.entries.append(entry)
        self._persist_entry(entry)

    def log_timing(self, metric: TimingMetric):
        """Log a timing metric.

        Args:
            metric: TimingMetric dataclass with operation timing data
        """
        self.timings.append(metric)
        self.log(
            LogLevel.METRIC,
            OperationType.OVERHEAD_CALCULATION,
            f"Timing: {metric.operation} took {metric.duration_seconds:.2f}s",
            asdict(metric)
        )

    # -------------------------------------------------------------------------
    # Specialized Logging Methods
    # -------------------------------------------------------------------------

    def log_task_split(self, decision: TaskSplitDecision):
        """Log a task splitting decision.

        Args:
            decision: TaskSplitDecision with full splitting details
        """
        self.task_splits.append(decision)
        self.log(
            LogLevel.INFO,
            OperationType.TASK_SPLIT,
            f"Split task into {decision.actual_splits} subtasks "
            f"(efficiency gain: {decision.efficiency_gain_percent:.1f}%)",
            asdict(decision)
        )

    def log_agent_allocation(self, allocation: AgentAllocation):
        """Log an agent allocation decision.

        Args:
            allocation: AgentAllocation with agent assignment details
        """
        self.agent_allocations.append(allocation)
        self.log(
            LogLevel.INFO,
            OperationType.AGENT_ALLOCATION,
            f"Allocated {allocation.agent_type} to '{allocation.subtask_name}' "
            f"(confidence: {allocation.confidence:.0%})",
            asdict(allocation)
        )

    def log_hypothesis_test(self, test_log: HypothesisTestLog):
        """Log a hypothesis testing session.

        Args:
            test_log: HypothesisTestLog with testing session details
        """
        self.hypothesis_tests.append(test_log)
        self.log(
            LogLevel.INFO,
            OperationType.HYPOTHESIS_TEST,
            f"Tested {test_log.hypotheses_tested} hypotheses: "
            f"{test_log.hypotheses_falsified} falsified, "
            f"{test_log.hypotheses_survived} survived "
            f"(speedup: {test_log.speedup_factor:.2f}x)",
            asdict(test_log)
        )

    def log_worktree_operation(self, op: WorktreeOperation):
        """Log a git worktree operation.

        Args:
            op: WorktreeOperation with worktree details
        """
        self.worktree_ops.append(op)
        status = "succeeded" if op.success else f"failed: {op.error_message}"
        self.log(
            LogLevel.INFO if op.success else LogLevel.ERROR,
            OperationType.WORKTREE_OPERATION,
            f"Worktree {op.operation} {status}: {op.branch_name}",
            asdict(op)
        )

    def log_complexity_analysis(self, complexity_data: Dict[str, Any]):
        """Log complexity analysis results.

        Args:
            complexity_data: Dictionary with complexity analysis details
        """
        self.log(
            LogLevel.INFO,
            OperationType.COMPLEXITY_ANALYSIS,
            f"Complexity score: {complexity_data.get('total_score', 'N/A')}",
            complexity_data
        )

    def log_validation(self, validation_type: str, passed: bool,
                       details: Optional[Dict[str, Any]] = None):
        """Log a validation check result.

        Args:
            validation_type: Type of validation (e.g., "file_conflicts")
            passed: Whether validation passed
            details: Optional validation details
        """
        self.log(
            LogLevel.INFO if passed else LogLevel.WARNING,
            OperationType.VALIDATION,
            f"Validation '{validation_type}': {'PASSED' if passed else 'FAILED'}",
            {"validation_type": validation_type, "passed": passed, **(details or {})}
        )

    # -------------------------------------------------------------------------
    # Context Manager for Timing
    # -------------------------------------------------------------------------

    def time_operation(self, operation_name: str,
                       metadata: Optional[Dict[str, Any]] = None):
        """Context manager for timing operations.

        Usage:
            with logger.time_operation("claude_api_call"):
                result = call_claude_api()

        Args:
            operation_name: Name of the operation being timed
            metadata: Optional metadata to include with timing

        Returns:
            OperationTimer context manager
        """
        return OperationTimer(self, operation_name, metadata)

    # -------------------------------------------------------------------------
    # Report Generation
    # -------------------------------------------------------------------------

    def generate_json_report(self) -> str:
        """Generate JSON report for machine consumption.

        Returns:
            JSON string with complete session report
        """
        return json.dumps(self._build_report_data(), indent=2, default=str)

    def generate_markdown_report(self) -> str:
        """Generate Markdown report for human consumption.

        Returns:
            Markdown string with formatted session report
        """
        data = self._build_report_data()
        return self._format_markdown_report(data)

    def save_reports(self) -> tuple:
        """Save both JSON and Markdown reports to files.

        Returns:
            Tuple of (json_path, markdown_path)
        """
        report_data = self._build_report_data()

        # JSON report
        json_path = self.logs_dir / "reports" / f"{self.session_id}.json"
        with open(json_path, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)

        # Markdown report
        md_path = self.logs_dir / "reports" / f"{self.session_id}.md"
        with open(md_path, 'w') as f:
            f.write(self._format_markdown_report(report_data))

        self.log(
            LogLevel.INFO,
            OperationType.SESSION,
            f"Reports saved: {json_path.name}, {md_path.name}",
            {"json_path": str(json_path), "markdown_path": str(md_path)}
        )

        return json_path, md_path

    # -------------------------------------------------------------------------
    # Metrics Aggregation
    # -------------------------------------------------------------------------

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Calculate aggregate performance metrics for analysis.

        Returns:
            Dictionary with performance metrics
        """
        if not self.timings:
            return {"total_operations": 0}

        total_time = sum(t.duration_seconds for t in self.timings)
        total_overhead = sum(t.overhead_seconds for t in self.timings)

        return {
            "total_operations": len(self.timings),
            "total_time_seconds": round(total_time, 2),
            "total_overhead_seconds": round(total_overhead, 2),
            "average_operation_time": round(total_time / len(self.timings), 2),
            "operations_by_type": self._group_timings_by_operation(),
            "efficiency_ratio": self._calculate_efficiency_ratio()
        }

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the current session.

        Returns:
            Dictionary with session summary
        """
        end_time = time.time()
        return {
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self._start_time).isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_duration_minutes": round((end_time - self._start_time) / 60, 2),
            "total_duration_seconds": round(end_time - self._start_time, 2),
            "operations_count": len(self.entries),
            "tasks_split": len(self.task_splits),
            "agents_allocated": len(self.agent_allocations),
            "hypothesis_tests": len(self.hypothesis_tests),
            "worktree_operations": len(self.worktree_ops),
            "errors_count": sum(1 for e in self.entries if e["level"] == "ERROR")
        }

    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------

    def _persist_entry(self, entry: Dict[str, Any]):
        """Append entry to session log file (JSONL format)."""
        with open(self.session_log_path, 'a') as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def _build_report_data(self) -> Dict[str, Any]:
        """Build complete report data structure."""
        return {
            "session_summary": self.get_session_summary(),
            "task_splits": [asdict(ts) for ts in self.task_splits],
            "agent_allocations": [asdict(aa) for aa in self.agent_allocations],
            "hypothesis_tests": [asdict(ht) for ht in self.hypothesis_tests],
            "worktree_operations": [asdict(wo) for wo in self.worktree_ops],
            "performance_metrics": self.get_performance_metrics(),
            "timing_details": [asdict(t) for t in self.timings]
        }

    def _format_markdown_report(self, data: Dict[str, Any]) -> str:
        """Format report as Markdown."""
        lines = []
        summary = data["session_summary"]

        # Header
        lines.append(f"# Parallel Orchestrator Session Report")
        lines.append(f"")
        lines.append(f"**Session ID**: `{summary['session_id']}`")
        lines.append(f"**Duration**: {summary['total_duration_minutes']:.1f} minutes")
        lines.append(f"**Start**: {summary['start_time']}")
        lines.append(f"**End**: {summary['end_time']}")
        lines.append("")

        # Summary stats
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Tasks Split | {summary['tasks_split']} |")
        lines.append(f"| Agents Allocated | {summary['agents_allocated']} |")
        lines.append(f"| Hypothesis Tests | {summary['hypothesis_tests']} |")
        lines.append(f"| Worktree Operations | {summary['worktree_operations']} |")
        lines.append(f"| Total Operations | {summary['operations_count']} |")
        lines.append(f"| Errors | {summary['errors_count']} |")
        lines.append("")

        # Task Splits
        if data["task_splits"]:
            lines.append("## Task Splitting Decisions")
            lines.append("")
            lines.append("| Task | Splits | Sequential Est. | Parallel Est. | Efficiency |")
            lines.append("|------|--------|-----------------|---------------|------------|")
            for ts in data["task_splits"]:
                task_short = ts["task_description"][:40] + "..." if len(ts["task_description"]) > 40 else ts["task_description"]
                lines.append(
                    f"| {task_short} | {ts['actual_splits']} | "
                    f"{ts['estimated_sequential_minutes']:.0f} min | "
                    f"{ts['estimated_parallel_minutes']:.0f} min | "
                    f"{ts['efficiency_gain_percent']:.0f}% |"
                )
            lines.append("")

        # Agent Allocations
        if data["agent_allocations"]:
            lines.append("## Agent Allocations")
            lines.append("")
            lines.append("| Subtask | Agent | Confidence | Files |")
            lines.append("|---------|-------|------------|-------|")
            for aa in data["agent_allocations"]:
                files_str = ", ".join(aa["files_assigned"][:3])
                if len(aa["files_assigned"]) > 3:
                    files_str += f" (+{len(aa['files_assigned']) - 3} more)"
                lines.append(
                    f"| {aa['subtask_name']} | {aa['agent_type']} | "
                    f"{aa['confidence']:.0%} | {files_str} |"
                )
            lines.append("")

        # Hypothesis Tests
        if data["hypothesis_tests"]:
            lines.append("## Hypothesis Testing Sessions")
            lines.append("")
            for ht in data["hypothesis_tests"]:
                lines.append(f"### Session: {ht['session_id']}")
                lines.append("")
                lines.append("| Metric | Value |")
                lines.append("|--------|-------|")
                lines.append(f"| Hypotheses Tested | {ht['hypotheses_tested']} |")
                lines.append(f"| Falsified | {ht['hypotheses_falsified']} |")
                lines.append(f"| Survived | {ht['hypotheses_survived']} |")
                lines.append(f"| Inconclusive | {ht['hypotheses_inconclusive']} |")
                lines.append(f"| Total Duration | {ht['total_duration_seconds']:.1f}s |")
                lines.append(f"| Parallel Duration | {ht['parallel_duration_seconds']:.1f}s |")
                lines.append(f"| Speedup | {ht['speedup_factor']:.2f}x |")
                lines.append("")
                lines.append(f"**Recommendation**: {ht['recommendation']}")
                lines.append(f"**Next Action**: {ht['next_action']}")
                lines.append("")

        # Performance Metrics
        metrics = data["performance_metrics"]
        if metrics.get("total_operations", 0) > 0:
            lines.append("## Performance Metrics")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Total Operations | {metrics['total_operations']} |")
            lines.append(f"| Total Time | {metrics['total_time_seconds']:.1f}s |")
            lines.append(f"| Total Overhead | {metrics['total_overhead_seconds']:.1f}s |")
            lines.append(f"| Avg Operation Time | {metrics['average_operation_time']:.2f}s |")
            lines.append(f"| Efficiency Ratio | {metrics['efficiency_ratio']:.2f}x |")
            lines.append("")

            if metrics.get("operations_by_type"):
                lines.append("### Operations by Type")
                lines.append("")
                lines.append("| Operation | Count | Total Time | Avg Time |")
                lines.append("|-----------|-------|------------|----------|")
                for op_type, stats in metrics["operations_by_type"].items():
                    lines.append(
                        f"| {op_type} | {stats['count']} | "
                        f"{stats['total_seconds']:.1f}s | {stats['avg_seconds']:.2f}s |"
                    )
                lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Generated by parallel-orchestrator at {datetime.now().isoformat()}*")

        return "\n".join(lines)

    def _group_timings_by_operation(self) -> Dict[str, Dict]:
        """Group timing metrics by operation type."""
        groups: Dict[str, Dict] = {}
        for t in self.timings:
            if t.operation not in groups:
                groups[t.operation] = {"count": 0, "total_seconds": 0.0, "avg_seconds": 0.0}
            groups[t.operation]["count"] += 1
            groups[t.operation]["total_seconds"] += t.duration_seconds

        for op in groups:
            groups[op]["total_seconds"] = round(groups[op]["total_seconds"], 2)
            groups[op]["avg_seconds"] = round(
                groups[op]["total_seconds"] / groups[op]["count"], 2
            )

        return groups

    def _calculate_efficiency_ratio(self) -> float:
        """Calculate overall efficiency ratio from task splits."""
        if not self.task_splits:
            return 1.0

        total_sequential = sum(ts.estimated_sequential_minutes for ts in self.task_splits)
        total_parallel = sum(ts.estimated_parallel_minutes for ts in self.task_splits)

        if total_parallel > 0:
            return round(total_sequential / total_parallel, 2)
        return 1.0


# ============================================================================
# CONTEXT MANAGER FOR TIMING
# ============================================================================

class OperationTimer:
    """Context manager for timing operations.

    Usage:
        with logger.time_operation("api_call", {"endpoint": "/split"}):
            result = make_api_call()
    """

    def __init__(self, logger: OrchestratorLogger, operation: str,
                 metadata: Optional[Dict[str, Any]] = None):
        self.logger = logger
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        metric = TimingMetric(
            operation=self.operation,
            start_time=self.start_time,
            end_time=self.end_time,
            duration_seconds=round(self.end_time - self.start_time, 3),
            metadata=self.metadata
        )
        self.logger.log_timing(metric)
        return False  # Don't suppress exceptions

    @property
    def elapsed(self) -> float:
        """Get elapsed time (works during and after context)."""
        if self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return time.time() - self.start_time
        return 0.0


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_session_logs(logs_dir: Path, session_id: str) -> List[Dict[str, Any]]:
    """Load all log entries for a specific session.

    Args:
        logs_dir: Path to logs directory
        session_id: Session ID to load

    Returns:
        List of log entry dictionaries
    """
    session_file = logs_dir / "sessions" / f"{session_id}.jsonl"
    if not session_file.exists():
        return []

    entries = []
    with open(session_file, 'r') as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def list_sessions(logs_dir: Path) -> List[str]:
    """List all session IDs in the logs directory.

    Args:
        logs_dir: Path to logs directory

    Returns:
        List of session IDs sorted by most recent first
    """
    sessions_dir = logs_dir / "sessions"
    if not sessions_dir.exists():
        return []

    sessions = [f.stem for f in sessions_dir.glob("*.jsonl")]
    return sorted(sessions, reverse=True)


def get_historical_metrics(logs_dir: Path, days: int = 7) -> Dict[str, Any]:
    """Aggregate metrics from recent sessions for trend analysis.

    Args:
        logs_dir: Path to logs directory
        days: Number of days to include

    Returns:
        Dictionary with aggregated historical metrics
    """
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y%m%d")

    sessions = list_sessions(logs_dir)
    recent_sessions = [s for s in sessions if s[:8] >= cutoff_str]

    total_splits = 0
    total_efficiency = 0.0
    total_hypotheses = 0
    session_count = len(recent_sessions)

    for session_id in recent_sessions:
        report_file = logs_dir / "reports" / f"{session_id}.json"
        if report_file.exists():
            with open(report_file, 'r') as f:
                report = json.load(f)
                summary = report.get("session_summary", {})
                metrics = report.get("performance_metrics", {})

                total_splits += summary.get("tasks_split", 0)
                total_efficiency += metrics.get("efficiency_ratio", 1.0)
                total_hypotheses += summary.get("hypothesis_tests", 0)

    return {
        "period_days": days,
        "sessions_analyzed": session_count,
        "total_tasks_split": total_splits,
        "total_hypothesis_tests": total_hypotheses,
        "average_efficiency_ratio": round(total_efficiency / session_count, 2) if session_count > 0 else 1.0
    }


# ============================================================================
# CLI FOR STANDALONE USAGE
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parallel Orchestrator Logging Utilities")
    parser.add_argument("--list", action="store_true", help="List all sessions")
    parser.add_argument("--report", type=str, help="Generate report for session ID")
    parser.add_argument("--history", type=int, default=7, help="Show historical metrics for N days")
    parser.add_argument("--logs-dir", type=str, default="logs", help="Path to logs directory")

    args = parser.parse_args()
    logs_dir = Path(args.logs_dir)

    if args.list:
        sessions = list_sessions(logs_dir)
        print(f"Found {len(sessions)} sessions:")
        for s in sessions[:20]:  # Show last 20
            print(f"  {s}")

    elif args.report:
        entries = load_session_logs(logs_dir, args.report)
        print(f"Session {args.report}: {len(entries)} log entries")
        for entry in entries[:10]:
            print(f"  [{entry['level']}] {entry['operation']}: {entry['message']}")

    else:
        metrics = get_historical_metrics(logs_dir, args.history)
        print(f"Historical Metrics (last {args.history} days):")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
