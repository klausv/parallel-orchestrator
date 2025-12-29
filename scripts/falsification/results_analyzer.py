#!/usr/bin/env python3
"""
Results Analysis Module

Analyzes test results and generates reports
"""

import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
from .config import (
    Hypothesis, TestExecutionResult, FalsificationReport,
    HypothesisStatus, TestResult, FalsificationConfig
)

logger = logging.getLogger(__name__)


class ResultsAnalyzer:
    """Analyzes test results and generates reports"""

    def __init__(self, config: Optional[FalsificationConfig] = None):
        """
        Initialize results analyzer

        Args:
            config: Optional FalsificationConfig instance
        """
        self.config = config or FalsificationConfig()
        self.results: List[TestExecutionResult] = []

    def generate_report(self, hypotheses: List[Hypothesis],
                       results: List[TestExecutionResult]) -> FalsificationReport:
        """
        Generate falsification report (FR4.1)

        Report includes:
            - Summary of falsified/supported/inconclusive
            - Confidence scores
            - Recommended next action
            - Test artifacts and logs

        Args:
            hypotheses: List of tested hypotheses
            results: List of test execution results

        Returns:
            FalsificationReport with complete analysis
        """
        session_id = f"falsification_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Generating report for session: {session_id}")

        falsified = []
        supported = []
        inconclusive = []

        # Classify results
        for result in results:
            hyp = next((h for h in hypotheses if h.id == result.hypothesis_id), None)
            if not hyp:
                logger.warning(f"Hypothesis not found for result: {result.hypothesis_id}")
                continue

            status = self._classify_result(result)
            hyp.status = status

            if status == HypothesisStatus.FALSIFIED:
                falsified.append(hyp)
            elif status == HypothesisStatus.SUPPORTED:
                supported.append(hyp)
            else:
                inconclusive.append(hyp)

        # Calculate overall confidence
        if supported:
            total_confidence = sum(h.confidence_score or 0.0 for h in supported) / len(supported)
        else:
            total_confidence = 0.0

        # Determine next action
        next_action = self._determine_next_action(falsified, supported, inconclusive)
        next_steps = self._generate_next_steps(falsified, supported, inconclusive)

        # Get bug description from first hypothesis if available
        bug_description = hypotheses[0].description if hypotheses else "Unknown bug"

        # Create report
        report = FalsificationReport(
            session_id=session_id,
            bug_description=bug_description,
            total_hypotheses=len(hypotheses),
            falsified=falsified,
            supported=supported,
            inconclusive=inconclusive,
            recommended_action=next_action,
            next_steps=next_steps,
            confidence=total_confidence,
            test_results=results
        )

        logger.info(f"Report generated: {len(falsified)} falsified, {len(supported)} supported, {len(inconclusive)} inconclusive")
        return report

    def _classify_result(self, result: TestExecutionResult) -> HypothesisStatus:
        """
        Classify test result into hypothesis status (FR3.4)

        Logic:
            - PASS + exit_code=0 → FALSIFIED (hypothesis eliminated)
            - FAIL + exit_code!=0 → SUPPORTED (hypothesis likely)
            - TIMEOUT → INCONCLUSIVE
            - ERROR → INCONCLUSIVE

        Args:
            result: TestExecutionResult to classify

        Returns:
            HypothesisStatus classification
        """
        if result.result == TestResult.PASS or result.exit_code == 0:
            return HypothesisStatus.FALSIFIED
        elif result.result == TestResult.FAIL or result.exit_code != 0:
            return HypothesisStatus.SUPPORTED
        elif result.result == TestResult.TIMEOUT:
            return HypothesisStatus.INCONCLUSIVE
        else:
            return HypothesisStatus.INCONCLUSIVE

    def _determine_next_action(self, falsified: List[Hypothesis],
                               supported: List[Hypothesis],
                               inconclusive: List[Hypothesis]) -> str:
        """
        Determine recommended next action (FR4.2)

        Decision tree:
            - 1 supported, rest falsified → "Focus on implementing fix"
            - >1 supported → "Refine hypotheses to isolate root cause"
            - All falsified → "Generate new hypotheses (RCA)"
            - Mix with inconclusive → "Investigate inconclusive cases"

        Args:
            falsified: List of falsified hypotheses
            supported: List of supported hypotheses
            inconclusive: List of inconclusive hypotheses

        Returns:
            Recommended action string
        """
        if len(supported) == 0:
            return "Generate new hypotheses - all current hypotheses falsified"
        elif len(supported) == 1:
            return f"Focus on implementing fix for: {supported[0].description}"
        elif len(supported) > 1:
            return "Refine hypotheses to isolate single root cause"
        else:
            return "Review inconclusive test results"

    def _generate_next_steps(self, falsified: List[Hypothesis],
                            supported: List[Hypothesis],
                            inconclusive: List[Hypothesis]) -> List[str]:
        """
        Generate list of next steps

        Args:
            falsified: List of falsified hypotheses
            supported: List of supported hypotheses
            inconclusive: List of inconclusive hypotheses

        Returns:
            List of recommended next steps
        """
        steps = []

        if supported:
            steps.append(f"Review supported hypothesis: {supported[0].description}")
            steps.append("Design fix for the root cause")
            steps.append("Implement and test the fix")

        if inconclusive:
            steps.append(f"Investigate {len(inconclusive)} inconclusive result(s)")
            steps.append("Improve test strategy or environment")

        if not supported and not inconclusive:
            steps.append("Request additional information about the bug")
            steps.append("Generate new hypotheses with /sc:root-cause")
            steps.append("Adjust test timeouts or strategy")

        if len(supported) > 1:
            steps.append(f"Create refined hypotheses to distinguish between {len(supported)} supported options")

        return steps

    def persist_session(self, report: FalsificationReport,
                       memory_mcp=None) -> None:
        """
        Save session state to memory MCP (FR4.3)

        Stores:
            - Session ID and metadata
            - Hypothesis results
            - Report summary
            - Next action

        Args:
            report: FalsificationReport to persist
            memory_mcp: Optional memory MCP instance
        """
        if not memory_mcp:
            logger.warning("Memory MCP not available, skipping persistence")
            return

        try:
            # Create session data
            session_data = {
                "session_id": report.session_id,
                "bug_description": report.bug_description,
                "timestamp": datetime.now().isoformat(),
                "results": {
                    "falsified": len(report.falsified),
                    "supported": len(report.supported),
                    "inconclusive": len(report.inconclusive)
                },
                "recommended_action": report.recommended_action,
                "next_steps": report.next_steps,
                "confidence": report.confidence
            }

            # Save to memory
            memory_key = f"{self.config.session_prefix}_session_{report.session_id}"
            memory_mcp.create_entities([{
                "name": memory_key,
                "entityType": "falsification_session",
                "observations": [json.dumps(session_data)]
            }])

            logger.info(f"Session persisted: {memory_key}")

        except Exception as e:
            logger.error(f"Failed to persist session: {e}")

    def resume_session(self, session_id: str,
                      memory_mcp=None) -> Optional[FalsificationReport]:
        """
        Resume previous session from memory (FR4.3)

        Args:
            session_id: ID of session to resume
            memory_mcp: Optional memory MCP instance

        Returns:
            FalsificationReport or None if not found
        """
        if not memory_mcp:
            logger.warning("Memory MCP not available, cannot resume session")
            return None

        try:
            memory_key = f"{self.config.session_prefix}_session_{session_id}"
            # Note: actual implementation would use memory_mcp.read_memory()
            logger.info(f"Would resume session: {memory_key}")
            return None

        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            return None

    def export_report(self, report: FalsificationReport, format: str = "json") -> str:
        """
        Export report in specified format

        Args:
            report: FalsificationReport to export
            format: Export format (json, markdown, text)

        Returns:
            Formatted report string
        """
        if format == "json":
            return self._export_json(report)
        elif format == "markdown":
            return self._export_markdown(report)
        else:
            return self._export_text(report)

    def _export_json(self, report: FalsificationReport) -> str:
        """Export as JSON"""
        data = {
            "session_id": report.session_id,
            "bug_description": report.bug_description,
            "total_hypotheses": report.total_hypotheses,
            "results": {
                "falsified": len(report.falsified),
                "supported": len(report.supported),
                "inconclusive": len(report.inconclusive)
            },
            "recommended_action": report.recommended_action,
            "next_steps": report.next_steps,
            "confidence": report.confidence
        }
        return json.dumps(data, indent=2)

    def _export_markdown(self, report: FalsificationReport) -> str:
        """Export as Markdown"""
        lines = [
            "# Falsification Report",
            f"\n## Session: {report.session_id}",
            f"\n## Bug Description\n{report.bug_description}",
            f"\n## Results\n- **Falsified**: {len(report.falsified)}",
            f"- **Supported**: {len(report.supported)}",
            f"- **Inconclusive**: {len(report.inconclusive)}",
            f"\n## Recommended Action\n{report.recommended_action}",
            "\n## Next Steps"
        ]

        for i, step in enumerate(report.next_steps, 1):
            lines.append(f"{i}. {step}")

        lines.append(f"\n## Confidence Score\n{report.confidence:.2%}")

        return "\n".join(lines)

    def _export_text(self, report: FalsificationReport) -> str:
        """Export as plain text"""
        lines = [
            "=" * 60,
            "FALSIFICATION REPORT",
            "=" * 60,
            f"\nSession: {report.session_id}",
            f"Bug: {report.bug_description}",
            f"\nResults:",
            f"  Falsified:     {len(report.falsified)}",
            f"  Supported:     {len(report.supported)}",
            f"  Inconclusive:  {len(report.inconclusive)}",
            f"\nRecommended Action:",
            f"  {report.recommended_action}",
            f"\nNext Steps:"
        ]

        for i, step in enumerate(report.next_steps, 1):
            lines.append(f"  {i}. {step}")

        lines.append(f"\nConfidence: {report.confidence:.2%}")
        lines.append("\n" + "=" * 60)

        return "\n".join(lines)
