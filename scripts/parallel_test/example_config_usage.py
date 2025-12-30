#!/usr/bin/env python3
"""
Example: Using the Unified Configuration System

Demonstrates loading, validating, and using the unified configuration
across different components of the parallel orchestrator.
"""

from unified_config import UnifiedConfig, load_config, ConfigValidationError
from pathlib import Path


def example_1_basic_loading():
    """Example 1: Basic configuration loading"""
    print("\n=== Example 1: Basic Loading ===")

    # Load from default location
    config = load_config("../../config/falsification_config.yaml")

    # Access structured configuration
    print(f"Max concurrent hypotheses: {config.hypothesis.max_concurrent}")
    print(f"Test timeout: {config.execution.test_timeout}s")
    print(f"Worktree base dir: {config.worktree.base_dir}")
    print(f"Max parallel sessions: {config.task_splitting.max_concurrent_sessions}")


def example_2_validation():
    """Example 2: Configuration validation"""
    print("\n=== Example 2: Validation ===")

    # Create config with defaults
    config = UnifiedConfig()

    # Modify a value
    config.hypothesis.max_concurrent = 10

    # Validate (should pass)
    try:
        config.validate()
        print("✓ Configuration is valid")
    except ConfigValidationError as e:
        print(f"✗ Validation failed: {e}")

    # Try invalid configuration
    config.hypothesis.max_concurrent = 0  # Invalid: must be >= 1

    try:
        config.validate()
    except ConfigValidationError as e:
        print(f"✓ Caught invalid config: {e}")


def example_3_environment_overrides():
    """Example 3: Environment variable overrides"""
    print("\n=== Example 3: Environment Overrides ===")

    import os

    # Set environment variables
    os.environ["PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT"] = "15"
    os.environ["PARALLEL_TEST_EXECUTION_TEST_TIMEOUT"] = "900"

    # Load config (env vars will override YAML values)
    config = load_config("../../config/falsification_config.yaml")

    print(f"Max concurrent (from env): {config.hypothesis.max_concurrent}")
    print(f"Test timeout (from env): {config.execution.test_timeout}s")

    # Clean up
    del os.environ["PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT"]
    del os.environ["PARALLEL_TEST_EXECUTION_TEST_TIMEOUT"]


def example_4_explicit_overrides():
    """Example 4: Explicit overrides via kwargs"""
    print("\n=== Example 4: Explicit Overrides ===")

    # Load with explicit overrides
    config = UnifiedConfig.from_yaml(
        "../../config/falsification_config.yaml",
        hypothesis={"max_concurrent": 20},
        execution={"test_timeout": 1200}
    )

    print(f"Max concurrent (override): {config.hypothesis.max_concurrent}")
    print(f"Test timeout (override): {config.execution.test_timeout}s")


def example_5_convert_to_dict():
    """Example 5: Converting to dictionary"""
    print("\n=== Example 5: Dictionary Conversion ===")

    config = load_config("../../config/falsification_config.yaml")

    # Convert to dictionary
    config_dict = config.to_dict()

    print(f"Config as dict keys: {list(config_dict.keys())}")
    print(f"Hypothesis section: {config_dict['hypothesis']}")


def example_6_backward_compatibility():
    """Example 6: Backward compatibility with old system"""
    print("\n=== Example 6: Backward Compatibility ===")

    # Load as UnifiedConfig
    unified_config = load_config("../../config/falsification_config.yaml")

    # Convert to old FalsificationConfig format
    old_config = unified_config.to_falsification_config()

    print(f"Old format - max_hypotheses: {old_config.max_hypotheses}")
    print(f"Old format - test_timeout: {old_config.test_timeout}s")

    # Convert back to UnifiedConfig
    unified_again = old_config.to_unified()

    print(f"Unified again - max_concurrent: {unified_again.hypothesis.max_concurrent}")


def example_7_task_splitting_config():
    """Example 7: Using task splitting configuration"""
    print("\n=== Example 7: Task Splitting Config ===")

    config = load_config("../../config/falsification_config.yaml")

    # Access task splitting settings
    print(f"Max concurrent sessions: {config.task_splitting.max_concurrent_sessions}")
    print(f"Max worktrees: {config.task_splitting.max_worktrees}")
    print(f"Break-even thresholds:")
    for num_splits, min_time in config.task_splitting.min_task_time_for_splits.items():
        print(f"  {num_splits} splits: >{min_time} min")

    # Convert to ParallelConfig for task-splitter.py
    parallel_config = config.to_parallel_config()
    print(f"\nParallelConfig - worktree creation time: {parallel_config.worktree_creation_time}s")


