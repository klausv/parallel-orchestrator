#!/usr/bin/env python3
"""
Falsification Debugger - Main Entry Point

Systematically debug bugs through parallel hypothesis testing with SuperClaude agent integration.
Based on Karl Popper's falsification principle.

Usage:
    python test_hypothesis.py "Bug description"
    python test_hypothesis.py --analyze-only "Bug description"
    python test_hypothesis.py --no-parallel "Bug description"
    python test_hypothesis.py --session-id SESSION_ID  # Resume session
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parallel_test import (
    FalsificationConfig,
    HypothesisManager,
    WorktreeOrchestrator,
    WorktreeConfig,
    TestExecutor,
    ResultsAnalyzer,
    utils
)

# Setup logging
utils.setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)


class FalsificationDebugger:
    """Main orchestrator for falsification-based debugging"""

    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize debugger

        Args:
            config_file: Path to falsification_config.yaml
        """
        if config_file:
            self.config = FalsificationConfig.from_yaml(config_file)
        else:
            # Try to load default config
            default_config = Path(__file__).parent.parent.parent / "config" / "falsification_config.yaml"
            if default_config.exists():
                self.config = FalsificationConfig.from_yaml(str(default_config))
            else:
                logger.info("Using default FalsificationConfig")
                self.config = FalsificationConfig()

        self.hypothesis_manager = HypothesisManager(self.config)
        self.results_analyzer = ResultsAnalyzer(self.config)

    def run_session(self, bug_description: str,
                   analyze_only: bool = False,
                   no_parallel: bool = False,
                   max_hypotheses: int = 5) -> None:
        """
        Run a complete falsification debugging session

        Args:
            bug_description: Description of the bug to debug
            analyze_only: Just analyze, don't execute tests
            no_parallel: Force sequential execution
            max_hypotheses: Maximum hypotheses to test
        """
        logger.info("=" * 70)
        logger.info("FALSIFICATION DEBUGGER - BUG DEBUGGING SESSION")
        logger.info("=" * 70)
        logger.info(f"Bug Description: {bug_description}")
        logger.info("")

        # Phase 1: Generate hypotheses (delegate to RCA)
        logger.info("[Phase 1] Generating hypotheses with /sc:root-cause...")
        hypotheses = self._generate_hypotheses_with_rca(bug_description)

        if not hypotheses:
            logger.error("No hypotheses generated. Cannot proceed.")
            return

        # Accept hypotheses into manager
        for hyp in hypotheses:
            self.hypothesis_manager.accept_hypothesis(hyp)

        logger.info(f"✓ Generated {len(hypotheses)} hypotheses")
        logger.info("")

        # Phase 2: Rank and filter
        logger.info("[Phase 2] Ranking hypotheses...")
        ranked = self.hypothesis_manager.rank_hypotheses()
        top_k = self.hypothesis_manager.limit_to_top_k(min(max_hypotheses, len(ranked)))

        logger.info(f"✓ Top {len(top_k)} hypotheses for testing:")
        for i, hyp in enumerate(top_k, 1):
            logger.info(f"  {i}. {hyp.description}")
            logger.info(f"     Probability: {hyp.probability:.1%}, Impact: {hyp.impact:.1%}")
        logger.info("")

        if analyze_only:
            logger.info("✓ Analysis complete. Use without --analyze-only to run tests.")
            return

        # Phase 3: Create worktrees (using context manager for guaranteed cleanup)
        logger.info("[Phase 3] Creating git worktrees...")
        worktree_config = WorktreeConfig(
            base_repo=Path.cwd(),
            worktree_dir=Path.cwd().parent / "worktrees"
        )

        with WorktreeOrchestrator(worktree_config, self.config) as orchestrator:
            worktrees = orchestrator.create_worktrees(top_k)
            logger.info(f"✓ Created {len(worktrees)} worktrees")

            # Setup test environments
            for hyp in top_k:
                orchestrator.setup_test_environment(worktrees[hyp.id], hyp)
            logger.info(f"✓ Test environments configured")
            logger.info("")

            # Phase 4: Execute tests
            logger.info("[Phase 4] Executing tests...")
            executor = TestExecutor(self.config)

            if no_parallel or not executor.should_parallelize(top_k):
                logger.info("Executing tests sequentially...")
                results = [executor.execute_single(hyp, worktrees[hyp.id]) for hyp in top_k]
            else:
                logger.info("Executing tests in parallel...")
                results = executor.execute_parallel(top_k, worktrees)

            logger.info(f"✓ Test execution complete")
            logger.info("")

            # Phase 5: Analyze results
            logger.info("[Phase 5] Analyzing results...")
            report = self.results_analyzer.generate_report(top_k, results)
            logger.info("")

            # Display report
            self._display_report(report)

            # Phase 6: Next actions
            logger.info("[Phase 6] Determining next actions...")
            if report.supported:
                logger.info("")
                logger.info("Supported Hypothesis(es):")
                for hyp in report.supported:
                    logger.info(f"  ✓ {hyp.description}")

                logger.info("")
                logger.info("Recommended Actions:")
                logger.info(f"  1. /sc:analyze   - Analyze root cause context")
                logger.info(f"  2. /sc:troubleshoot - Diagnose error patterns")
                logger.info(f"  3. /sc:design    - Design fix architecture")
                logger.info(f"  4. /sc:implement - Implement the solution")
            else:
                logger.info("")
                logger.info("No supported hypotheses. Recommended Actions:")
                logger.info(f"  1. Generate new hypotheses with /sc:root-cause")
                logger.info(f"  2. Adjust test strategy")
                logger.info(f"  3. Increase test timeout")

            logger.info("")
            logger.info(report.recommended_action)

        # Cleanup happens automatically via context manager
        logger.info("")
        logger.info("[Cleanup] Worktrees removed automatically")
        logger.info("✓ Cleanup complete")

    def _generate_hypotheses_with_rca(self, bug_description: str) -> List:
        """
        Delegate hypothesis generation to /sc:root-cause

        In a real implementation, this would invoke the SuperClaude /sc:root-cause agent.
        For now, returns example hypotheses.

        Args:
            bug_description: Bug description

        Returns:
            List of Hypothesis objects
        """
        from falsification import Hypothesis

        logger.info("(Would delegate to: /sc:root-cause)")
        logger.info("Using example hypotheses for demonstration...")

        # These are placeholder hypotheses
        # In real usage, /sc:root-cause would generate these
        example_hypotheses = [
            Hypothesis(
                id="hyp-1",
                description="Race condition in concurrent access",
                test_strategy="Run concurrent test suite",
                expected_behavior="All requests complete without errors",
                estimated_test_time=120,
                probability=0.85,
                impact=0.9,
                test_complexity=0.6
            ),
            Hypothesis(
                id="hyp-2",
                description="Cache invalidation issue",
                test_strategy="Test cache consistency under load",
                expected_behavior="Cache remains consistent across instances",
                estimated_test_time=60,
                probability=0.72,
                impact=0.7,
                test_complexity=0.4
            ),
            Hypothesis(
                id="hyp-3",
                description="Database transaction isolation problem",
                test_strategy="Run concurrent transaction test",
                expected_behavior="No dirty reads or conflicts",
                estimated_test_time=180,
                probability=0.68,
                impact=0.8,
                test_complexity=0.7
            )
        ]

        return example_hypotheses

    def _display_report(self, report) -> None:
        """Display formatted report"""
        logger.info("=" * 70)
        logger.info("FALSIFICATION REPORT")
        logger.info("=" * 70)
        logger.info(f"Session: {report.session_id}")
        logger.info(f"Bug: {report.bug_description}")
        logger.info("")
        logger.info("Results:")
        logger.info(f"  Falsified:     {len(report.falsified)} hypotheses")
        logger.info(f"  Supported:     {len(report.supported)} hypotheses")
        logger.info(f"  Inconclusive:  {len(report.inconclusive)} hypotheses")
        logger.info(f"  Confidence:    {report.confidence:.1%}")
        logger.info("")

        if report.falsified:
            logger.info("Falsified (Eliminated):")
            for hyp in report.falsified:
                logger.info(f"  ✗ {hyp.description}")

        if report.supported:
            logger.info("Supported (Likely Root Cause):")
            for hyp in report.supported:
                logger.info(f"  ✓ {hyp.description}")

        if report.inconclusive:
            logger.info("Inconclusive (Needs Investigation):")
            for hyp in report.inconclusive:
                logger.info(f"  ? {hyp.description}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Falsification Debugger - Systematic bug debugging with parallel hypothesis testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "API returns 500 errors under load"
  %(prog)s --analyze-only "Auth service randomly rejects sessions"
  %(prog)s --no-parallel "Database connection pool exhaustion"
  %(prog)s --max-hypotheses 3 "Bug description"
        """
    )

    parser.add_argument("bug_description", nargs="?", help="Description of the bug to debug")
    parser.add_argument("--session-id", help="Resume existing session")
    parser.add_argument("--config", help="Path to falsification_config.yaml")
    parser.add_argument("--analyze-only", action="store_true",
                       help="Analyze hypotheses without executing tests")
    parser.add_argument("--no-parallel", action="store_true",
                       help="Force sequential test execution")
    parser.add_argument("--max-hypotheses", type=int, default=5,
                       help="Maximum hypotheses to test (default: 5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    utils.setup_logging(level=log_level)

    # Validate input
    if args.session_id:
        logger.info(f"Resuming session: {args.session_id}")
        logger.warning("Session resumption not yet implemented")
        return

    if not args.bug_description:
        parser.print_help()
        sys.exit(1)

    # Run debugger
    try:
        debugger = FalsificationDebugger(args.config)
        debugger.run_session(
            bug_description=args.bug_description,
            analyze_only=args.analyze_only,
            no_parallel=args.no_parallel,
            max_hypotheses=args.max_hypotheses
        )
    except KeyboardInterrupt:
        logger.info("Session interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Session failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
