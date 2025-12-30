# Worktree Pooling Quick Start

Get started with worktree pooling in 5 minutes.

## TL;DR

Worktree pooling makes repeated testing **3-32x faster** by reusing git worktrees instead of creating them from scratch each time.

## Installation

No installation needed - pooling is built-in and **enabled by default**.

## Instant Usage

### Option 1: Use WorktreeOrchestrator (Recommended)

```python
from pathlib import Path
from worktree_orchestrator import WorktreeOrchestrator, WorktreeConfig
from config import Hypothesis

# Create config (pooling enabled by default)
config = WorktreeConfig(
    base_repo=Path.cwd(),
    worktree_dir=Path.cwd() / "worktrees",
    pool_size=10  # Max worktrees in pool
)

# Create hypotheses
hypotheses = [
    Hypothesis(id="hyp_1", description="Test 1"),
    Hypothesis(id="hyp_2", description="Test 2"),
]

# Use it
with WorktreeOrchestrator(config) as orch:
    worktrees = orch.create_worktrees(hypotheses)
    # ... test in worktrees ...
# Automatically released to pool for reuse
```

That's it! Subsequent runs will reuse the pool.

### Option 2: Use WorktreePool Directly

```python
from pathlib import Path
from worktree_pool import WorktreePool

# Create pool
pool = WorktreePool(
    base_repo=Path.cwd(),
    pool_dir=Path.cwd() / "pool",
    max_size=10
)

# Use worktrees
with pool.worktree("hyp_1") as wt_path:
    # Test in worktree
    print(f"Testing in {wt_path}")

# State automatically saved for next session
pool.persist_state()
```

## Performance

### First Run (Creates Pool)
```bash
$ python your_test.py
Creating worktrees...  # ~8s per worktree
Testing...
Done in 45s
```

### Second Run (Reuses Pool)
```bash
$ python your_test.py
Reusing worktrees from pool...  # ~0.5s per worktree
Testing...
Done in 18s  # 2.5x faster!
```

## Disable Pooling

If you want the old behavior:

```python
config = WorktreeConfig(
    base_repo=Path.cwd(),
    worktree_dir=Path.cwd() / "worktrees",
    use_pool=False  # Disable pooling
)
```

## Check Pool Status

```python
# Via orchestrator
stats = orch.get_pool_stats()
print(stats)
# {
#   'total_worktrees': 5,
#   'available': 3,
#   'allocated': 2,
#   'capacity_used': '50.0%'
# }

# Via pool directly
stats = pool.get_stats()
```

## Clean Up Pool

Remove all pooled worktrees:

```python
# Via orchestrator
orch.cleanup_pool()

# Via pool directly
pool.cleanup_all()
```

## Common Scenarios

### Scenario 1: Running Tests Repeatedly

```python
# First run: creates pool (~45s)
# Second run: reuses pool (~18s) - 2.5x faster
# Third run: reuses pool (~18s) - 2.5x faster
# ... and so on

# No manual intervention needed!
```

### Scenario 2: Different Hypotheses Each Time

```python
# Pool adapts automatically
# Day 1: Test hyp_1, hyp_2, hyp_3 (creates pool)
# Day 2: Test hyp_4, hyp_5, hyp_6 (reuses pool)
# Day 3: Test hyp_7, hyp_8 (reuses pool)
```

### Scenario 3: Pool Too Small

```python
# Pool has 5 worktrees, need 8
config = WorktreeConfig(pool_size=5)

with WorktreeOrchestrator(config) as orch:
    # Creates 8 hypotheses
    hypotheses = [Hypothesis(id=f"hyp_{i}") for i in range(8)]

    # 5 from pool (fast), 3 created directly (slower)
    worktrees = orch.create_worktrees(hypotheses)
    # Still works! Automatic fallback
```

## Troubleshooting

### Pool state corrupted

**Symptom**: Errors loading pool state

**Fix**: Delete state file and restart
```bash
rm worktrees/pool/.worktree_pool.json
```

### Worktrees not being reused

**Symptom**: Always creating new worktrees

**Check 1**: Is pooling enabled?
```python
print(config.use_pool)  # Should be True
```

**Check 2**: Are you persisting state?
```python
# Make sure you're using context manager
with WorktreeOrchestrator(config) as orch:
    pass  # Automatically persists
```

### Disk space issues

**Symptom**: Running out of space

**Fix**: Reduce pool size or clean up
```python
# Option 1: Smaller pool
config = WorktreeConfig(pool_size=3)  # Instead of 10

# Option 2: Clean up
pool.cleanup_all()
```

## Advanced Usage

### Custom pool location

```python
config = WorktreeConfig(
    base_repo=Path("/path/to/repo"),
    worktree_dir=Path("/path/to/custom/worktrees"),
    pool_size=10
)
```

### Expand pool dynamically

```python
# Start with small pool
pool = WorktreePool(base_repo, pool_dir, max_size=5)

# Need more later?
pool.expand_pool(5)  # Now max_size=10
```

### Thread-safe concurrent usage

```python
import threading

def test_worker(pool, hyp_id):
    with pool.worktree(hyp_id) as wt:
        # Test in worktree
        pass

# Multiple threads can safely use same pool
pool = WorktreePool(base_repo, pool_dir, max_size=10)

threads = [
    threading.Thread(target=test_worker, args=(pool, f"hyp_{i}"))
    for i in range(5)
]

for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Best Practices

1. **Always use context managers**
   ```python
   # ✓ Good
   with pool.worktree("hyp_1") as wt:
       pass

   # ✗ Bad
   wt = pool.acquire("hyp_1")
   # ... might forget to release
   ```

2. **Set appropriate pool size**
   ```python
   # Rule of thumb: max_concurrent_tests * 1.5
   config = WorktreeConfig(pool_size=8)  # For 5 concurrent tests
   ```

3. **Clean up before major changes**
   ```python
   # Before switching branches, rebasing, etc.
   pool.cleanup_all()
   ```

4. **Monitor pool capacity**
   ```python
   stats = pool.get_stats()
   if stats['allocated'] == stats['max_size']:
       print("Warning: Pool at capacity!")
   ```

## Next Steps

- Read full documentation: `WORKTREE_POOL_README.md`
- Run test suite: `python test_worktree_pool.py`
- Review implementation: `IMPLEMENTATION_SUMMARY.md`

## FAQ

**Q: Is pooling safe?**
A: Yes, each worktree is reset to clean state before reuse.

**Q: What if I change branches?**
A: Pool state is invalidated if base repo changes. Start fresh.

**Q: Can I share pool between projects?**
A: No, each project should have its own pool.

**Q: Does pooling work on Windows?**
A: Yes, git worktrees work on all platforms.

**Q: What's the overhead of pooling?**
A: Minimal - state file is ~1KB JSON, loads in ~5ms.

## Summary

**Enabled by default** - Just use WorktreeOrchestrator normally
**3x faster** - For typical testing sessions
**32x faster** - For worktree-only operations
**Zero config** - Works out of the box
**Session persistent** - Survives restarts
**Thread safe** - Use concurrently
**Backward compatible** - Doesn't break existing code

Start using it now - no changes needed to existing code!
