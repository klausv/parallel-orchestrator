#!/usr/bin/env python3
"""
Quick test to verify shared infrastructure works correctly

Run with: python3 scripts/test_shared_infrastructure.py
"""

import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all shared modules can be imported"""
    print("Testing imports...")

    try:
        from shared import (
            # Git
            get_current_branch,
            create_worktree,
            remove_worktree,
            reset_worktree,
            list_worktrees,
            count_worktrees,
            WorktreeContext,
            GitOperationError,
            # Subprocess
            run_command,
            run_command_async,
            run_script,
            run_shell_script,
            CommandResult,
            CommandRunner,
            # Logging
            setup_logging,
            get_logger,
            ProgressLogger,
            LogSection,
            log_exception,
            configure_third_party_loggers,
            Colors,
            ColoredFormatter,
        )
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False


def test_git_utils():
    """Test git utilities with current repo"""
    print("\nTesting git utilities...")

    try:
        from shared.git_utils import get_current_branch, count_worktrees

        # Test get_current_branch
        branch = get_current_branch(Path.cwd())
        print(f"  Current branch: {branch}")

        # Test count_worktrees
        count = count_worktrees(Path.cwd())
        print(f"  Worktree count: {count}")

        print("✅ Git utilities working")
        return True
    except Exception as e:
        print(f"❌ Git utilities failed: {e}")
        return False


def test_subprocess_utils():
    """Test subprocess utilities"""
    print("\nTesting subprocess utilities...")

    try:
        from shared.subprocess_utils import run_command, CommandResult

        # Test simple command
        result = run_command("echo 'Hello from shared infrastructure'")

        assert isinstance(result, CommandResult)
        assert result.success
        assert "Hello" in result.stdout
        print(f"  Command result: {result}")
        print(f"  Output: {result.stdout.strip()}")

        # Test timeout
        result = run_command("sleep 2", timeout=1)
        assert result.timed_out
        assert result.exit_code == 124
        print(f"  Timeout handled correctly: {result.timed_out}")

        print("✅ Subprocess utilities working")
        return True
    except Exception as e:
        print(f"❌ Subprocess utilities failed: {e}")
        return False


def test_logging_utils():
    """Test logging utilities"""
    print("\nTesting logging utilities...")

    try:
        from shared.logging_utils import (
            setup_logging,
            get_logger,
            ProgressLogger,
            LogSection,
            Colors
        )
        import logging

        # Test setup_logging
        setup_logging(level=logging.INFO, use_colors=True)

        # Test get_logger
        logger = get_logger(__name__)
        logger.info("Test log message")

        # Test ProgressLogger
        progress = ProgressLogger("Test task", total=5)
        for i in range(5):
            progress.update(i + 1, f"Step {i+1}")
        progress.complete()

        # Test LogSection
        with LogSection("Test section"):
            logger.info("Inside section")

        # Test Colors
        print(f"  {Colors.GREEN}Green text{Colors.RESET}")
        print(f"  {Colors.YELLOW}Yellow text{Colors.RESET}")

        print("✅ Logging utilities working")
        return True
    except Exception as e:
        print(f"❌ Logging utilities failed: {e}")
        return False


def test_command_runner():
    """Test CommandRunner class"""
    print("\nTesting CommandRunner...")

    try:
        from shared.subprocess_utils import CommandRunner

        runner = CommandRunner(default_cwd=Path.cwd(), default_timeout=5)

        # Run multiple commands
        result1 = runner.run("echo 'Command 1'")
        result2 = runner.run("echo 'Command 2'")
        result3 = runner.run("false")  # This will fail

        assert len(runner.command_history) == 3
        assert result1.success
        assert result2.success
        assert result3.failed

        failed = runner.get_failed_commands()
        assert len(failed) == 1

        print(f"  Commands run: {len(runner.command_history)}")
        print(f"  Failed commands: {len(failed)}")

        print("✅ CommandRunner working")
        return True
    except Exception as e:
        print(f"❌ CommandRunner failed: {e}")
        return False


def test_worktree_context():
    """Test WorktreeContext manager (dry run - doesn't create actual worktree)"""
    print("\nTesting WorktreeContext...")

    try:
        from shared.git_utils import WorktreeContext
        from pathlib import Path

        # We can import and instantiate the context manager
        # but we won't actually use it to avoid creating test worktrees
        print("  WorktreeContext class available and importable")
        print("  (Skipping actual worktree creation in test)")

        print("✅ WorktreeContext available")
        return True
    except Exception as e:
        print(f"❌ WorktreeContext failed: {e}")
        return False


def main():
    """Run all tests"""
    print("="*60)
    print("SHARED INFRASTRUCTURE TEST SUITE")
    print("="*60)

    tests = [
        test_imports,
        test_git_utils,
        test_subprocess_utils,
        test_logging_utils,
        test_command_runner,
        test_worktree_context,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append(False)

    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
