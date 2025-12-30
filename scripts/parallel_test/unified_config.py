#!/usr/bin/env python3
"""
Unified Configuration System for Parallel Orchestrator

Consolidates three incompatible configuration systems:
1. FalsificationConfig (scripts/parallel_test/config.py)
2. falsification_config.yaml (config/)
3. ParallelConfig (scripts/task-splitter.py)

Configuration hierarchy (highest priority first):
1. Environment variables (PARALLEL_TEST_*)
2. YAML config file
3. Explicit kwargs
4. Default values

Usage:
    # Load from YAML
    config = UnifiedConfig.from_yaml("config/falsification_config.yaml")

    # Load with overrides
    config = UnifiedConfig.from_yaml("config.yaml", max_hypotheses=10)

    # Access settings
    config.hypothesis.max_concurrent
    config.worktree.base_dir
    config.execution.test_timeout

    # Convert to old format for backward compatibility
    old_config = config.to_falsification_config()
    parallel_config = config.to_parallel_config()
"""

import os
import importlib.util
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum


# ============================================================================
# VALIDATION ERRORS
# ============================================================================

class ConfigValidationError(Exception):
    """Configuration validation failed."""
    pass


# ============================================================================
# CONFIGURATION SECTIONS
# ============================================================================

@dataclass
class HypothesisManagementConfig:
    """Hypothesis generation and management settings."""

    # Limits
    max_concurrent: int = 5
    min_hypotheses: int = 2
    require_falsifiability: bool = True

    # Ranking weights (must sum to ~1.0)
    probability_weight: float = 0.5
    impact_weight: float = 0.3
    complexity_weight: float = -0.2

    # Validation rules
    require_test_strategy: bool = True
    require_expected_behavior: bool = True
    min_test_time: float = 1.0  # Minimum seconds for valid test

    def validate(self) -> None:
        """Validate hypothesis management settings."""
        if self.max_concurrent < 1:
            raise ConfigValidationError("max_concurrent must be >= 1")

        if self.min_hypotheses < 1:
            raise ConfigValidationError("min_hypotheses must be >= 1")

        if self.min_hypotheses > self.max_concurrent:
            raise ConfigValidationError("min_hypotheses cannot exceed max_concurrent")

        # Validate weights sum to approximately 1.0 (allow some tolerance)
        weight_sum = abs(self.probability_weight) + abs(self.impact_weight) + abs(self.complexity_weight)
        if not (0.8 <= weight_sum <= 1.2):
            raise ConfigValidationError(
                f"Ranking weights should sum to ~1.0, got {weight_sum:.2f}"
            )


@dataclass
class WorktreeConfig:
    """Git worktree orchestration settings."""

    base_dir: Path = Path("../worktrees")
    branch_prefix: str = "hyp"
    auto_cleanup: bool = True
    preserve_on_error: bool = False
    use_pool: bool = True
    pool_size: int = 10

    # Overhead timings (seconds)
    creation_time: float = 8.0
    cleanup_time: float = 3.0

    def validate(self) -> None:
        """Validate worktree settings."""
        if self.pool_size < 1:
            raise ConfigValidationError("pool_size must be >= 1")

        if self.creation_time < 0:
            raise ConfigValidationError("creation_time cannot be negative")

        if not self.branch_prefix:
            raise ConfigValidationError("branch_prefix cannot be empty")


@dataclass
class ExecutionConfig:
    """Test and task execution settings."""

    # Test execution
    test_timeout: int = 300  # seconds (5 minutes)
    test_command: str = "pytest"
    max_concurrent_tests: int = 5
    min_parallel_time: int = 60  # Only parallelize if test >= 60s

    # Output capture
    capture_stdout: bool = True
    capture_stderr: bool = True
    collect_metrics: bool = True

    # Overhead timings (seconds)
    session_startup_time: float = 5.0
    context_building_time: float = 20.0
    environment_setup_time: float = 5.0
    merge_time_per_branch: float = 10.0
    conflict_resolution_base: float = 60.0

    # Async execution
    use_async: bool = True

    def validate(self) -> None:
        """Validate execution settings."""
        if self.test_timeout < 1:
            raise ConfigValidationError("test_timeout must be >= 1")

        if self.max_concurrent_tests < 1:
            raise ConfigValidationError("max_concurrent_tests must be >= 1")

        if self.min_parallel_time < 0:
            raise ConfigValidationError("min_parallel_time cannot be negative")


