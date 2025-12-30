# Configuration System Migration Guide

**Status**: Active - Migrate to UnifiedConfig by 2025-01-15

## Overview

The parallel orchestrator previously had **three incompatible configuration systems**:

1. `FalsificationConfig` (scripts/parallel_test/config.py) - Flat dataclass
2. `falsification_config.yaml` (config/) - Nested YAML structure
3. `ParallelConfig` (scripts/task-splitter.py) - Task splitting dataclass

These have been **unified into a single system**: `UnifiedConfig` (scripts/parallel_test/unified_config.py)

## Why Migrate?

**Problems with old system:**
- Configuration duplication across 3 files
- Inconsistent naming (e.g., `max_hypotheses` vs `max_concurrent`)
- No single source of truth
- Different structures (flat vs nested)
- Manual syncing required between systems

**Benefits of new system:**
- Single configuration system for all components
- Consistent naming and structure
- Proper validation with clear error messages
- Environment variable support
- Backward compatibility during migration
- Type hints throughout

## Migration Path

### Quick Start (Recommended)

**Old code:**
```python
from scripts.parallel_test.config import FalsificationConfig

config = FalsificationConfig.from_yaml("config/falsification_config.yaml")
print(config.max_hypotheses)
```

**New code:**
```python
from scripts.parallel_test.unified_config import UnifiedConfig

config = UnifiedConfig.from_yaml("config/falsification_config.yaml")
print(config.hypothesis.max_concurrent)  # Note: structured access
```

### Step-by-Step Migration

#### Step 1: Update Imports

**Before:**
```python
from scripts.parallel_test.config import FalsificationConfig
from scripts.task_splitter import ParallelConfig
```

**After:**
```python
from scripts.parallel_test.unified_config import UnifiedConfig
# Old classes still available for compatibility if needed
```

#### Step 2: Update Config Loading

**Before:**
```python
config = FalsificationConfig.from_yaml("config.yaml")
```

**After:**
```python
config = UnifiedConfig.from_yaml("config.yaml")
```

#### Step 3: Update Field Access

The new system uses **structured sections** instead of flat attributes.

**Field Mapping Table:**

| Old (FalsificationConfig) | New (UnifiedConfig) |
|---------------------------|---------------------|
| `max_hypotheses` | `hypothesis.max_concurrent` |
| `min_hypotheses` | `hypothesis.min_hypotheses` |
| `probability_weight` | `hypothesis.probability_weight` |
| `test_timeout` | `execution.test_timeout` |
| `max_concurrent_tests` | `execution.max_concurrent_tests` |
| `worktree_creation_time` | `worktree.creation_time` |
| `use_memory_mcp` | `agent_integration.use_memory_mcp` |
| `session_prefix` | `agent_integration.session_prefix` |

**Before:**
```python
timeout = config.test_timeout
max_hyp = config.max_hypotheses
```

**After:**
```python
timeout = config.execution.test_timeout
max_hyp = config.hypothesis.max_concurrent
```

#### Step 4: Update Backward Compatibility (If Needed)

If you have code that **requires** the old FalsificationConfig format:

```python
# Load as UnifiedConfig
config = UnifiedConfig.from_yaml("config.yaml")

# Convert to old format for legacy code
old_config = config.to_falsification_config()

# Pass to legacy function
legacy_function(old_config)
```

## Configuration Structure

### UnifiedConfig Sections

The new configuration is organized into **9 logical sections**:

```python
@dataclass
class UnifiedConfig:
    hypothesis: HypothesisManagementConfig         # Hypothesis generation and ranking
    worktree: WorktreeConfig                       # Git worktree settings
    execution: ExecutionConfig                     # Test and task execution
    analysis: AnalysisConfig                       # Results analysis
    task_splitting: TaskSplittingConfig            # Parallelization optimization
    agent_integration: AgentIntegrationConfig      # SuperClaude agent settings
    paths: PathsConfig                             # Project paths
    session: SessionConfig                         # Session persistence
    logging: LoggingConfig                         # Logging configuration
```

### Example YAML Configuration

```yaml
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
  use_pool: true
  pool_size: 10

test_execution:
  default_timeout: 300
  max_concurrent_tests: 5
  test_command: "pytest"
  overhead:
    worktree_creation: 8.0
    session_startup: 5.0
    context_building: 20.0

task_splitting:
  max_concurrent_sessions: 8
  max_worktrees: 15
  min_task_time_for_splits:
    2: 5.0
    3: 12.0
    4: 20.0

agent_integration:
  memory_mcp:
    enabled: true
    session_prefix: "falsification"
```

## Environment Variable Overrides

**New feature**: Override any config value with environment variables.

**Pattern**: `PARALLEL_TEST_<SECTION>_<FIELD>=<value>`

**Examples:**
```bash
export PARALLEL_TEST_HYPOTHESIS_MAX_CONCURRENT=10
export PARALLEL_TEST_EXECUTION_TEST_TIMEOUT=600
export PARALLEL_TEST_TASK_MAX_SESSIONS=12
```

**Priority order:**
1. Environment variables (highest)
2. YAML config file
3. Explicit kwargs to `from_yaml()`
4. Default values (lowest)

## Validation

The new system includes **comprehensive validation**:

```python
config = UnifiedConfig()
config.hypothesis.max_concurrent = 0  # Invalid

try:
    config.validate()
except ConfigValidationError as e:
    print(f"Invalid config: {e}")
    # Output: "hypothesis: max_concurrent must be >= 1"
```

**Validation runs automatically** when loading from YAML or creating from dict.

## Common Migration Patterns

### Pattern 1: Simple Script

