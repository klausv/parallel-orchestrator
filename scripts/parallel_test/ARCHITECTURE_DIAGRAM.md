# Worktree Pool Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Parallel Testing System                         │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              User Code / Test Runner                          │ │
│  └───────────────────────┬───────────────────────────────────────┘ │
│                          │                                          │
│                          ↓                                          │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │           WorktreeOrchestrator (High-Level API)               │ │
│  │  • create_worktrees(hypotheses)                               │ │
│  │  • setup_test_environment(worktree, hypothesis)               │ │
│  │  • cleanup_worktrees(hypothesis_ids)                          │ │
│  │  • get_pool_stats()                                           │ │
│  └───────────────────────┬───────────────────────────────────────┘ │
│                          │                                          │
│              ┌───────────┴───────────┐                              │
│              │                       │                              │
│              ↓                       ↓                              │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │  WorktreePool        │  │  Direct Mode         │                │
│  │  (Pooled Mode)       │  │  (Legacy)            │                │
│  │  • acquire()         │  │  • _create_direct()  │                │
│  │  • release()         │  │  • git worktree add  │                │
│  │  • persist_state()   │  │  • git worktree rm   │                │
│  │  • load_state()      │  │                      │                │
│  └──────────┬───────────┘  └──────────────────────┘                │
│             │                                                       │
│             ↓                                                       │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Shared Git Utils (shared/git_utils.py)           │ │
│  │  • create_worktree(repo, path, branch)                        │ │
│  │  • remove_worktree(repo, path, force)                         │ │
│  │  • reset_worktree(path)                                       │ │
│  │  • get_current_branch(repo)                                   │ │
│  └───────────────────────┬───────────────────────────────────────┘ │
│                          │                                          │
│                          ↓                                          │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    Git Subprocess Calls                       │ │
│  │  • git worktree add                                           │ │
│  │  • git worktree remove                                        │ │
│  │  • git checkout HEAD -- .                                     │ │
│  │  • git clean -fd                                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## WorktreePool State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                     WorktreePool State                          │
│                                                                 │
│  ┌────────────┐                                                 │
│  │  Initial   │                                                 │
│  │  State     │                                                 │
│  └─────┬──────┘                                                 │
│        │                                                        │
│        │ auto_load=True?                                        │
│        │                                                        │
│    YES │           NO                                           │
│        ↓            ↓                                           │
│  ┌─────────────┐  ┌─────────────┐                              │
│  │ load_state()│  │ Empty Pool  │                              │
│  │ from JSON   │  │             │                              │
│  └─────┬───────┘  └─────┬───────┘                              │
│        │                 │                                      │
│        └────────┬────────┘                                      │
│                 │                                               │
│                 ↓                                               │
│        ┌─────────────────┐                                      │
│        │  Pool Ready     │←────────────┐                        │
│        │  (available +   │             │                        │
│        │   allocated)    │             │                        │
│        └────────┬────────┘             │                        │
│                 │                      │                        │
│         acquire("hyp_1")               │                        │
│                 │                      │                        │
│                 ↓                      │                        │
│        ┌─────────────────┐             │                        │
│        │ Available?      │             │                        │
│        └────────┬────────┘             │                        │
│          YES │      │ NO               │                        │
│              │      │                  │                        │
│              │      ↓                  │                        │
│              │  ┌────────────────┐    │                        │
│              │  │ < max_size?    │    │                        │
│              │  └───┬────────┬───┘    │                        │
│              │   YES│     NO │         │                        │
│              │      │        │         │                        │
│              │      ↓        ↓         │                        │
│              │  ┌────────┐ ┌──────┐   │                        │
│              │  │ Create │ │Error │   │                        │
│              │  │  New   │ └──────┘   │                        │
│              │  └───┬────┘            │                        │
│              │      │                 │                        │
│              └──────┼─────────────────┘                        │
│                     │                                          │
│                     ↓                                          │
│              ┌──────────────┐                                  │
│              │ Reset to     │                                  │
│              │ Clean State  │                                  │
│              └──────┬───────┘                                  │
│                     │                                          │
│                     ↓                                          │
│              ┌──────────────┐                                  │
│              │ Mark as      │                                  │
│              │ Allocated    │                                  │
│              └──────┬───────┘                                  │
│                     │                                          │
│                     ↓                                          │
│              ┌──────────────┐                                  │
│              │ Return Path  │                                  │
│              └──────────────┘                                  │
│                                                                │
│  release("hyp_1")                                              │
│         │                                                      │
│         ↓                                                      │
│  ┌──────────────┐                                              │
│  │ Move to      │                                              │
│  │ Available    │──────────────────────────┐                   │
│  └──────────────┘                          │                   │
│                                            │                   │
│  persist_state()                           │                   │
│         │                                  │                   │
│         ↓                                  │                   │
│  ┌──────────────┐                          │                   │
│  │ Save JSON    │                          │                   │
│  └──────────────┘                          │                   │
│                                            ↓                   │
│                                    ┌──────────────┐            │
│                                    │ Pool Ready   │            │
│                                    │ (next use)   │            │
│                                    └──────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