def example_8_comprehensive_workflow():
    """Example 8: Comprehensive workflow simulation"""
    print("\n=== Example 8: Comprehensive Workflow ===")

    # Load configuration
    config = load_config("../../config/falsification_config.yaml")

    # Simulate falsification debugger workflow
    print("\n1. Hypothesis Management:")
    print(f"   - Generate up to {config.hypothesis.max_concurrent} hypotheses")
    print(f"   - Ranking weights: P={config.hypothesis.probability_weight}, "
          f"I={config.hypothesis.impact_weight}, C={config.hypothesis.complexity_weight}")

    # Simulate worktree orchestration
    print("\n2. Worktree Setup:")
    print(f"   - Base directory: {config.worktree.base_dir}")
    print(f"   - Branch prefix: {config.worktree.branch_prefix}")
    print(f"   - Pool size: {config.worktree.pool_size}")
    print(f"   - Creation overhead: {config.worktree.creation_time}s per worktree")

    # Simulate test execution
    print("\n3. Test Execution:")
    print(f"   - Timeout: {config.execution.test_timeout}s")
    print(f"   - Max concurrent tests: {config.execution.max_concurrent_tests}")
    print(f"   - Test command: {config.execution.test_command}")

    # Calculate total overhead
    total_overhead = (
        config.worktree.creation_time +
        config.execution.session_startup_time +
        config.execution.context_building_time +
        config.execution.environment_setup_time
    )
    print(f"\n4. Overhead Analysis:")
    print(f"   - Total setup time: {total_overhead:.1f}s")
    print(f"   - Merge time per branch: {config.execution.merge_time_per_branch}s")

    # Simulate results analysis
    print("\n5. Results Analysis:")
    print(f"   - Confidence threshold: {config.analysis.confidence_threshold}")
    print(f"   - Report format: {config.analysis.report_formats[0]}")
    print(f"   - Session persistence: {config.analysis.session_persistence}")

    # Agent integration
    print("\n6. Agent Integration:")
    agents = []
    if config.agent_integration.use_root_cause_analyst:
        agents.append("root-cause-analyst")
    if config.agent_integration.use_sequential_thinking:
        agents.append("sequential-thinking")
    if config.agent_integration.use_quality_engineer:
        agents.append("quality-engineer")
    print(f"   - Active agents: {', '.join(agents)}")
    print(f"   - Memory MCP enabled: {config.agent_integration.use_memory_mcp}")


def example_9_create_custom_config():
    """Example 9: Creating custom configuration programmatically"""
    print("\n=== Example 9: Custom Configuration ===")

    from unified_config import (
        HypothesisManagementConfig,
        WorktreeConfig,
        ExecutionConfig,
    )

    # Create custom configuration
    config = UnifiedConfig(
        hypothesis=HypothesisManagementConfig(
            max_concurrent=3,
            min_hypotheses=1,
            probability_weight=0.6,
            impact_weight=0.3,
            complexity_weight=-0.1
        ),
        worktree=WorktreeConfig(
            base_dir=Path("/tmp/worktrees"),
            branch_prefix="test",
            auto_cleanup=False
        ),
        execution=ExecutionConfig(
            test_timeout=120,
            max_concurrent_tests=3,
            test_command="pytest -v"
        )
    )

    # Validate
    config.validate()

    print("✓ Custom configuration created and validated")
    print(f"  Max hypotheses: {config.hypothesis.max_concurrent}")
    print(f"  Worktree dir: {config.worktree.base_dir}")
    print(f"  Test timeout: {config.execution.test_timeout}s")


def main():
    """Run all examples"""
    print("=" * 60)
    print("UNIFIED CONFIGURATION SYSTEM - EXAMPLES")
    print("=" * 60)

    try:
        example_1_basic_loading()
        example_2_validation()
        example_3_environment_overrides()
        example_4_explicit_overrides()
        example_5_convert_to_dict()
        example_6_backward_compatibility()
        example_7_task_splitting_config()
        example_8_comprehensive_workflow()
        example_9_create_custom_config()

        print("\n" + "=" * 60)
        print("✓ All examples completed successfully")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
