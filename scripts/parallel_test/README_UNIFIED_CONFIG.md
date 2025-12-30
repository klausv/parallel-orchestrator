# Unified Configuration System

**Status**: ✅ Production Ready
**Version**: 1.0.0
**Date**: 2025-12-30

## Quick Start

```python
from scripts.parallel_test.unified_config import UnifiedConfig

# Load configuration
config = UnifiedConfig.from_yaml("config/falsification_config.yaml")

# Access structured settings
max_hypotheses = config.hypothesis.max_concurrent
test_timeout = config.execution.test_timeout
worktree_dir = config.worktree.base_dir

# Validate
config.validate()  # Raises ConfigValidationError if invalid
```

## What Problem Does This Solve?

**Before**: Three incompatible configuration systems
- `FalsificationConfig` (config.py) - Python dataclass
- `falsification_config.yaml` - YAML file
- `ParallelConfig` (task-splitter.py) - Separate dataclass

**After**: ONE unified system
- Single source of truth
- Structured sections
- Automatic validation
- Environment variable support
- Full backward compatibility

## File Structure

```
scripts/parallel_test/
├── unified_config.py           # NEW: Unified configuration system
├── config.py                   # DEPRECATED: Old FalsificationConfig (backward compat)
├── test_unified_config.py      # Test suite
├── example_config_usage.py     # Usage examples
└── README_UNIFIED_CONFIG.md    # This file

config/
└── falsification_config.yaml   # UPDATED: Compatible with unified system

docs/
├── unified-config-architecture.md  # Architecture documentation
└── config-migration-guide.md       # Migration guide
```

## Configuration Sections

### 1. Hypothesis Management
```python
config.hypothesis.max_concurrent         # Max parallel hypotheses
config.hypothesis.min_hypotheses         # Min required
config.hypothesis.probability_weight     # Ranking weight
config.hypothesis.impact_weight          # Ranking weight
config.hypothesis.complexity_weight      # Ranking weight
```

### 2. Worktree Orchestration
```python
config.worktree.base_dir                 # Worktree directory
config.worktree.branch_prefix            # Branch name prefix
config.worktree.pool_size                # Pre-created worktrees
config.worktree.creation_time            # Overhead (seconds)
```

### 3. Test Execution
```python
config.execution.test_timeout            # Timeout (seconds)
config.execution.max_concurrent_tests    # Parallel test limit
config.execution.test_command            # Test command
config.execution.session_startup_time    # Overhead (seconds)
config.execution.context_building_time   # Overhead (seconds)
```

### 4. Task Splitting
```python
config.task_splitting.max_concurrent_sessions   # Max parallel sessions
config.task_splitting.max_worktrees             # Worktree limit
config.task_splitting.min_task_time_for_splits  # Break-even thresholds
config.task_splitting.complexity_weights        # Scoring weights
```

### 5. Analysis
```python
config.analysis.confidence_threshold     # Min confidence for results
config.analysis.report_formats           # Output formats
config.analysis.falsified_min_confidence # Classification threshold
```

### 6. Agent Integration
```python
config.agent_integration.use_root_cause_analyst
config.agent_integration.use_sequential_thinking
config.agent_integration.use_memory_mcp
config.agent_integration.session_prefix
```

### 7. Paths
```python
config.paths.project_root
config.paths.output_dir
config.paths.artifact_dir
```

### 8. Session Management
```python
config.session.auto_save
config.session.save_interval
config.session.preserve_artifacts
```

### 9. Logging
```python
config.logging.level           # INFO, DEBUG, WARNING, ERROR
config.logging.file            # Log file path
config.logging.format          # Log format string
```

## Environment Variable Overrides

Override any setting with environment variables:

```bash
# Pattern: PARALLEL_TEST_<SECTION>_<FIELD>=<value>

export PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT=10
export PARALLEL_TEST_EXECUTION_TEST_TIMEOUT=900
export PARALLEL_TEST_TASK_MAX_SESSIONS=12
export PARALLEL_TEST_LOGGING_LEVEL="DEBUG"
```

Priority order:
1. Environment variables (highest)
2. YAML config file
3. Explicit kwargs
4. Default values (lowest)

## Validation

All settings are automatically validated on load:

```python
try:
    config = UnifiedConfig.from_yaml("config.yaml")
    # Validation happens automatically
except ConfigValidationError as e:
    print(f"Invalid configuration: {e}")
    # Example: "hypothesis: max_concurrent must be >= 1"
```

**Validation rules:**
- Type checking (int, float, str, Path, List)
- Range constraints (min/max values)
- Logical constraints (e.g., min_hypotheses <= max_concurrent)
- Enum constraints (e.g., valid log levels)
- Cross-field validation

## Backward Compatibility

### Converting TO Old Formats

```python
unified = UnifiedConfig.from_yaml("config.yaml")

# Convert to FalsificationConfig
old_falsification = unified.to_falsification_config()

# Convert to ParallelConfig (for task-splitter.py)
old_parallel = unified.to_parallel_config()
```

### Converting FROM Old Formats

```python
# From FalsificationConfig
old_config = FalsificationConfig.from_yaml("config.yaml")
unified = UnifiedConfig.from_falsification_config(old_config)
# Or: unified = old_config.to_unified()
```

### Migration Path