## Performance Flow Comparison

### Direct Mode (No Pooling)

```
Session 1:                          Time
┌─────────────────────────────┐
│ create_worktree("hyp_1")    │    ~8s
│  ↓ git worktree add         │
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ setup_test_environment()    │    ~5s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ run_tests()                 │    ~30s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ cleanup_worktree()          │    ~3s
│  ↓ git worktree remove      │
└─────────────────────────────┘
         │
         ↓
     Total: ~46s


Session 2:                          Time
┌─────────────────────────────┐
│ create_worktree("hyp_1")    │    ~8s  ← Same overhead!
│  ↓ git worktree add         │
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ setup_test_environment()    │    ~5s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ run_tests()                 │    ~30s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ cleanup_worktree()          │    ~3s
│  ↓ git worktree remove      │
└─────────────────────────────┘
         │
         ↓
     Total: ~46s  (No improvement)
```

### Pooled Mode (With Pooling)

```
Session 1:                          Time
┌─────────────────────────────┐
│ pool.acquire("hyp_1")       │
│  ↓ Available? NO            │
│  ↓ create_worktree()        │    ~8s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ setup_test_environment()    │    ~5s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ run_tests()                 │    ~30s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ pool.release("hyp_1")       │    ~0s
│  ↓ Keep in pool             │
└─────────────────────────────┘
         │
         ↓
     Total: ~43s


Session 2:                          Time
┌─────────────────────────────┐
│ pool.acquire("hyp_1")       │
│  ↓ Available? YES           │
│  ↓ reset_worktree()         │    ~0.5s ← 16x faster!
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ setup_test_environment()    │    ~5s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ run_tests()                 │    ~30s
└─────────────────────────────┘
         │
         ↓
┌─────────────────────────────┐
│ pool.release("hyp_1")       │    ~0s
│  ↓ Keep in pool             │
└─────────────────────────────┘
         │
         ↓
     Total: ~35.5s  (23% faster)
```

## Pool State File Structure

```
.worktree_pool.json
{
  "pool_dir": "/path/to/pool",
  "base_repo": "/path/to/repo",
  "max_size": 10,
  "available_worktrees": [      ← Free for reuse
    "pool-wt-000",
    "pool-wt-001",
    "pool-wt-002"
  ],
  "allocated_worktrees": {      ← Currently in use
    "hyp_1": "pool-wt-003",
    "hyp_2": "pool-wt-004"
  },
  "total_worktrees": 5
}

Pool Directory Structure:
pool/
├── .worktree_pool.json        ← State file
├── pool-wt-000/               ← Worktree 0 (available)
├── pool-wt-001/               ← Worktree 1 (available)
├── pool-wt-002/               ← Worktree 2 (available)
├── pool-wt-003/               ← Worktree 3 (allocated to hyp_1)
└── pool-wt-004/               ← Worktree 4 (allocated to hyp_2)
```

## Thread Safety Model