@dataclass
class AnalysisConfig:
    """Results analysis and reporting settings."""

    confidence_threshold: float = 0.7
    session_persistence: bool = True
    report_formats: List[str] = field(default_factory=lambda: ["markdown"])

    # Classification rules
    falsified_min_confidence: float = 0.7
    supported_min_confidence: float = 0.7
    falsified_exit_codes: List[int] = field(default_factory=lambda: [0])
    supported_exit_codes: List[int] = field(default_factory=lambda: [1, 2])

    def validate(self) -> None:
        """Validate analysis settings."""
        if not (0.0 <= self.confidence_threshold <= 1.0):
            raise ConfigValidationError("confidence_threshold must be between 0.0 and 1.0")

        valid_formats = ["markdown", "json", "text"]
        for fmt in self.report_formats:
            if fmt not in valid_formats:
                raise ConfigValidationError(
                    f"Invalid report format '{fmt}'. Must be one of: {valid_formats}"
                )


@dataclass
class TaskSplittingConfig:
    """Task splitting and parallelization optimization settings."""

    # Resource limits
    max_concurrent_sessions: int = 8
    max_worktrees: int = 15
    min_files_per_subtask: int = 2
    min_task_complexity: float = 0.2

    # Break-even thresholds (minutes)
    # Tasks shorter than these should not be split
    min_task_time_for_splits: Dict[int, float] = field(default_factory=lambda: {
        2: 5.0,   # 2-way split requires >5 min task
        3: 12.0,  # 3-way split requires >12 min task
        4: 20.0,  # 4-way split requires >20 min task
        5: 30.0   # 5+ way split requires >30 min task
    })

    # Complexity weights (for scoring)
    complexity_per_file_modify: float = 0.15
    complexity_per_file_create: float = 0.10
    complexity_per_loc_estimate: float = 0.001
    complexity_per_dependency: float = 0.05

    def validate(self) -> None:
        """Validate task splitting settings."""
        if self.max_concurrent_sessions < 1:
            raise ConfigValidationError("max_concurrent_sessions must be >= 1")

        if self.max_worktrees < 1:
            raise ConfigValidationError("max_worktrees must be >= 1")

        if self.min_files_per_subtask < 1:
            raise ConfigValidationError("min_files_per_subtask must be >= 1")

        if not (0.0 <= self.min_task_complexity <= 1.0):
            raise ConfigValidationError("min_task_complexity must be between 0.0 and 1.0")


@dataclass
class AgentIntegrationConfig:
    """SuperClaude agent and MCP integration settings."""

    # Agent enablement
    use_root_cause_analyst: bool = True
    use_sequential_thinking: bool = True
    use_quality_engineer: bool = True
    use_parallel_orchestrator: bool = True

    # MCP servers
    use_memory_mcp: bool = True
    session_prefix: str = "falsification"

    # Paths
    scripts_path: str = "~/klauspython/parallel-orchestrator/scripts"

    def validate(self) -> None:
        """Validate agent integration settings."""
        if not self.session_prefix:
            raise ConfigValidationError("session_prefix cannot be empty")


@dataclass
class PathsConfig:
    """Project paths and directories."""

    project_root: Path = Path(".")
    output_dir: Path = Path(".")
    config_file: Path = Path("")
    artifact_dir: Path = Path(".falsification_artifacts")

    def validate(self) -> None:
        """Validate paths."""
        # Ensure paths are Path objects
        self.project_root = Path(self.project_root)
        self.output_dir = Path(self.output_dir)
        self.config_file = Path(self.config_file)
        self.artifact_dir = Path(self.artifact_dir)