**Before:**
```python
from scripts.parallel_test.config import FalsificationConfig

config = FalsificationConfig.from_yaml("config.yaml")

def run_tests():
    timeout = config.test_timeout
    max_tests = config.max_concurrent_tests
    # ...
```

**After:**
```python
from scripts.parallel_test.unified_config import UnifiedConfig

config = UnifiedConfig.from_yaml("config.yaml")

def run_tests():
    timeout = config.execution.test_timeout
    max_tests = config.execution.max_concurrent_tests
    # ...
```

### Pattern 2: Class-Based Configuration

**Before:**
```python
class TestRunner:
    def __init__(self, config: FalsificationConfig):
        self.config = config
        self.timeout = config.test_timeout
```

**After:**
```python
class TestRunner:
    def __init__(self, config: UnifiedConfig):
        self.config = config
        self.timeout = config.execution.test_timeout
```

### Pattern 3: Config Passing Between Components

**Before:**
```python
# Component 1: Falsification debugger
falsification_config = FalsificationConfig.from_yaml("config.yaml")

# Component 2: Task splitter (separate config!)
parallel_config = ParallelConfig(
    worktree_creation_time=falsification_config.worktree_creation_time,
    max_concurrent_sessions=8,  # Hardcoded, not synced
    # ...
)
```

**After:**
```python
# Single unified config for all components
config = UnifiedConfig.from_yaml("config.yaml")

# Component 1: Falsification debugger
falsification_runner = FalsificationRunner(config)

# Component 2: Task splitter (same config!)
task_splitter = TaskSplitter(config)

# Both use same source of truth
```

### Pattern 4: Dynamic Configuration

**Before:**
```python
config = FalsificationConfig.from_yaml("config.yaml")
config.test_timeout = 600  # Direct mutation
```

**After:**
```python
config = UnifiedConfig.from_yaml("config.yaml")
config.execution.test_timeout = 600  # Structured mutation
config.validate()  # Optional: re-validate after changes
```

## Backward Compatibility

During the migration period, the old `FalsificationConfig` class is still available but **deprecated**.

### Deprecation Warnings

Using the old class will show warnings:

```python
from scripts.parallel_test.config import FalsificationConfig

config = FalsificationConfig()
# DeprecationWarning: FalsificationConfig is deprecated.
# Use UnifiedConfig from unified_config.py instead.
```

### Converting Between Formats

**Old → New:**
```python
old_config = FalsificationConfig.from_yaml("config.yaml")
new_config = old_config.to_unified()
```

**New → Old:**
```python
new_config = UnifiedConfig.from_yaml("config.yaml")
old_config = new_config.to_falsification_config()
```

## Testing

Run the test suite to verify your migration:

```bash
cd /home/klaus/klauspython/parallel-orchestrator
pytest scripts/parallel_test/test_unified_config.py -v
```

## Migration Checklist

- [ ] Update all imports to use `UnifiedConfig`
- [ ] Update field access to use structured sections
- [ ] Update any custom config loading code
- [ ] Update tests to use new configuration system
- [ ] Remove any hardcoded config values (use YAML or env vars)
- [ ] Run test suite to verify no regressions
- [ ] Update documentation to reference new config structure
- [ ] Remove deprecated `FalsificationConfig` usage (after migration period)

## Timeline

**Phase 1 (Now - 2025-01-15)**: Transition period
- Both systems work side-by-side
- Deprecation warnings guide migration
- Full backward compatibility

**Phase 2 (After 2025-01-15)**: New system only
- Remove deprecated `FalsificationConfig` class
- Remove backward compatibility shims
- UnifiedConfig becomes the single source of truth

## Troubleshooting

### Issue: "ConfigValidationError" on load

**Cause**: Invalid configuration values in YAML file.

**Solution**: Check the error message for specific field and constraint:
```
ConfigValidationError: hypothesis: max_concurrent must be >= 1
```

Fix the YAML file:
```yaml
hypothesis_management:
  max_concurrent: 5  # Was: 0 (invalid)
```

### Issue: "AttributeError: 'UnifiedConfig' object has no attribute 'max_hypotheses'"

**Cause**: Using old flat attribute names instead of structured sections.

**Solution**: Use structured access:
```python
# Wrong: config.max_hypotheses
# Right:  config.hypothesis.max_concurrent
```

### Issue: Can't find config file

**Cause**: YAML file path is incorrect.

**Solution**: Use convenience function to search default locations:
```python
from scripts.parallel_test.unified_config import load_config

config = load_config()  # Auto-finds config in standard locations
```

### Issue: Legacy code requires old format

**Cause**: Third-party or legacy code expects `FalsificationConfig`.

**Solution**: Convert temporarily:
```python
unified_config = UnifiedConfig.from_yaml("config.yaml")
old_format = unified_config.to_falsification_config()
legacy_function(old_format)
```

## Support

For questions or issues during migration:

1. **Check documentation**: `docs/falsification-debugger-architecture.md`
2. **Check examples**: `scripts/parallel_test/test_unified_config.py`
3. **Review code**: `scripts/parallel_test/unified_config.py` (heavily commented)

## Summary

**Key Changes:**

| Aspect | Old System | New System |
|--------|-----------|------------|
| **Files** | 3 separate configs | 1 unified config |
| **Structure** | Flat attributes | Organized sections |
| **Validation** | Manual/none | Automatic with clear errors |
| **Env vars** | Not supported | Full support |
| **Type hints** | Partial | Complete |
| **Backward compat** | N/A | Full during migration |

**Migration is straightforward**: Update imports and use structured field access. The system handles the rest.
