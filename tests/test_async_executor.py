#!/usr/bin/env python3
"""
Tests for AsyncTestExecutor

Verifies AsyncIO implementation maintains same behavior as ThreadPoolExecutor version.
"""

import asyncio
import pytest
import tempfile
import shutil
from pathlib import Path
from scripts.parallel_test.async_test_executor import AsyncTestExecutor
from scripts.parallel_test.config import Hypothesis, TestResult, FalsificationConfig


@pytest.fixture
def config():
    """Create test configuration"""
    return FalsificationConfig(
        test_timeout=10,
        max_concurrent_tests=3
    )


@pytest.fixture
def executor(config):
    """Create AsyncTestExecutor instance"""
    return AsyncTestExecutor(config)


@pytest.fixture
def temp_worktree():
    """Create temporary worktree with test script"""
    temp_dir = tempfile.mkdtemp()
    worktree = Path(temp_dir)

    # Create .falsification directory
    falsification_dir = worktree / ".falsification"
    falsification_dir.mkdir(parents=True)

    yield worktree

    # Cleanup
    shutil.rmtree(temp_dir)


def create_test_script(worktree: Path, hypothesis_id: str, exit_code: int = 0, sleep_time: float = 0):
    """Helper to create test script"""
    script_path = worktree / ".falsification" / f"test_{hypothesis_id}.sh"
    script_content = f"""#!/bin/bash
echo "Running test {hypothesis_id}"
sleep {sleep_time}
exit {exit_code}
"""
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    return script_path


class TestAsyncTestExecutor:
    """Test AsyncTestExecutor functionality"""

    def test_execute_single_pass(self, executor, temp_worktree):
        """Test single test execution that passes"""
        hyp = Hypothesis(
            id="test_001",
            description="Test hypothesis",
            estimated_test_time=1.0
        )

        create_test_script(temp_worktree, hyp.id, exit_code=0, sleep_time=0.1)

        result = executor.execute_single(hyp, temp_worktree)

        assert result.hypothesis_id == "test_001"
        assert result.result == TestResult.PASS
        assert result.exit_code == 0
        assert result.duration > 0

    def test_execute_single_fail(self, executor, temp_worktree):
        """Test single test execution that fails"""
        hyp = Hypothesis(
            id="test_002",
            description="Test hypothesis",
            estimated_test_time=1.0
        )

        create_test_script(temp_worktree, hyp.id, exit_code=1, sleep_time=0.1)

        result = executor.execute_single(hyp, temp_worktree)

        assert result.hypothesis_id == "test_002"
        assert result.result == TestResult.FAIL
        assert result.exit_code == 1

    def test_execute_single_timeout(self, temp_worktree):
        """Test single test execution with timeout"""
        config = FalsificationConfig(test_timeout=1)
        executor = AsyncTestExecutor(config)

        hyp = Hypothesis(
            id="test_003",
            description="Test hypothesis",
            estimated_test_time=1.0
        )

        create_test_script(temp_worktree, hyp.id, exit_code=0, sleep_time=5)

        result = executor.execute_single(hyp, temp_worktree)

        assert result.hypothesis_id == "test_003"
        assert result.result == TestResult.TIMEOUT
        assert result.exit_code == 124

    def test_execute_single_missing_script(self, executor, temp_worktree):
        """Test single test execution with missing script"""
        hyp = Hypothesis(
            id="test_004",
            description="Test hypothesis",
            estimated_test_time=1.0
        )

        # Don't create script

        result = executor.execute_single(hyp, temp_worktree)

        assert result.hypothesis_id == "test_004"
        assert result.result == TestResult.ERROR
        assert "not found" in result.error_message.lower()

    def test_execute_parallel(self, executor):
        """Test parallel execution of multiple hypotheses"""
        # Create temporary worktrees
        temp_dirs = []
        worktrees = {}
        hypotheses = []

        try:
            for i in range(3):
                temp_dir = tempfile.mkdtemp()
                temp_dirs.append(temp_dir)
                worktree = Path(temp_dir)

                # Create .falsification directory
                falsification_dir = worktree / ".falsification"
                falsification_dir.mkdir(parents=True)

                hyp_id = f"test_{i:03d}"
                hyp = Hypothesis(
                    id=hyp_id,
                    description=f"Test hypothesis {i}",
                    estimated_test_time=1.0
                )
                hypotheses.append(hyp)
                worktrees[hyp_id] = worktree

                # Create test script (alternating pass/fail)
                create_test_script(worktree, hyp_id, exit_code=i % 2, sleep_time=0.1)

            results = executor.execute_parallel(hypotheses, worktrees)

            assert len(results) == 3
            # Results may be returned in any order due to asyncio.as_completed
            # So we check by hypothesis_id rather than index
            results_by_id = {r.hypothesis_id: r for r in results}
            assert results_by_id["test_000"].result == TestResult.PASS  # i=0, exit_code=0
            assert results_by_id["test_001"].result == TestResult.FAIL  # i=1, exit_code=1
            assert results_by_id["test_002"].result == TestResult.PASS  # i=2, exit_code=0

        finally:
            # Cleanup
            for temp_dir in temp_dirs:
                shutil.rmtree(temp_dir)

    def test_should_parallelize_single_hypothesis(self, executor):
        """Test should_parallelize with single hypothesis"""
        hypotheses = [
            Hypothesis(id="test_001", description="Test", estimated_test_time=30.0)
        ]

        assert executor.should_parallelize(hypotheses) is False

    def test_should_parallelize_worthwhile(self, executor):
        """Test should_parallelize when parallel is worthwhile"""
        hypotheses = [
            Hypothesis(id=f"test_{i:03d}", description="Test", estimated_test_time=60.0)
            for i in range(5)
        ]

        # Sequential: 5 * 60 = 300s
        # Parallel: 60 + 7 + (16*5) = 147s
        # Savings: 153s
        assert executor.should_parallelize(hypotheses) is True

    def test_should_parallelize_not_worthwhile(self, executor):
        """Test should_parallelize when parallel is not worthwhile"""
        hypotheses = [
            Hypothesis(id=f"test_{i:03d}", description="Test", estimated_test_time=10.0)
            for i in range(2)
        ]

        # Sequential: 2 * 10 = 20s
        # Parallel: 10 + 7 + (16*2) = 49s
        # Savings: -29s (worse!)
        assert executor.should_parallelize(hypotheses) is False

    def test_confidence_calculation(self, executor):
        """Test confidence score calculation"""
        # Timeout
        assert executor._calculate_confidence(TestResult.TIMEOUT, 10.0) == 0.3

        # Error
        assert executor._calculate_confidence(TestResult.ERROR, 10.0) == 0.2

        # Fast test
        assert executor._calculate_confidence(TestResult.PASS, 2.0) == 0.6

        # Normal test
        assert executor._calculate_confidence(TestResult.PASS, 10.0) == 0.85

    @pytest.mark.asyncio
    async def test_async_api_directly(self, executor, temp_worktree):
        """Test async API can be called directly"""
        hyp = Hypothesis(
            id="test_async",
            description="Test async API",
            estimated_test_time=1.0
        )

        create_test_script(temp_worktree, hyp.id, exit_code=0, sleep_time=0.1)

        result = await executor.execute_single_async(hyp, temp_worktree)

        assert result.hypothesis_id == "test_async"
        assert result.result == TestResult.PASS
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