@dataclass
class SessionConfig:
    """Session persistence and state management."""

    auto_save: bool = True
    save_interval: int = 300  # seconds
    preserve_artifacts: bool = True

    def validate(self) -> None:
        """Validate session settings."""
        if self.save_interval < 1:
            raise ConfigValidationError("save_interval must be >= 1")


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    file: str = "falsification.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def validate(self) -> None:
        """Validate logging settings."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.level.upper() not in valid_levels:
            raise ConfigValidationError(
                f"Invalid log level '{self.level}'. Must be one of: {valid_levels}"
            )


# ============================================================================
# UNIFIED CONFIGURATION
# ============================================================================

@dataclass
class UnifiedConfig:
    """
    Unified configuration for parallel orchestrator and falsification debugger.

    Consolidates all configuration systems with proper validation and
    backward compatibility.
    """

    hypothesis: HypothesisManagementConfig = field(default_factory=HypothesisManagementConfig)
    worktree: WorktreeConfig = field(default_factory=WorktreeConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    task_splitting: TaskSplittingConfig = field(default_factory=TaskSplittingConfig)
    agent_integration: AgentIntegrationConfig = field(default_factory=AgentIntegrationConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def validate(self) -> None:
        """Validate all configuration sections."""
        errors = []

        sections = [
            ("hypothesis", self.hypothesis),
            ("worktree", self.worktree),
            ("execution", self.execution),
            ("analysis", self.analysis),
            ("task_splitting", self.task_splitting),
            ("agent_integration", self.agent_integration),
            ("paths", self.paths),
            ("session", self.session),
            ("logging", self.logging),
        ]

        for name, section in sections:
            try:
                section.validate()
            except ConfigValidationError as e:
                errors.append(f"{name}: {e}")

        if errors:
            raise ConfigValidationError(
                f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )

    @classmethod
    def from_yaml(cls, config_path: str, **overrides) -> "UnifiedConfig":
        """
        Load configuration from YAML file with optional overrides.

        Args:
            config_path: Path to YAML configuration file
            **overrides: Explicit overrides for any config value

        Returns:
            UnifiedConfig instance

        Raises:
            ConfigValidationError: If configuration is invalid
            FileNotFoundError: If config file doesn't exist
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, 'r') as f:
            yaml_data = yaml.safe_load(f) or {}

        # Parse sections from YAML
        sections = {}

        # Hypothesis management
        if "hypothesis_management" in yaml_data:
            hm = yaml_data["hypothesis_management"]
            sections["hypothesis"] = HypothesisManagementConfig(
                max_concurrent=hm.get("max_concurrent", 5),
                min_hypotheses=hm.get("min_hypotheses", 2),
                probability_weight=hm.get("ranking_weights", {}).get("probability", 0.5),
                impact_weight=hm.get("ranking_weights", {}).get("impact", 0.3),
                complexity_weight=hm.get("ranking_weights", {}).get("complexity", -0.2),
                require_test_strategy=hm.get("validation_rules", {}).get("require_test_strategy", True),
                require_expected_behavior=hm.get("validation_rules", {}).get("require_expected_behavior", True),
                min_test_time=hm.get("validation_rules", {}).get("min_test_time", 1.0),
            )

        # Worktree orchestration
        if "worktree_orchestration" in yaml_data:
            wo = yaml_data["worktree_orchestration"]
            sections["worktree"] = WorktreeConfig(
                base_dir=Path(wo.get("base_dir", "../worktrees")),
                branch_prefix=wo.get("branch_prefix", "hyp"),
                auto_cleanup=wo.get("auto_cleanup", True),
                preserve_on_error=wo.get("preserve_on_error", False),
            )

        # Test execution
        if "test_execution" in yaml_data:
            te = yaml_data["test_execution"]
            sections["execution"] = ExecutionConfig(
                test_timeout=te.get("default_timeout", 300),
                min_parallel_time=te.get("min_parallel_time", 60),
                max_concurrent_tests=te.get("max_concurrent_tests", 5),
                capture_stdout=te.get("capture_stdout", True),
                capture_stderr=te.get("capture_stderr", True),
                collect_metrics=te.get("collect_metrics", True),
                environment_setup_time=te.get("overhead", {}).get("environment_setup", 5.0),
            )

            # Merge overhead settings from worktree_orchestration if present
            if "worktree_orchestration" in yaml_data:
                wo_overhead = yaml_data["test_execution"].get("overhead", {})
                sections["worktree"].creation_time = wo_overhead.get("worktree_creation", 8.0)
                sections["worktree"].cleanup_time = wo_overhead.get("cleanup", 3.0)

        # Results analysis
        if "results_analysis" in yaml_data:
            ra = yaml_data["results_analysis"]

            # Parse classification rules
            classification = ra.get("classification_rules", {})
            falsified = classification.get("falsified", {})
            supported = classification.get("supported", {})

            sections["analysis"] = AnalysisConfig(
                confidence_threshold=ra.get("confidence_threshold", 0.7),
                session_persistence=ra.get("session_persistence", True),
                report_formats=[ra.get("report_format", "markdown")],
                falsified_min_confidence=falsified.get("min_confidence", 0.7),
                supported_min_confidence=supported.get("min_confidence", 0.7),
                falsified_exit_codes=[falsified.get("exit_code", 0)],
                supported_exit_codes=supported.get("exit_code", [1, 2]) if isinstance(supported.get("exit_code"), list) else [supported.get("exit_code", 1)],
            )

        # Agent integration
        if "agent_integration" in yaml_data:
            ai = yaml_data["agent_integration"]
            sections["agent_integration"] = AgentIntegrationConfig(
                use_root_cause_analyst=ai.get("root_cause_analyst", {}).get("enabled", True),
                use_sequential_thinking=ai.get("sequential_thinking_mcp", {}).get("enabled", True),
                use_quality_engineer=ai.get("quality_engineer", {}).get("enabled", True),
                use_parallel_orchestrator=ai.get("parallel_orchestrator", {}).get("enabled", True),
                use_memory_mcp=ai.get("memory_mcp", {}).get("enabled", True),
                session_prefix=ai.get("memory_mcp", {}).get("session_prefix", "falsification"),
                scripts_path=ai.get("parallel_orchestrator", {}).get("scripts_path", "~/klauspython/parallel-orchestrator/scripts"),
            )

        # Session management
        if "session" in yaml_data:
            sess = yaml_data["session"]
            sections["session"] = SessionConfig(
                auto_save=sess.get("auto_save", True),
                save_interval=sess.get("save_interval", 300),
                preserve_artifacts=sess.get("preserve_artifacts", True),
            )
            sections["paths"] = PathsConfig(
                artifact_dir=Path(sess.get("artifact_dir", ".falsification_artifacts"))
            )

        # Logging
        if "logging" in yaml_data:
            log = yaml_data["logging"]
            sections["logging"] = LoggingConfig(
                level=log.get("level", "INFO"),
                file=log.get("file", "falsification.log"),
                format=log.get("format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
            )

        # Apply environment variable overrides
        env_overrides = cls._load_from_env()
        sections = cls._deep_update(sections, env_overrides)

        # Apply explicit overrides
        sections = cls._deep_update(sections, overrides)

        # Create instance
        config = cls(**sections)

        # Validate
        config.validate()

        return config

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "UnifiedConfig":
        """
        Load configuration from dictionary.

        Args:
            config_dict: Dictionary with configuration values

        Returns:
            UnifiedConfig instance
        """
        sections = {}

        # Convert each section
        if "hypothesis" in config_dict:
            sections["hypothesis"] = HypothesisManagementConfig(**config_dict["hypothesis"])
        if "worktree" in config_dict:
            sections["worktree"] = WorktreeConfig(**config_dict["worktree"])
        if "execution" in config_dict:
            sections["execution"] = ExecutionConfig(**config_dict["execution"])
        if "analysis" in config_dict:
            sections["analysis"] = AnalysisConfig(**config_dict["analysis"])
        if "task_splitting" in config_dict:
            sections["task_splitting"] = TaskSplittingConfig(**config_dict["task_splitting"])
        if "agent_integration" in config_dict:
            sections["agent_integration"] = AgentIntegrationConfig(**config_dict["agent_integration"])
        if "paths" in config_dict:
            sections["paths"] = PathsConfig(**config_dict["paths"])
        if "session" in config_dict:
            sections["session"] = SessionConfig(**config_dict["session"])
        if "logging" in config_dict:
            sections["logging"] = LoggingConfig(**config_dict["logging"])

        config = cls(**sections)
        config.validate()
        return config

    @classmethod
    def _load_from_env(cls) -> Dict[str, Any]:
        """Load configuration overrides from environment variables."""
        overrides = {}

        # Environment variable pattern: PARALLEL_TEST_SECTION_FIELD
        # Example: PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT=10

        env_mappings = {
            # Hypothesis
            "PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT": ("hypothesis", "max_concurrent", int),
            "PARALLEL_TEST_HYPOTHESIS_MIN_HYPOTHESES": ("hypothesis", "min_hypotheses", int),

            # Execution
            "PARALLEL_TEST_EXECUTION_TEST_TIMEOUT": ("execution", "test_timeout", int),
            "PARALLEL_TEST_EXECUTION_MAX_CONCURRENT_TESTS": ("execution", "max_concurrent_tests", int),

            # Task splitting
            "PARALLEL_TEST_TASK_MAX_SESSIONS": ("task_splitting", "max_concurrent_sessions", int),
            "PARALLEL_TEST_TASK_MAX_WORKTREES": ("task_splitting", "max_worktrees", int),

            # Analysis
            "PARALLEL_TEST_ANALYSIS_CONFIDENCE_THRESHOLD": ("analysis", "confidence_threshold", float),

            # Logging
            "PARALLEL_TEST_LOGGING_LEVEL": ("logging", "level", str),
        }

        for env_var, (section, field, type_fn) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    if section not in overrides:
                        overrides[section] = {}
                    overrides[section][field] = type_fn(value)
                except (ValueError, TypeError):
                    # Skip invalid environment values
                    pass

        return overrides

    @staticmethod
    def _deep_update(base: Dict, updates: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = UnifiedConfig._deep_update(result[key], value)
            else:
                result[key] = value
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hypothesis": asdict(self.hypothesis),
            "worktree": {
                **asdict(self.worktree),
                "base_dir": str(self.worktree.base_dir)
            },
            "execution": asdict(self.execution),
            "analysis": asdict(self.analysis),
            "task_splitting": asdict(self.task_splitting),
            "agent_integration": asdict(self.agent_integration),
            "paths": {
                "project_root": str(self.paths.project_root),
                "output_dir": str(self.paths.output_dir),
                "config_file": str(self.paths.config_file),
                "artifact_dir": str(self.paths.artifact_dir),
            },
            "session": asdict(self.session),
            "logging": asdict(self.logging),
        }

    # ============================================================================
    # BACKWARD COMPATIBILITY
    # ============================================================================

    def to_falsification_config(self):
        """
        Convert to old FalsificationConfig format for backward compatibility.

        Returns:
            FalsificationConfig instance
        """
        from .config import FalsificationConfig

        return FalsificationConfig(
            # Hypothesis Management
            max_hypotheses=self.hypothesis.max_concurrent,
            min_hypotheses=self.hypothesis.min_hypotheses,
            require_falsifiability=self.hypothesis.require_falsifiability,

            # Ranking Weights
            probability_weight=self.hypothesis.probability_weight,
            impact_weight=self.hypothesis.impact_weight,
            complexity_weight=self.hypothesis.complexity_weight,

            # Test Execution
            test_timeout=self.execution.test_timeout,
            min_parallel_time=self.execution.min_parallel_time,
            test_command=self.execution.test_command,
            max_concurrent_tests=self.execution.max_concurrent_tests,

            # Overhead Timings
            worktree_creation_time=self.worktree.creation_time,
            session_startup_time=self.execution.session_startup_time,
            environment_setup_time=self.execution.environment_setup_time,
            cleanup_time=self.worktree.cleanup_time,

            # Paths
            project_root=str(self.paths.project_root),
            output_dir=str(self.paths.output_dir),
            config_file=str(self.paths.config_file),

            # Agent Integration
            use_root_cause_analyst=self.agent_integration.use_root_cause_analyst,
            use_sequential_thinking=self.agent_integration.use_sequential_thinking,
            use_quality_engineer=self.agent_integration.use_quality_engineer,

            # Session Persistence
            use_memory_mcp=self.agent_integration.use_memory_mcp,
            session_prefix=self.agent_integration.session_prefix,
        )

    def to_parallel_config(self):
        """
        Convert to ParallelConfig format for backward compatibility.

        Returns:
            ParallelConfig instance from task-splitter.py
        """
        # Import using importlib to handle hyphenated filename
        spec = importlib.util.spec_from_file_location(
            "task_splitter_module",
            str(Path(__file__).parent.parent / "task-splitter.py")
        )
        task_splitter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(task_splitter)
        ParallelConfig = task_splitter.ParallelConfig


        return ParallelConfig(
            # Overhead times
            worktree_creation_time=self.worktree.creation_time,
            session_startup_time=self.execution.session_startup_time,
            context_building_time=self.execution.context_building_time,
            merge_time_per_branch=self.execution.merge_time_per_branch,
            conflict_resolution_base=self.execution.conflict_resolution_base,

            # Resource limits
            max_concurrent_sessions=self.task_splitting.max_concurrent_sessions,
            max_worktrees=self.task_splitting.max_worktrees,
            min_files_per_subtask=self.task_splitting.min_files_per_subtask,
            min_task_complexity=self.task_splitting.min_task_complexity,

            # Break-even thresholds
            min_task_time_for_2_splits=self.task_splitting.min_task_time_for_splits.get(2, 5.0),
            min_task_time_for_3_splits=self.task_splitting.min_task_time_for_splits.get(3, 12.0),
            min_task_time_for_4_splits=self.task_splitting.min_task_time_for_splits.get(4, 20.0),
            min_task_time_for_5_plus=self.task_splitting.min_task_time_for_splits.get(5, 30.0),

            # Complexity weights
            complexity_per_file_modify=self.task_splitting.complexity_per_file_modify,
            complexity_per_file_create=self.task_splitting.complexity_per_file_create,
            complexity_per_loc_estimate=self.task_splitting.complexity_per_loc_estimate,
            complexity_per_dependency=self.task_splitting.complexity_per_dependency,
        )

    @classmethod
    def from_falsification_config(cls, old_config) -> "UnifiedConfig":
        """
        Create UnifiedConfig from old FalsificationConfig.

        Args:
            old_config: FalsificationConfig instance

        Returns:
            UnifiedConfig instance
        """
        return cls(
            hypothesis=HypothesisManagementConfig(
                max_concurrent=old_config.max_hypotheses,
                min_hypotheses=old_config.min_hypotheses,
                require_falsifiability=old_config.require_falsifiability,
                probability_weight=old_config.probability_weight,
                impact_weight=old_config.impact_weight,
                complexity_weight=old_config.complexity_weight,
            ),
            worktree=WorktreeConfig(
                creation_time=old_config.worktree_creation_time,
                cleanup_time=old_config.cleanup_time,
            ),
            execution=ExecutionConfig(
                test_timeout=old_config.test_timeout,
                min_parallel_time=old_config.min_parallel_time,
                test_command=old_config.test_command,
                max_concurrent_tests=old_config.max_concurrent_tests,
                session_startup_time=old_config.session_startup_time,
                environment_setup_time=old_config.environment_setup_time,
            ),
            agent_integration=AgentIntegrationConfig(
                use_root_cause_analyst=old_config.use_root_cause_analyst,
                use_sequential_thinking=old_config.use_sequential_thinking,
                use_quality_engineer=old_config.use_quality_engineer,
                use_memory_mcp=old_config.use_memory_mcp,
                session_prefix=old_config.session_prefix,
            ),
            paths=PathsConfig(
                project_root=Path(old_config.project_root) if old_config.project_root else Path("."),
                output_dir=Path(old_config.output_dir) if old_config.output_dir else Path("."),
                config_file=Path(old_config.config_file) if old_config.config_file else Path(""),
            ),
        )


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def load_config(config_path: Optional[str] = None, **overrides) -> UnifiedConfig:
    """
    Load configuration with smart defaults.

    Args:
        config_path: Path to YAML config file (optional)
        **overrides: Explicit overrides for any config value

    Returns:
        UnifiedConfig instance
    """
    if config_path:
        return UnifiedConfig.from_yaml(config_path, **overrides)

    # Try to find config in default locations
    default_paths = [
        "config/falsification_config.yaml",
        "../config/falsification_config.yaml",
        "falsification_config.yaml",
    ]

    for path in default_paths:
        if Path(path).exists():
            return UnifiedConfig.from_yaml(path, **overrides)

    # No config file found, use defaults with overrides
    config = UnifiedConfig()

    # Apply environment variable overrides
    env_overrides = UnifiedConfig._load_from_env()
    for section, values in env_overrides.items():
        section_obj = getattr(config, section)
        for key, value in values.items():
            setattr(section_obj, key, value)

    # Apply explicit overrides
    for section, values in overrides.items():
        if hasattr(config, section):
            section_obj = getattr(config, section)
            for key, value in values.items():
                setattr(section_obj, key, value)

    config.validate()
    return config