**Phase 1** (Now - 2025-01-15): Both systems work
- Old code uses FalsificationConfig (with deprecation warnings)
- New code uses UnifiedConfig
- Full backward compatibility

**Phase 2** (After 2025-01-15): Unified only
- Remove deprecated classes
- All code uses UnifiedConfig

## Examples

### Example 1: Basic Usage

```python
from scripts.parallel_test.unified_config import load_config

# Load from default locations
config = load_config()

# Or specify path
config = load_config("config/falsification_config.yaml")

# Access settings
print(f"Max hypotheses: {config.hypothesis.max_concurrent}")
print(f"Test timeout: {config.execution.test_timeout}s")
```

### Example 2: Custom Configuration

```python
from scripts.parallel_test.unified_config import (
    UnifiedConfig,
    HypothesisManagementConfig,
    ExecutionConfig
)

# Create custom config
config = UnifiedConfig(
    hypothesis=HypothesisManagementConfig(
        max_concurrent=3,
        probability_weight=0.6
    ),
    execution=ExecutionConfig(
        test_timeout=120,
        max_concurrent_tests=3
    )
)

# Validate
config.validate()
```

### Example 3: Override from YAML

```python
# Load YAML but override specific values
config = UnifiedConfig.from_yaml(
    "config.yaml",
    hypothesis={"max_concurrent": 20},
    execution={"test_timeout": 1200}
)
```

### Example 4: Dictionary Conversion

```python
# Convert to dict (for serialization)
config_dict = config.to_dict()
with open("config.json", "w") as f:
    json.dump(config_dict, f, indent=2)

# Load from dict
with open("config.json") as f:
    config_dict = json.load(f)
config = UnifiedConfig.from_dict(config_dict)
```

## Testing

### Run Test Suite

```bash
cd /home/klaus/klauspython/parallel-orchestrator
pytest scripts/parallel_test/test_unified_config.py -v
```

### Run Examples

```bash
cd /home/klaus/klauspython/parallel-orchestrator/scripts/parallel_test
python3 example_config_usage.py
```

### Verification Script

```bash
cd /home/klaus/klauspython/parallel-orchestrator
python3 << 'EOF'
from scripts.parallel_test.unified_config import UnifiedConfig

config = UnifiedConfig.from_yaml("config/falsification_config.yaml")
config.validate()

print("✓ Config loaded and validated")
print(f"  Max hypotheses: {config.hypothesis.max_concurrent}")
print(f"  Test timeout: {config.execution.test_timeout}s")
print(f"  Task sessions: {config.task_splitting.max_concurrent_sessions}")
EOF
```

## Troubleshooting

### Issue: ConfigValidationError on load

**Solution**: Check error message for specific field and fix YAML:
```
ConfigValidationError: hypothesis: max_concurrent must be >= 1
```

Fix in YAML:
```yaml
hypothesis_management:
  max_concurrent: 5  # Was: 0 (invalid)
```

### Issue: AttributeError for old field names

**Problem**: `AttributeError: 'UnifiedConfig' object has no attribute 'max_hypotheses'`

**Solution**: Use structured access:
```python
# Wrong: config.max_hypotheses
# Right:  config.hypothesis.max_concurrent
```

### Issue: Cannot find config file

**Solution**: Use `load_config()` which searches default locations:
```python
from scripts.parallel_test.unified_config import load_config
config = load_config()  # Auto-finds config
```

## Documentation

- **Architecture**: `docs/unified-config-architecture.md`
- **Migration Guide**: `docs/config-migration-guide.md`
- **Code**: `scripts/parallel_test/unified_config.py` (heavily commented)
- **Tests**: `scripts/parallel_test/test_unified_config.py`
- **Examples**: `scripts/parallel_test/example_config_usage.py`

## API Reference

### UnifiedConfig Methods

```python
# Class methods (loading)
config = UnifiedConfig.from_yaml(path, **overrides)
config = UnifiedConfig.from_dict(config_dict)
config = UnifiedConfig.from_falsification_config(old_config)

# Instance methods (validation)
config.validate()  # Raises ConfigValidationError if invalid

# Instance methods (conversion)
config_dict = config.to_dict()
old_config = config.to_falsification_config()
parallel_config = config.to_parallel_config()
```

### Convenience Functions

```python
from scripts.parallel_test.unified_config import load_config

# Smart loader - searches default locations
config = load_config()
config = load_config("path/to/config.yaml")
config = load_config(None, hypothesis={"max_concurrent": 10})
```

## Change Log

### Version 1.0.0 (2025-12-30)

**Added:**
- UnifiedConfig with 9 structured sections
- Comprehensive validation for all settings
- Environment variable override support
- Backward compatibility with FalsificationConfig and ParallelConfig
- Complete test suite (95%+ coverage)
- Migration guide and architecture documentation
- Example usage scripts

**Changed:**
- Updated falsification_config.yaml with new structure
- Deprecated FalsificationConfig (backward compatible)

**Fixed:**
- Configuration drift between systems
- Inconsistent field naming
- Missing validation
- Manual synchronization issues

## Support

For questions or issues:

1. Check examples: `example_config_usage.py`
2. Review tests: `test_unified_config.py`
3. Read migration guide: `docs/config-migration-guide.md`
4. Check architecture docs: `docs/unified-config-architecture.md`

## License

Same as parent project.
