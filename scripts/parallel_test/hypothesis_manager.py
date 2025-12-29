#!/usr/bin/env python3
"""
Hypothesis Management Module

Manages hypothesis lifecycle: validation, ranking, prioritization
"""

from typing import List, Dict, Optional
import logging
from .config import Hypothesis, HypothesisStatus, FalsificationConfig

logger = logging.getLogger(__name__)


class HypothesisManager:
    """Manages hypothesis lifecycle and ranking"""

    def __init__(self, config: Optional[FalsificationConfig] = None):
        """
        Initialize hypothesis manager

        Args:
            config: FalsificationConfig instance (optional)
        """
        self.config = config or FalsificationConfig()
        self.pool: List[Hypothesis] = []
        self.max_hypotheses = self.config.max_hypotheses

    def accept_hypothesis(self, hypothesis: Hypothesis) -> bool:
        """
        Accept a new hypothesis into the pool (FR1.1)

        Args:
            hypothesis: Hypothesis object to accept

        Returns:
            True if accepted, False if validation fails
        """
        if not self.validate_hypothesis(hypothesis):
            logger.warning(f"Hypothesis validation failed: {hypothesis.description}")
            return False

        if len(self.pool) >= self.config.max_hypotheses * 2:
            logger.info("Hypothesis pool at capacity, ranking before accepting new")
            self.limit_to_top_k(self.config.max_hypotheses)

        self.pool.append(hypothesis)
        logger.info(f"Accepted hypothesis: {hypothesis.id} - {hypothesis.description}")
        return True

    def validate_hypothesis(self, hypothesis: Hypothesis) -> bool:
        """
        Validate hypothesis structure and testability (FR1.2)

        Checks:
            - Required fields present
            - Test strategy is concrete
            - Expected behavior is measurable
            - Estimated test time > 0

        Args:
            hypothesis: Hypothesis to validate

        Returns:
            True if valid, False otherwise
        """
        if not hypothesis.id:
            logger.warning("Hypothesis missing ID")
            return False

        if not hypothesis.description:
            logger.warning("Hypothesis missing description")
            return False

        if not hypothesis.is_falsifiable():
            if self.config.require_falsifiability:
                logger.warning(f"Hypothesis {hypothesis.id} is not falsifiable")
                return False

        if hypothesis.estimated_test_time <= 0:
            logger.warning(f"Hypothesis {hypothesis.id} has invalid test time: {hypothesis.estimated_test_time}")
            return False

        if not (0.0 <= hypothesis.probability <= 1.0):
            logger.warning(f"Hypothesis {hypothesis.id} has invalid probability: {hypothesis.probability}")
            return False

        if not (0.0 <= hypothesis.impact <= 1.0):
            logger.warning(f"Hypothesis {hypothesis.id} has invalid impact: {hypothesis.impact}")
            return False

        if not (0.0 <= hypothesis.test_complexity <= 1.0):
            logger.warning(f"Hypothesis {hypothesis.id} has invalid complexity: {hypothesis.test_complexity}")
            return False

        return True

    def rank_hypotheses(self, sequential_thinking_mcp=None) -> List[Hypothesis]:
        """
        Rank hypotheses by priority (FR1.3)

        Ranking criteria:
            - Probability of being root cause
            - Impact if true (severity)
            - Test complexity (prefer simpler tests)

        Formula: score = (probability * 0.5) + (impact * 0.3) - (complexity * 0.2)

        Args:
            sequential_thinking_mcp: Optional MCP for advanced ranking logic

        Returns:
            Sorted list (highest score first)
        """
        if not self.pool:
            logger.warning("No hypotheses to rank")
            return []

        # Calculate scores
        weights = {
            "probability": self.config.probability_weight,
            "impact": self.config.impact_weight,
            "complexity": self.config.complexity_weight
        }

        for hyp in self.pool:
            hyp.confidence_score = hyp.ranking_score(weights)

        # Sort by score descending
        ranked = sorted(self.pool, key=lambda h: h.confidence_score or 0.0, reverse=True)

        logger.info(f"Ranked {len(ranked)} hypotheses")
        for i, hyp in enumerate(ranked, 1):
            logger.info(f"  {i}. {hyp.id}: {hyp.description} (score: {hyp.confidence_score:.3f})")

        return ranked

    def limit_to_top_k(self, k: int = 5) -> List[Hypothesis]:
        """
        Limit pool to top K hypotheses (FR1.4)

        Args:
            k: Number of top hypotheses to keep (default: 5)

        Returns:
            Limited list of top hypotheses
        """
        ranked = self.rank_hypotheses()
        self.pool = ranked[:k]
        logger.info(f"Limited to top {k} hypotheses")
        return self.pool

    def update_status(self, hypothesis_id: str, status: HypothesisStatus,
                     results: Optional[Dict] = None) -> bool:
        """
        Update hypothesis status after test execution

        Args:
            hypothesis_id: ID of hypothesis to update
            status: New HypothesisStatus
            results: Optional test results dictionary

        Returns:
            True if updated, False if not found
        """
        hyp = next((h for h in self.pool if h.id == hypothesis_id), None)
        if not hyp:
            logger.warning(f"Hypothesis {hypothesis_id} not found")
            return False

        hyp.status = status
        if results:
            hyp.test_results = results

        logger.info(f"Updated {hypothesis_id} status to {status.value}")
        return True

    def get_next_for_testing(self) -> Optional[Hypothesis]:
        """
        Get next untested hypothesis in priority order

        Returns:
            Next Hypothesis to test, or None if all tested
        """
        for hyp in self.pool:
            if hyp.status == HypothesisStatus.PENDING:
                return hyp
        return None

    def get_by_id(self, hypothesis_id: str) -> Optional[Hypothesis]:
        """
        Get hypothesis by ID

        Args:
            hypothesis_id: ID to search for

        Returns:
            Hypothesis or None if not found
        """
        return next((h for h in self.pool if h.id == hypothesis_id), None)

    def get_all(self) -> List[Hypothesis]:
        """
        Get all hypotheses in pool

        Returns:
            List of all Hypothesis objects
        """
        return self.pool.copy()

    def get_by_status(self, status: HypothesisStatus) -> List[Hypothesis]:
        """
        Get all hypotheses with specific status

        Args:
            status: HypothesisStatus to filter by

        Returns:
            List of matching Hypothesis objects
        """
        return [h for h in self.pool if h.status == status]

    def clear_pool(self) -> None:
        """Clear all hypotheses from pool"""
        self.pool.clear()
        logger.info("Cleared hypothesis pool")

    def __len__(self) -> int:
        """Return number of hypotheses in pool"""
        return len(self.pool)

    def __repr__(self) -> str:
        """String representation"""
        return f"HypothesisManager(pool_size={len(self.pool)}, max={self.max_hypotheses})"