```
┌─────────────────────────────────────────────────────┐
│            WorktreePool (Thread-Safe)               │
│                                                     │
│  ┌───────────────────────────────────────────────┐ │
│  │         threading.Lock (_lock)                │ │
│  │                                               │ │
│  │  ┌─────────────────────────────────────────┐ │ │
│  │  │  Protected State:                       │ │ │
│  │  │  • _available (Set[str])                │ │ │
│  │  │  • _allocated (Dict[str, str])          │ │ │
│  │  │  • _worktree_paths (Dict[str, Path])    │ │ │
│  │  │  • _total_created (int)                 │ │ │
│  │  └─────────────────────────────────────────┘ │ │
│  │                                               │ │
│  │  Thread A              Thread B              │ │
│  │     │                     │                  │ │
│  │     ↓                     ↓                  │ │
│  │  acquire()             acquire()             │ │
│  │     │                     │                  │ │
│  │     ├──→ Lock ←───────────┤                  │ │
│  │     │                     │ (waits)          │ │
│  │     ↓                     │                  │ │
│  │  Get worktree             │                  │ │
│  │  Update state             │                  │ │
│  │     │                     │                  │ │
│  │     ├──→ Unlock           │                  │ │
│  │     │                     ↓                  │ │
│  │     ↓                  Lock acquired         │ │
│  │  Return path          Get worktree           │ │
│  │                       Update state           │ │
│  │                          │                   │ │
│  │                       Unlock                 │ │
│  │                       Return path            │ │
│  └───────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘

All public methods protected:
• acquire()
• release()
• expand_pool()
• shrink_pool()
• persist_state()
• load_state()
• cleanup_all()
• get_stats()
```

## Error Handling Flow

```
acquire("hyp_1")
    │
    ↓
┌────────────────┐
│ Get from       │
│ available?     │
└───┬────────────┘
    │ NO
    ↓
┌────────────────┐      NO      ┌────────────────┐
│ Can create?    │─────────────→│ Raise          │
│ < max_size?    │              │ RuntimeError   │
└───┬────────────┘              └────────────────┘
    │ YES
    ↓
┌────────────────┐
│ create_        │
│ worktree()     │
└───┬────────────┘
    │
    ↓
┌────────────────┐    FAIL     ┌────────────────┐
│ reset_         │────────────→│ Attempt        │
│ worktree()     │             │ recreate       │
└───┬────────────┘             └───┬────────────┘
    │ SUCCESS                      │
    │                              │
    └──────────┬───────────────────┘
               │
               ↓
        ┌─────────────┐
        │ Mark as     │
        │ allocated   │
        └──────┬──────┘
               │
               ↓
        ┌─────────────┐
        │ Return path │
        └─────────────┘
```

## Integration with Orchestrator

```
┌──────────────────────────────────────────────────────────┐
│              WorktreeOrchestrator                        │
│                                                          │
│  config.use_pool = True                                  │
│          │                                               │
│          ↓                                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ __init__()                                        │  │
│  │   ↓                                               │  │
│  │ Create WorktreePool instance                      │  │
│  │   pool = WorktreePool(config.base_repo, ...)      │  │
│  └───────────────────────────────────────────────────┘  │
│          │                                               │
│          ↓                                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ create_worktrees(hypotheses)                      │  │
│  │   ↓                                               │  │
│  │ for hyp in hypotheses:                            │  │
│  │   try:                                            │  │
│  │     path = pool.acquire(hyp.id)  ← Fast reuse    │  │
│  │   except RuntimeError:                            │  │
│  │     path = _create_direct(hyp.id) ← Fallback     │  │
│  └───────────────────────────────────────────────────┘  │
│          │                                               │
│          ↓                                               │
│  ┌───────────────────────────────────────────────────┐  │
│  │ __exit__()                                        │  │
│  │   ↓                                               │  │
│  │ for hyp_id in active_worktrees:                   │  │
│  │   pool.release(hyp_id)  ← Release to pool        │  │
│  │   ↓                                               │  │
│  │ pool.persist_state()    ← Save for next session  │  │
│  └───────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## Summary

The worktree pooling system provides:

1. **Layered Architecture**: Clean separation between high-level orchestration and low-level pooling
2. **Shared Infrastructure**: Reuses git utilities across modules
3. **State Persistence**: JSON-based state survives restarts
4. **Thread Safety**: Concurrent operations protected by locks
5. **Graceful Degradation**: Automatic fallback if pool exhausted
6. **Performance**: 3-32x speedup through worktree reuse
