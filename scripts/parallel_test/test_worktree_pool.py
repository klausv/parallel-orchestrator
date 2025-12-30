#!/usr/bin/env python3
"""
Test script for WorktreePool functionality

Demonstrates:
    - Pool initialization and state persistence
    - Worktree acquire/release operations
    - Context manager usage
    - Pool statistics and monitoring
    - Performance comparison: pooled vs direct mode
"""

import sys
import time
import logging
from pathlib import Path

# Setup path to import modules
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent.parent))

from scripts.parallel_test.worktree_pool import WorktreePool
from scripts.parallel_test.worktree_orchestrator import WorktreeOrchestrator, WorktreeConfig
from scripts.parallel_test.config import Hypothesis

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_basic_pool_operations():
    """Test basic pool acquire/release operations"""
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Basic Pool Operations")
    logger.info("="*60)

    # Setup paths
    base_repo = Path.cwd()
    pool_dir = Path.cwd() / "test_pool"

    # Create pool
    pool = WorktreePool(base_repo, pool_dir, max_size=3, auto_load=False)

    try:
        # Acquire worktrees
        logger.info("\nAcquiring 3 worktrees...")
        wt1 = pool.acquire("hyp_1")
        wt2 = pool.acquire("hyp_2")
        wt3 = pool.acquire("hyp_3")

        logger.info(f"Acquired: {wt1}, {wt2}, {wt3}")
        logger.info(f"Pool stats: {pool.get_stats()}")

        # Try to acquire beyond capacity
        logger.info("\nTrying to acquire beyond capacity...")
        try:
            pool.acquire("hyp_4")
            logger.error("Should have raised RuntimeError!")
        except RuntimeError as e:
            logger.info(f"Expected error: {e}")

        # Release and re-acquire
        logger.info("\nReleasing hyp_1 and acquiring hyp_4...")
        pool.release("hyp_1")
        wt4 = pool.acquire("hyp_4")
        logger.info(f"Acquired: {wt4}")
        logger.info(f"Pool stats: {pool.get_stats()}")

        # Persist state
        logger.info("\nPersisting pool state...")
        pool.persist_state()
        logger.info(f"State saved to: {pool.state_file}")

    finally:
        # Cleanup
        pool.cleanup_all()
        logger.info("\nCleaned up test pool")


def test_context_manager():
    """Test context manager for automatic release"""
    logger.info("\n" + "="*60)
    logger.info("TEST 2: Context Manager Usage")
    logger.info("="*60)

    base_repo = Path.cwd()
    pool_dir = Path.cwd() / "test_pool"

    pool = WorktreePool(base_repo, pool_dir, max_size=3, auto_load=False)

    try:
        # Use context manager
        logger.info("\nUsing context manager for automatic release...")
        with pool.worktree("hyp_1") as wt_path:
            logger.info(f"Acquired worktree: {wt_path}")
            logger.info(f"Pool stats inside context: {pool.get_stats()}")

        # Worktree should be released automatically
        logger.info(f"Pool stats after context: {pool.get_stats()}")

    finally:
        pool.cleanup_all()


def test_state_persistence():
    """Test pool state persistence across sessions"""
    logger.info("\n" + "="*60)
    logger.info("TEST 3: State Persistence")
    logger.info("="*60)

    base_repo = Path.cwd()
    pool_dir = Path.cwd() / "test_pool"

    # Session 1: Create pool and acquire worktrees
    logger.info("\nSession 1: Creating pool and acquiring worktrees...")
    pool1 = WorktreePool(base_repo, pool_dir, max_size=5, auto_load=False)
    pool1.acquire("hyp_1")
    pool1.acquire("hyp_2")
    pool1.release("hyp_1")  # hyp_1 available, hyp_2 allocated
    pool1.persist_state()

    stats1 = pool1.get_stats()
    logger.info(f"Session 1 stats: {stats1}")

    # Session 2: Load previous state
    logger.info("\nSession 2: Loading previous state...")
    pool2 = WorktreePool(base_repo, pool_dir, max_size=5, auto_load=True)

    stats2 = pool2.get_stats()
    logger.info(f"Session 2 stats: {stats2}")

    # Verify state was restored
    assert stats2['allocated'] == stats1['allocated'], "Allocated count mismatch"
    assert stats2['available'] == stats1['available'], "Available count mismatch"

    logger.info("\nState successfully restored!")

    # Cleanup
    pool2.cleanup_all()


