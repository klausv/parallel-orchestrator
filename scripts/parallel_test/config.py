#!/usr/bin/env python3
"""
Configuration management for falsification debugger

DEPRECATED: This module is deprecated in favor of unified_config.py
New code should use UnifiedConfig instead of FalsificationConfig.

For migration:
    from scripts.parallel_test.unified_config import UnifiedConfig

    # Old way (deprecated)
    config = FalsificationConfig.from_yaml("config.yaml")

    # New way (recommended)
    config = UnifiedConfig.from_yaml("config.yaml")
    old_config = config.to_falsification_config()  # If needed for compatibility
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum
import yaml
import json
import warnings


class HypothesisStatus(Enum):
    """Hypothesis lifecycle states"""
    PENDING = "pending"
    TESTING = "testing"
    FALSIFIED = "falsified"
    SUPPORTED = "supported"
    INCONCLUSIVE = "inconclusive"


class TestResult(Enum):
    """Test execution outcomes"""
    PASS = "pass"           # Test passed (hypothesis falsified)
    FAIL = "fail"           # Test failed (hypothesis supported)
    TIMEOUT = "timeout"     # Test exceeded time limit
    ERROR = "error"         # Test crashed/error


@dataclass
class Hypothesis:
    """Represents a single bug hypothesis"""
    id: str
    description: str
    test_strategy: str = ""
    expected_behavior: str = ""
    estimated_test_time: float = 0.0
    probability: float = 0.5
    impact: float = 0.5
    test_complexity: float = 0.5
    status: HypothesisStatus = HypothesisStatus.PENDING
    test_results: Optional[Dict] = None
    confidence_score: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)

    def is_falsifiable(self) -> bool:
        """Check if hypothesis can be empirically tested"""
        return bool(self.test_strategy or self.description)

    def ranking_score(self, weights: Dict[str, float]) -> float:
        """Calculate ranking score for prioritization"""
        return (
            self.probability * weights.get("probability", 0.5) +
            self.impact * weights.get("impact", 0.3) -
            self.test_complexity * weights.get("complexity", 0.2)
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        d["status"] = self.status.value
        if self.test_results:
            d["test_results"] = self.test_results
        return d


@dataclass
class TestExecutionResult:
    """Result of testing a single hypothesis"""
    hypothesis_id: str
    result: TestResult
    duration: float
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    worktree_path: str = ""
    error_message: str = ""
    metrics: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "hypothesis_id": self.hypothesis_id,
            "result": self.result.value,
            "duration": self.duration,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "worktree_path": self.worktree_path,
            "error_message": self.error_message,
            "metrics": self.metrics
        }


@dataclass
class FalsificationReport:
    """Final report after hypothesis testing"""
    session_id: str
    bug_description: str
    total_hypotheses: int
    falsified: List[Hypothesis] = field(default_factory=list)
    supported: List[Hypothesis] = field(default_factory=list)
    inconclusive: List[Hypothesis] = field(default_factory=list)
    recommended_action: str = ""
    next_steps: List[str] = field(default_factory=list)
    confidence: float = 0.0
    test_results: List[TestExecutionResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "session_id": self.session_id,
            "bug_description": self.bug_description,
            "total_hypotheses": self.total_hypotheses,
            "falsified": len(self.falsified),
            "supported": len(self.supported),
            "inconclusive": len(self.inconclusive),
            "recommended_action": self.recommended_action,
            "next_steps": self.next_steps,
            "confidence": self.confidence
        }


@dataclass
class FalsificationConfig:
    """
    Configuration for falsification debugging

    DEPRECATED: Use UnifiedConfig from unified_config.py instead.
    This class is maintained for backward compatibility only.
    """

    # Hypothesis Management
    max_hypotheses: int = 5
    min_hypotheses: int = 2
    require_falsifiability: bool = True

    # Ranking Weights
    probability_weight: float = 0.5
    impact_weight: float = 0.3
    complexity_weight: float = -0.2

    # Test Execution
    test_timeout: int = 300  # 5 minutes
    min_parallel_time: int = 60
    test_command: str = "pytest"
    max_concurrent_tests: int = 5

    # Overhead Timings (seconds)
    worktree_creation_time: float = 8.0
    session_startup_time: float = 5.0
    environment_setup_time: float = 5.0
    cleanup_time: float = 3.0

    # Paths
    project_root: str = ""
    output_dir: str = ""
    config_file: str = ""

    # Agent Integration
    use_root_cause_analyst: bool = True
    use_sequential_thinking: bool = True
    use_quality_engineer: bool = True

    # Session Persistence
    use_memory_mcp: bool = True
    session_prefix: str = "falsification"

    def __post_init__(self):
        """Show deprecation warning"""
        warnings.warn(
            "FalsificationConfig is deprecated. Use UnifiedConfig from unified_config.py instead. "
            "See scripts/parallel_test/unified_config.py for migration guide.",
            DeprecationWarning,
            stacklevel=2
        )

    @classmethod
    def from_yaml(cls, config_path: str) -> "FalsificationConfig":
        """
        Load configuration from YAML file

        DEPRECATED: Use UnifiedConfig.from_yaml() instead
        """
        warnings.warn(
            "FalsificationConfig.from_yaml() is deprecated. "
            "Use UnifiedConfig.from_yaml() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f) or {}

        # Flatten nested config
        flat_config = {}

        # Hypothesis management
        if "hypothesis_management" in config_dict:
            hm = config_dict["hypothesis_management"]
            flat_config.update({
                "max_hypotheses": hm.get("max_concurrent", 5),
                "require_falsifiability": hm.get("validation_rules", {}).get("require_test_strategy", True)
            })

        # Test execution
        if "test_execution" in config_dict:
            test_cfg = config_dict["test_execution"]
            flat_config.update({
                "test_timeout": test_cfg.get("default_timeout", 300),
                "min_parallel_time": test_cfg.get("min_parallel_time", 60),
            })
            if "overhead" in test_cfg:
                flat_config.update({
                    "worktree_creation_time": test_cfg["overhead"].get("worktree_creation", 8.0),
                    "environment_setup_time": test_cfg["overhead"].get("environment_setup", 5.0),
                })

        # Agent integration
        if "agent_integration" in config_dict:
            integration = config_dict["agent_integration"]
            flat_config.update({
                "use_root_cause_analyst": integration.get("root_cause_analyst", {}).get("enabled", True),
                "use_sequential_thinking": integration.get("sequential_thinking_mcp", {}).get("enabled", True),
                "use_quality_engineer": integration.get("quality_engineer", {}).get("enabled", True),
                "use_memory_mcp": integration.get("memory_mcp", {}).get("enabled", True),
            })

        return cls(**flat_config)

    @classmethod
    def from_dict(cls, config_dict: Dict) -> "FalsificationConfig":
        """Load configuration from dictionary"""
        # Filter only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_config = {k: v for k, v in config_dict.items() if k in known_fields}
        return cls(**filtered_config)

    @classmethod
    def from_unified(cls, unified_config) -> "FalsificationConfig":
        """
        Create FalsificationConfig from UnifiedConfig

        Args:
            unified_config: UnifiedConfig instance

        Returns:
            FalsificationConfig instance (for backward compatibility)
        """
        return unified_config.to_falsification_config()

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)

    def to_unified(self):
        """
        Convert to UnifiedConfig

        Returns:
            UnifiedConfig instance
        """
        from .unified_config import UnifiedConfig
        return UnifiedConfig.from_falsification_config(self)


# ============================================================================
# MIGRATION HELPERS
# ============================================================================

def migrate_to_unified_config(old_config: FalsificationConfig):
    """
    Migrate old FalsificationConfig to new UnifiedConfig.

    Args:
        old_config: FalsificationConfig instance

    Returns:
        UnifiedConfig instance

    Example:
        old_config = FalsificationConfig.from_yaml("config.yaml")
        new_config = migrate_to_unified_config(old_config)
    """
    from .unified_config import UnifiedConfig
    return UnifiedConfig.from_falsification_config(old_config)


def load_config_auto(config_path: Optional[str] = None):
    """
    Auto-load configuration using the new UnifiedConfig system.

    This is a convenience function that automatically uses UnifiedConfig
    instead of the deprecated FalsificationConfig.

    Args:
        config_path: Path to YAML config file (optional)

    Returns:
        UnifiedConfig instance
    """
    from .unified_config import load_config
    return load_config(config_path)
