#!/usr/bin/env python3
"""
Unit tests for unified configuration system

Tests configuration loading, validation, and backward compatibility.
"""

import pytest
import tempfile
from pathlib import Path
import yaml

from .unified_config import (
    UnifiedConfig,
    HypothesisManagementConfig,
    WorktreeConfig,
    ExecutionConfig,
    AnalysisConfig,
    TaskSplittingConfig,
    ConfigValidationError,
    load_config,
)
from .config import FalsificationConfig


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_yaml_config():
    """Create a temporary YAML config file for testing"""
    config_content = """
hypothesis_management:
  max_concurrent: 5
  min_hypotheses: 2
  ranking_weights:
    probability: 0.5
    impact: 0.3
    complexity: -0.2

worktree_orchestration:
  base_dir: "../worktrees"
  branch_prefix: "hyp"
  auto_cleanup: true

test_execution:
  default_timeout: 300
  min_parallel_time: 60
  max_concurrent_tests: 5

task_splitting:
  max_concurrent_sessions: 8
  max_worktrees: 15
  min_task_time_for_splits:
    2: 5.0
    3: 12.0

logging:
  level: "INFO"
  file: "test.log"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_content)
        return f.name


# ============================================================================
# VALIDATION TESTS
# ============================================================================

def test_hypothesis_config_validation():
    """Test hypothesis management config validation"""
    # Valid config
    config = HypothesisManagementConfig(max_concurrent=5, min_hypotheses=2)
    config.validate()  # Should not raise

    # Invalid: min > max
    invalid = HypothesisManagementConfig(max_concurrent=2, min_hypotheses=5)
    with pytest.raises(ConfigValidationError):
        invalid.validate()

    # Invalid: max < 1
    invalid = HypothesisManagementConfig(max_concurrent=0)
    with pytest.raises(ConfigValidationError):
        invalid.validate()


def test_worktree_config_validation():
    """Test worktree config validation"""
    # Valid config
    config = WorktreeConfig(pool_size=10, creation_time=8.0)
    config.validate()  # Should not raise

    # Invalid: pool_size < 1
    invalid = WorktreeConfig(pool_size=0)
    with pytest.raises(ConfigValidationError):
        invalid.validate()

    # Invalid: empty branch prefix
    invalid = WorktreeConfig(branch_prefix="")
    with pytest.raises(ConfigValidationError):
        invalid.validate()


def test_execution_config_validation():
    """Test execution config validation"""
    # Valid config
    config = ExecutionConfig(test_timeout=300, max_concurrent_tests=5)
    config.validate()  # Should not raise

    # Invalid: test_timeout < 1
    invalid = ExecutionConfig(test_timeout=0)
    with pytest.raises(ConfigValidationError):
        invalid.validate()

    # Invalid: max_concurrent_tests < 1
    invalid = ExecutionConfig(max_concurrent_tests=0)
    with pytest.raises(ConfigValidationError):
        invalid.validate()


def test_analysis_config_validation():
    """Test analysis config validation"""
    # Valid config
    config = AnalysisConfig(confidence_threshold=0.7, report_formats=["markdown"])
    config.validate()  # Should not raise

    # Invalid: confidence threshold out of range
    invalid = AnalysisConfig(confidence_threshold=1.5)
    with pytest.raises(ConfigValidationError):
        invalid.validate()

    # Invalid: unknown report format
    invalid = AnalysisConfig(report_formats=["invalid_format"])
    with pytest.raises(ConfigValidationError):
        invalid.validate()


def test_task_splitting_config_validation():
    """Test task splitting config validation"""
    # Valid config
    config = TaskSplittingConfig(max_concurrent_sessions=8, max_worktrees=15)
    config.validate()  # Should not raise

    # Invalid: max_concurrent_sessions < 1
    invalid = TaskSplittingConfig(max_concurrent_sessions=0)
    with pytest.raises(ConfigValidationError):
        invalid.validate()


# ============================================================================
# YAML LOADING TESTS
# ============================================================================

def test_load_from_yaml(sample_yaml_config):
    """Test loading configuration from YAML file"""
    config = UnifiedConfig.from_yaml(sample_yaml_config)

    # Verify sections loaded correctly
    assert config.hypothesis.max_concurrent == 5
    assert config.hypothesis.min_hypotheses == 2
    assert config.hypothesis.probability_weight == 0.5

    assert config.worktree.branch_prefix == "hyp"
    assert config.worktree.auto_cleanup is True

    assert config.execution.test_timeout == 300
    assert config.execution.max_concurrent_tests == 5

    assert config.task_splitting.max_concurrent_sessions == 8
    assert config.task_splitting.max_worktrees == 15

    assert config.logging.level == "INFO"


def test_yaml_with_overrides(sample_yaml_config):
    """Test YAML loading with explicit overrides"""
    config = UnifiedConfig.from_yaml(
        sample_yaml_config,
        hypothesis={"max_concurrent": 10}
    )

    # Override should take precedence
    assert config.hypothesis.max_concurrent == 10

    # Other values should come from YAML
    assert config.hypothesis.min_hypotheses == 2


def test_missing_yaml_file():
    """Test handling of missing config file"""
    with pytest.raises(FileNotFoundError):
        UnifiedConfig.from_yaml("nonexistent.yaml")


# ============================================================================
# DICTIONARY CONVERSION TESTS
# ============================================================================

def test_to_dict():
    """Test converting UnifiedConfig to dictionary"""
    config = UnifiedConfig()
    config_dict = config.to_dict()

    assert "hypothesis" in config_dict
    assert "worktree" in config_dict
    assert "execution" in config_dict
    assert "analysis" in config_dict
    assert "task_splitting" in config_dict

    # Verify structure
    assert config_dict["hypothesis"]["max_concurrent"] == 5
    assert config_dict["execution"]["test_timeout"] == 300


def test_from_dict():
    """Test creating UnifiedConfig from dictionary"""
    config_dict = {
        "hypothesis": {
            "max_concurrent": 10,
            "min_hypotheses": 3,
        },
        "execution": {
            "test_timeout": 600,
        }
    }

    config = UnifiedConfig.from_dict(config_dict)

    assert config.hypothesis.max_concurrent == 10
    assert config.hypothesis.min_hypotheses == 3
    assert config.execution.test_timeout == 600


# ============================================================================
# BACKWARD COMPATIBILITY TESTS
# ============================================================================

def test_to_falsification_config():
    """Test converting UnifiedConfig to old FalsificationConfig"""
    unified = UnifiedConfig()
    unified.hypothesis.max_concurrent = 10
    unified.execution.test_timeout = 600

    # Convert to old format
    old_config = unified.to_falsification_config()

    assert isinstance(old_config, FalsificationConfig)
    assert old_config.max_hypotheses == 10
    assert old_config.test_timeout == 600


def test_from_falsification_config():
    """Test creating UnifiedConfig from old FalsificationConfig"""
    # Suppress deprecation warnings for testing
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    old_config = FalsificationConfig(
        max_hypotheses=10,
        test_timeout=600,
        probability_weight=0.6
    )

    # Convert to new format
    unified = UnifiedConfig.from_falsification_config(old_config)

    assert unified.hypothesis.max_concurrent == 10
    assert unified.execution.test_timeout == 600
    assert unified.hypothesis.probability_weight == 0.6


def test_to_parallel_config():
    """Test converting UnifiedConfig to ParallelConfig"""
    unified = UnifiedConfig()
    unified.task_splitting.max_concurrent_sessions = 12
    unified.worktree.creation_time = 10.0

    # Convert to task-splitter format
    parallel_config = unified.to_parallel_config()

    assert parallel_config.max_concurrent_sessions == 12
    assert parallel_config.worktree_creation_time == 10.0


# ============================================================================
# ENVIRONMENT VARIABLE TESTS
# ============================================================================

def test_env_variable_override(monkeypatch):
    """Test environment variable overrides"""
    monkeypatch.setenv("PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT", "15")
    monkeypatch.setenv("PARALLEL_TEST_EXECUTION_TEST_TIMEOUT", "900")

    config = UnifiedConfig()
    env_overrides = UnifiedConfig._load_from_env()

    assert env_overrides["hypothesis"]["max_concurrent"] == 15
    assert env_overrides["execution"]["test_timeout"] == 900


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_full_roundtrip(sample_yaml_config):
    """Test full roundtrip: YAML -> UnifiedConfig -> dict -> UnifiedConfig"""
    # Load from YAML
    config1 = UnifiedConfig.from_yaml(sample_yaml_config)

    # Convert to dict
    config_dict = config1.to_dict()

    # Create from dict
    config2 = UnifiedConfig.from_dict(config_dict)

    # Should be equivalent
    assert config2.hypothesis.max_concurrent == config1.hypothesis.max_concurrent
    assert config2.execution.test_timeout == config1.execution.test_timeout
    assert config2.task_splitting.max_concurrent_sessions == config1.task_splitting.max_concurrent_sessions


def test_validation_on_load(sample_yaml_config):
    """Test that validation runs automatically on load"""
    # Create invalid YAML
    invalid_yaml = """
hypothesis_management:
  max_concurrent: 0  # Invalid: must be >= 1
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_yaml)
        invalid_path = f.name

    # Should raise validation error
    with pytest.raises(ConfigValidationError):
        UnifiedConfig.from_yaml(invalid_path)


def test_load_config_helper(sample_yaml_config):
    """Test convenience load_config function"""
    config = load_config(sample_yaml_config)

    assert isinstance(config, UnifiedConfig)
    assert config.hypothesis.max_concurrent == 5


def test_load_config_without_path(monkeypatch):
    """Test load_config without explicit path (uses defaults)"""
    # Change to temp directory so default paths don't exist
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.chdir(tmpdir)
        config = load_config()

        # Should use default values
        assert isinstance(config, UnifiedConfig)
        assert config.hypothesis.max_concurrent == 5  # Default value


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