def test_performance_comparison():
    """Compare performance: pooled vs direct mode"""
    logger.info("\n" + "="*60)
    logger.info("TEST 4: Performance Comparison")
    logger.info("="*60)

    base_repo = Path.cwd()
    worktree_dir = Path.cwd() / "test_worktrees"

    # Create test hypotheses
    hypotheses = [
        Hypothesis(id=f"perf_test_{i}", description=f"Test hypothesis {i}")
        for i in range(3)
    ]

    # Test 1: Direct mode (no pooling)
    logger.info("\nTest 1: Direct mode (no pooling)")
    config_direct = WorktreeConfig(
        base_repo=base_repo,
        worktree_dir=worktree_dir,
        use_pool=False
    )

    start = time.time()
    with WorktreeOrchestrator(config_direct) as orch:
        worktrees = orch.create_worktrees(hypotheses)
    direct_time = time.time() - start

    logger.info(f"Direct mode time: {direct_time:.2f}s")

    # Test 2: Pooled mode (first session - creates worktrees)
    logger.info("\nTest 2: Pooled mode (first session)")
    config_pooled = WorktreeConfig(
        base_repo=base_repo,
        worktree_dir=worktree_dir,
        use_pool=True,
        pool_size=5
    )

    start = time.time()
    with WorktreeOrchestrator(config_pooled) as orch:
        worktrees = orch.create_worktrees(hypotheses)
        stats = orch.get_pool_stats()
        logger.info(f"Pool stats: {stats}")
    pooled_first_time = time.time() - start

    logger.info(f"Pooled mode (first session) time: {pooled_first_time:.2f}s")

    # Test 3: Pooled mode (second session - reuses worktrees)
    logger.info("\nTest 3: Pooled mode (second session - reuse)")

    start = time.time()
    with WorktreeOrchestrator(config_pooled) as orch:
        worktrees = orch.create_worktrees(hypotheses)
        stats = orch.get_pool_stats()
        logger.info(f"Pool stats: {stats}")
    pooled_reuse_time = time.time() - start

    logger.info(f"Pooled mode (reuse) time: {pooled_reuse_time:.2f}s")

    # Calculate speedup
    if pooled_reuse_time > 0:
        speedup = pooled_first_time / pooled_reuse_time
        logger.info(f"\nSpeedup from pooling (reuse): {speedup:.1f}x")

    # Cleanup
    with WorktreeOrchestrator(config_pooled) as orch:
        orch.cleanup_pool()


def test_pool_expansion():
    """Test pool expansion and shrinking"""
    logger.info("\n" + "="*60)
    logger.info("TEST 5: Pool Expansion and Shrinking")
    logger.info("="*60)

    base_repo = Path.cwd()
    pool_dir = Path.cwd() / "test_pool"

    pool = WorktreePool(base_repo, pool_dir, max_size=10, auto_load=False)

    try:
        # Start with empty pool
        logger.info(f"\nInitial pool: {pool.get_stats()}")

        # Expand pool
        logger.info("\nExpanding pool by 3 worktrees...")
        added = pool.expand_pool(3)
        logger.info(f"Added {added} worktrees")
        logger.info(f"Pool stats: {pool.get_stats()}")

        # Shrink pool
        logger.info("\nShrinking pool by 2 worktrees...")
        removed = pool.shrink_pool(2)
        logger.info(f"Removed {removed} worktrees")
        logger.info(f"Pool stats: {pool.get_stats()}")

    finally:
        pool.cleanup_all()


def main():
    """Run all tests"""
    logger.info("Starting WorktreePool tests...")

    try:
        test_basic_pool_operations()
        test_context_manager()
        test_state_persistence()
        test_pool_expansion()
        test_performance_comparison()

        logger.info("\n" + "="*60)
        logger.info("ALL TESTS PASSED!")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"\nTEST FAILED: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
