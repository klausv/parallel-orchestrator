#!/usr/bin/env python3
"""
task-splitter.py - AI-powered task decomposition with overhead optimization

Uses Claude API to analyze a task and split it into optimal number of
non-conflicting subtasks, considering overhead costs and break-even points.

Usage:
    python3 task-splitter.py "Implement user authentication with tests"
    python3 task-splitter.py --check-conflicts feature-a feature-b
    python3 task-splitter.py --analyze-repo
    python3 task-splitter.py --max-splits 5 "Large refactoring task"
"""

import os
import sys
import json
import argparse
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


# ============================================================================
# CONFIGURATION - Overhead and Resource Constraints
# ============================================================================

@dataclass
class ParallelConfig:
    """Configuration for parallelization decisions."""
    # Overhead times (in seconds)
    worktree_creation_time: float = 8.0      # Time to create a git worktree
    session_startup_time: float = 5.0         # Time to start Claude session
    context_building_time: float = 20.0       # Time for Claude to understand context
    merge_time_per_branch: float = 10.0       # Time to merge each branch
    conflict_resolution_base: float = 60.0    # Base time if conflicts occur

    # Resource limits
    max_concurrent_sessions: int = 8          # Maximum parallel Claude sessions
    max_worktrees: int = 15                   # Maximum git worktrees per repo
    min_files_per_subtask: int = 2            # Minimum files to justify a subtask
    min_task_complexity: float = 0.2          # Minimum complexity to consider splitting

    # Break-even thresholds (in minutes)
    min_task_time_for_2_splits: float = 5.0   # Task must take >5 min for 2 parallel
    min_task_time_for_3_splits: float = 12.0  # Task must take >12 min for 3 parallel
    min_task_time_for_4_splits: float = 20.0  # etc.
    min_task_time_for_5_plus: float = 30.0

    # Complexity weights
    complexity_per_file_modify: float = 0.15  # Modifying existing file
    complexity_per_file_create: float = 0.10  # Creating new file
    complexity_per_loc_estimate: float = 0.001  # Per line of code
    complexity_per_dependency: float = 0.05   # Per cross-file dependency


DEFAULT_CONFIG = ParallelConfig()


# ============================================================================
# AGENT AND SKILL MATCHING
# ============================================================================

@dataclass
class AgentRecommendation:
    """Recommended agent and skill for a subtask."""
    agent: str
    skill: str
    confidence: float  # 0.0 - 1.0
    rationale: str


# Agent matching configuration - patterns to agent/skill mappings
AGENT_MATCHING = {
    # Task description patterns → agent
    "task_patterns": {
        # Security & Auth
        r"auth|login|session|jwt|oauth|permission|rbac|acl": {
            "agent": "security-engineer",
            "skill": "/sc:implement --focus security",
            "rationale": "Security-sensitive authentication/authorization code"
        },
        # Backend API
        r"api|endpoint|rest|graphql|route|controller|middleware": {
            "agent": "backend-architect",
            "skill": "/sc:implement",
            "rationale": "Backend API and routing logic"
        },
        # Frontend UI
        r"component|ui|frontend|react|vue|svelte|css|tailwind|style": {
            "agent": "frontend-architect",
            "skill": "/ui:design",
            "rationale": "Frontend UI components and styling"
        },
        # Testing
        r"test|spec|coverage|mock|fixture|e2e|integration|unit": {
            "agent": "quality-engineer",
            "skill": "/sc:test",
            "rationale": "Test implementation and coverage"
        },
        # Refactoring
        r"refactor|cleanup|debt|reorganize|restructure|simplify": {
            "agent": "refactoring-expert",
            "skill": "/sc:improve",
            "rationale": "Code refactoring and cleanup"
        },
        # Debugging
        r"bug|fix|error|debug|issue|crash|exception|trace": {
            "agent": "root-cause-analyst",
            "skill": "/sc:troubleshoot",
            "rationale": "Bug investigation and fixing"
        },
        # Documentation
        r"doc|readme|comment|jsdoc|docstring|wiki|guide": {
            "agent": "technical-writer",
            "skill": "/sc:document",
            "rationale": "Documentation and comments"
        },
        # Performance
        r"perf|optim|speed|cache|lazy|memo|bundle|profil": {
            "agent": "performance-engineer",
            "skill": "/sc:analyze --focus performance",
            "rationale": "Performance optimization"
        },
        # Database
        r"database|db|sql|query|migration|schema|model|orm": {
            "agent": "backend-architect",
            "skill": "/sc:implement",
            "rationale": "Database operations and models"
        },
        # DevOps/Deployment
        r"deploy|docker|ci|cd|pipeline|kubernetes|infra|cloud": {
            "agent": "devops-architect",
            "skill": "/sc:build",
            "rationale": "DevOps and deployment configuration"
        },
        # Architecture
        r"architect|design|structure|pattern|system|module": {
            "agent": "system-architect",
            "skill": "/sc:design",
            "rationale": "System architecture and design"
        },
    },
    # File path patterns → agent
    "file_patterns": {
        r"\.test\.|\.spec\.|__tests__|tests/": {
            "agent": "quality-engineer",
            "skill": "/sc:test"
        },
        r"\.md$|docs/|documentation/": {
            "agent": "technical-writer",
            "skill": "/sc:document"
        },
        r"components/|pages/|views/|ui/": {
            "agent": "frontend-architect",
            "skill": "/ui:design"
        },
        r"api/|routes/|controllers/|endpoints/": {
            "agent": "backend-architect",
            "skill": "/sc:implement"
        },
        r"auth/|security/|permissions/": {
            "agent": "security-engineer",
            "skill": "/sc:implement --focus security"
        },
        r"models/|schema/|migrations/|db/": {
            "agent": "backend-architect",
            "skill": "/sc:implement"
        },
        r"hooks/|utils/|helpers/|lib/": {
            "agent": "refactoring-expert",
            "skill": "/sc:improve"
        },
        r"config/|\.env|settings/": {
            "agent": "devops-architect",
            "skill": "/sc:build"
        },
    },
    # Complexity-based adjustments
    "complexity_overrides": {
        "high": {
            # For high complexity, prefer more specialized agents
            "default_agent": "system-architect",
            "default_skill": "/sc:design"
        }
    }
}


def match_agent_and_skill(
    subtask: Dict,
    task_description: str = "",
    complexity: str = "medium"
) -> AgentRecommendation:
    """
    Match a subtask to the optimal agent and skill based on content and files.

    Returns AgentRecommendation with agent, skill, confidence, and rationale.
    """
    import re

    name = subtask.get('name', '').lower()
    description = subtask.get('description', '').lower()
    files_modify = subtask.get('files_to_modify', [])
    files_create = subtask.get('files_to_create', [])
    all_files = files_modify + files_create
    prompt = subtask.get('prompt', '').lower()

    # Combined text for pattern matching
    combined_text = f"{name} {description} {prompt} {task_description}".lower()

    matches = []

    # Check task description patterns
    for pattern, config in AGENT_MATCHING["task_patterns"].items():
        if re.search(pattern, combined_text, re.IGNORECASE):
            matches.append({
                "agent": config["agent"],
                "skill": config["skill"],
                "rationale": config.get("rationale", "Pattern match"),
                "confidence": 0.8,
                "source": "task_pattern"
            })

    # Check file path patterns
    for file in all_files:
        for pattern, config in AGENT_MATCHING["file_patterns"].items():
            if re.search(pattern, file, re.IGNORECASE):
                matches.append({
                    "agent": config["agent"],
                    "skill": config["skill"],
                    "rationale": f"File pattern match: {file}",
                    "confidence": 0.7,
                    "source": "file_pattern"
                })

    # If no matches, use defaults based on complexity
    if not matches:
        if complexity == "high":
            override = AGENT_MATCHING["complexity_overrides"]["high"]
            return AgentRecommendation(
                agent=override["default_agent"],
                skill=override["default_skill"],
                confidence=0.4,
                rationale="High complexity task - using system architect"
            )
        return AgentRecommendation(
            agent="general-purpose",
            skill="/sc:implement",
            confidence=0.3,
            rationale="No specific pattern matched - using general agent"
        )

    # Score and rank matches
    agent_scores = {}
    for match in matches:
        agent = match["agent"]
        if agent not in agent_scores:
            agent_scores[agent] = {
                "skill": match["skill"],
                "score": 0,
                "rationales": []
            }
        agent_scores[agent]["score"] += match["confidence"]
        agent_scores[agent]["rationales"].append(match["rationale"])

    # Find best match
    best_agent = max(agent_scores.keys(), key=lambda a: agent_scores[a]["score"])
    best_data = agent_scores[best_agent]

    # Normalize confidence
    confidence = min(best_data["score"] / 2.0, 1.0)  # Cap at 1.0

    return AgentRecommendation(
        agent=best_agent,
        skill=best_data["skill"],
        confidence=confidence,
        rationale="; ".join(best_data["rationales"][:2])  # Top 2 rationales
    )


def enrich_subtasks_with_agents(
    subtasks: List[Dict],
    task_description: str = ""
) -> List[Dict]:
    """
    Enrich subtasks with recommended agents and skills.

    Modifies subtasks in-place and returns them.
    """
    for subtask in subtasks:
        complexity = subtask.get('estimated_complexity', 'medium')
        recommendation = match_agent_and_skill(subtask, task_description, complexity)

        subtask['recommended_agent'] = recommendation.agent
        subtask['recommended_skill'] = recommendation.skill
        subtask['agent_confidence'] = recommendation.confidence
        subtask['agent_rationale'] = recommendation.rationale

    return subtasks


# ============================================================================
# OVERHEAD AND EFFICIENCY CALCULATIONS
# ============================================================================

@dataclass
class OverheadAnalysis:
    """Analysis of parallelization overhead and efficiency."""
    estimated_sequential_minutes: float
    estimated_parallel_minutes: float
    overhead_minutes: float
    efficiency_gain_percent: float
    recommended_splits: int
    break_even_splits: int
    is_worth_parallelizing: bool
    reasoning: str


def calculate_overhead(num_splits: int, config: ParallelConfig = DEFAULT_CONFIG) -> float:
    """Calculate total overhead in seconds for a given number of splits."""
    if num_splits <= 1:
        return 0.0

    # Fixed overhead per session
    per_session = (
        config.worktree_creation_time +
        config.session_startup_time +
        config.context_building_time
    )

    # Merge overhead (sequential, not parallel)
    merge_overhead = num_splits * config.merge_time_per_branch

    # Total overhead
    total = (per_session * num_splits) + merge_overhead

    return total


def calculate_parallel_time(
    sequential_time: float,
    num_splits: int,
    config: ParallelConfig = DEFAULT_CONFIG
) -> Tuple[float, float]:
    """
    Calculate parallel execution time and overhead.

    Returns: (parallel_time, overhead_time) in seconds
    """
    if num_splits <= 1:
        return sequential_time, 0.0

    # Parallel execution: longest subtask determines time
    # Assume roughly equal distribution with some variance
    parallel_execution = sequential_time / num_splits * 1.2  # 20% variance buffer

    overhead = calculate_overhead(num_splits, config)

    total_parallel = parallel_execution + overhead

    return total_parallel, overhead


def find_optimal_splits(
    estimated_sequential_minutes: float,
    max_possible_splits: int,
    config: ParallelConfig = DEFAULT_CONFIG
) -> OverheadAnalysis:
    """
    Find the optimal number of splits considering overhead.

    Returns OverheadAnalysis with recommendation.
    """
    sequential_seconds = estimated_sequential_minutes * 60

    best_splits = 1
    best_time = sequential_seconds
    best_overhead = 0.0

    # Evaluate each possible split count
    analyses = []
    for n in range(1, min(max_possible_splits + 1, config.max_concurrent_sessions + 1)):
        parallel_time, overhead = calculate_parallel_time(sequential_seconds, n, config)

        analyses.append({
            'splits': n,
            'parallel_time': parallel_time,
            'overhead': overhead,
            'total': parallel_time,
            'gain': (sequential_seconds - parallel_time) / sequential_seconds * 100
        })

        if parallel_time < best_time:
            best_time = parallel_time
            best_splits = n
            best_overhead = overhead

    # Find break-even point (where parallelization starts being beneficial)
    break_even = 1
    for a in analyses:
        if a['total'] < sequential_seconds:
            break_even = a['splits']
            break

    # Check minimum thresholds
    is_worth = best_splits > 1
    reasoning_parts = []

    if estimated_sequential_minutes < config.min_task_time_for_2_splits:
        is_worth = False
        best_splits = 1
        reasoning_parts.append(
            f"Task too small ({estimated_sequential_minutes:.1f} min < {config.min_task_time_for_2_splits} min threshold)"
        )

    if best_splits > 1:
        efficiency = (sequential_seconds - best_time) / sequential_seconds * 100
        reasoning_parts.append(
            f"Optimal: {best_splits} parallel tasks saves {efficiency:.0f}% time"
        )
        reasoning_parts.append(
            f"Overhead: {best_overhead/60:.1f} min for setup/merge"
        )
    else:
        reasoning_parts.append("Sequential execution recommended")

    return OverheadAnalysis(
        estimated_sequential_minutes=estimated_sequential_minutes,
        estimated_parallel_minutes=best_time / 60,
        overhead_minutes=best_overhead / 60,
        efficiency_gain_percent=(sequential_seconds - best_time) / sequential_seconds * 100 if best_splits > 1 else 0,
        recommended_splits=best_splits,
        break_even_splits=break_even,
        is_worth_parallelizing=is_worth,
        reasoning=" | ".join(reasoning_parts)
    )


# ============================================================================
# COMPLEXITY SCORING
# ============================================================================

@dataclass
class ComplexityScore:
    """Complexity analysis of a task or repository."""
    total_score: float  # 0.0 - 1.0+
    file_count: int
    estimated_loc: int
    module_count: int
    dependency_score: float
    recent_change_risk: float
    max_parallel_by_structure: int
    breakdown: Dict[str, float]


def analyze_complexity(
    repo_structure: Dict,
    recent_files: List[str],
    task_description: str = "",
    config: ParallelConfig = DEFAULT_CONFIG
) -> ComplexityScore:
    """
    Analyze repository and task complexity.

    Returns ComplexityScore with detailed breakdown.
    """
    # Count files and estimate structure
    total_files = sum(len(files) for files in repo_structure.values())
    module_count = len([k for k in repo_structure.keys() if k not in ['.', '']])

    # Estimate LOC (rough heuristic: 100-300 LOC per file average)
    estimated_loc = total_files * 150

    # Recent change risk
    recent_risk = min(len(recent_files) / 20, 1.0)  # Normalize to 0-1

    # Calculate complexity components
    breakdown = {
        'file_complexity': min(total_files * 0.01, 0.4),
        'module_complexity': min(module_count * 0.05, 0.3),
        'loc_complexity': min(estimated_loc * config.complexity_per_loc_estimate, 0.3),
        'recent_change_risk': recent_risk * 0.2,
    }

    # Task description keywords that indicate complexity
    complex_keywords = [
        'refactor', 'migrate', 'rewrite', 'redesign', 'overhaul',
        'authentication', 'authorization', 'database', 'api',
        'integration', 'performance', 'security', 'testing'
    ]
    task_lower = task_description.lower()
    keyword_hits = sum(1 for kw in complex_keywords if kw in task_lower)
    breakdown['task_keyword_complexity'] = min(keyword_hits * 0.1, 0.3)

    total_score = sum(breakdown.values())

    # Calculate max parallel based on structure
    # Rule: Need at least min_files_per_subtask files per parallel task
    max_by_files = max(1, total_files // config.min_files_per_subtask)
    # Rule: Can't have more parallel tasks than modules (roughly)
    max_by_modules = max(1, module_count)

    max_parallel = min(
        max_by_files,
        max_by_modules,
        config.max_concurrent_sessions
    )

    return ComplexityScore(
        total_score=total_score,
        file_count=total_files,
        estimated_loc=estimated_loc,
        module_count=module_count,
        dependency_score=breakdown.get('module_complexity', 0),
        recent_change_risk=recent_risk,
        max_parallel_by_structure=max_parallel,
        breakdown=breakdown
    )


def estimate_task_time(complexity: ComplexityScore, task_scope: str = "medium") -> float:
    """
    Estimate sequential task time in minutes based on complexity.

    task_scope: "small" | "medium" | "large" | "xlarge"
    """
    scope_multipliers = {
        'small': 5,      # 5-15 minutes
        'medium': 20,    # 20-60 minutes
        'large': 60,     # 1-3 hours
        'xlarge': 180    # 3+ hours
    }

    base_time = scope_multipliers.get(task_scope, 20)

    # Adjust based on complexity
    adjusted = base_time * (1 + complexity.total_score)

    return adjusted


# ============================================================================
# REPOSITORY ANALYSIS
# ============================================================================

def get_repo_structure(max_depth: int = 3) -> dict:
    """Get the repository file structure for context."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return {"error": "Not a git repository"}

    files = result.stdout.strip().split('\n')

    # Group by directory
    structure = {}
    for file in files:
        parts = file.split('/')
        if len(parts) > max_depth:
            key = '/'.join(parts[:max_depth]) + '/...'
        else:
            key = '/'.join(parts[:-1]) if len(parts) > 1 else '.'

        if key not in structure:
            structure[key] = []
        structure[key].append(parts[-1] if len(parts) <= max_depth else '...')

    return structure


def get_recent_changes() -> list:
    """Get recently modified files to avoid conflicts."""
    result = subprocess.run(
        ["git", "log", "--oneline", "-20", "--name-only", "--pretty=format:"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return []

    files = [f for f in result.stdout.strip().split('\n') if f]
    return list(set(files))


def get_existing_worktrees() -> int:
    """Count existing worktrees for this repo."""
    # Use shared infrastructure
    sys.path.insert(0, str(Path(__file__).parent))
    from shared.git_utils import count_worktrees

    try:
        return count_worktrees(Path.cwd())
    except Exception:
        return 0


def check_branch_conflicts(branches: list) -> dict:
    """Check for potential conflicts between branches."""
    conflicts = {}

    for i, branch1 in enumerate(branches):
        for branch2 in branches[i+1:]:
            result1 = subprocess.run(
                ["git", "diff", "--name-only", f"main...{branch1}"],
                capture_output=True,
                text=True
            )
            result2 = subprocess.run(
                ["git", "diff", "--name-only", f"main...{branch2}"],
                capture_output=True,
                text=True
            )

            if result1.returncode != 0 or result2.returncode != 0:
                continue

            files1 = set(result1.stdout.strip().split('\n'))
            files2 = set(result2.stdout.strip().split('\n'))

            overlap = files1 & files2
            if overlap and '' not in overlap:
                conflicts[f"{branch1} <-> {branch2}"] = list(overlap)

    return conflicts


# ============================================================================
# VALIDATION
# ============================================================================

def validate_no_file_conflicts(subtasks: list) -> dict:
    """
    CRITICAL: Validate that subtasks don't have overlapping files.
    Returns validation result with any conflicts found.
    """
    conflicts = []
    file_assignments = {}

    for subtask in subtasks:
        name = subtask.get('name', 'unknown')
        files_to_modify = subtask.get('files_to_modify', [])
        files_to_create = subtask.get('files_to_create', [])
        all_files = set(files_to_modify + files_to_create)

        for file in all_files:
            if file in file_assignments:
                conflicts.append({
                    "file": file,
                    "subtask1": file_assignments[file],
                    "subtask2": name,
                    "severity": "HIGH"
                })
            else:
                file_assignments[file] = name

    return {
        "valid": len(conflicts) == 0,
        "conflicts": conflicts,
        "file_assignments": file_assignments
    }


def validate_resource_constraints(
    num_splits: int,
    config: ParallelConfig = DEFAULT_CONFIG
) -> Dict:
    """Validate that proposed splits don't exceed resource constraints."""
    existing_worktrees = get_existing_worktrees()
    available_worktrees = config.max_worktrees - existing_worktrees

    issues = []

    if num_splits > config.max_concurrent_sessions:
        issues.append(f"Exceeds max concurrent sessions ({config.max_concurrent_sessions})")

    if num_splits > available_worktrees:
        issues.append(f"Exceeds available worktrees ({available_worktrees} available)")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "existing_worktrees": existing_worktrees,
        "available_worktrees": available_worktrees,
        "max_concurrent": config.max_concurrent_sessions
    }


# ============================================================================
# AI-POWERED TASK SPLITTING
# ============================================================================

def split_task_with_claude(
    task: str,
    repo_structure: dict,
    recent_files: list,
    complexity: ComplexityScore,
    overhead_analysis: OverheadAnalysis,
    config: ParallelConfig = DEFAULT_CONFIG
) -> dict:
    """Use Claude API to split task into optimal number of parallel subtasks."""
    if not HAS_ANTHROPIC:
        return {
            "error": "anthropic package not installed. Run: pip install anthropic",
            "fallback": generate_fallback_split(task, overhead_analysis.recommended_splits)
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "fallback": generate_fallback_split(task, overhead_analysis.recommended_splits)
        }

    client = anthropic.Anthropic(api_key=api_key)

    # Dynamic split recommendation based on analysis
    recommended = overhead_analysis.recommended_splits
    max_splits = min(
        complexity.max_parallel_by_structure,
        config.max_concurrent_sessions,
        10  # Hard upper limit
    )

    prompt = f"""Analyze this development task and split it into the OPTIMAL number of independent subtasks
that can be executed in parallel by different AI agents WITHOUT CAUSING MERGE CONFLICTS.

TASK: {task}

PARALLELIZATION ANALYSIS (pre-computed):
- Recommended splits: {recommended} (based on overhead analysis)
- Maximum possible splits: {max_splits} (based on repository structure)
- Estimated sequential time: {overhead_analysis.estimated_sequential_minutes:.0f} minutes
- Worth parallelizing: {overhead_analysis.is_worth_parallelizing}
- Repository complexity score: {complexity.total_score:.2f}
- Number of modules: {complexity.module_count}

REPOSITORY STRUCTURE:
{json.dumps(repo_structure, indent=2)}

RECENTLY MODIFIED FILES (high conflict risk - AVOID these):
{json.dumps(recent_files, indent=2)}

OPTIMIZATION GUIDELINES:
1. Split into {recommended} to {max_splits} subtasks based on natural boundaries
2. Each additional split adds ~{calculate_overhead(2, config)/60:.1f} min overhead
3. Only create more splits if the task genuinely has independent components
4. Fewer splits is better if components are tightly coupled
5. Consider: Is the overhead worth it for this split?

CRITICAL REQUIREMENTS FOR CONFLICT-FREE SPLITTING:
1. Each subtask MUST modify COMPLETELY DIFFERENT FILES
2. NO file should appear in more than one subtask's files_to_modify or files_to_create
3. If a task cannot be split without file overlap, return fewer subtasks
4. Prefer creating NEW files over modifying existing shared files
5. Tests should be in separate test files per subtask
6. Shared utilities should be handled by ONE subtask only, others import it

CONFLICT PREVENTION STRATEGIES:
- Split by feature boundary (auth vs api vs ui)
- Split by layer (backend vs frontend vs tests)
- Split by module/directory
- If touching same file is unavoidable, DO NOT SPLIT that part

Output JSON format:
{{
    "analysis": "Brief analysis of the task and splitting strategy",
    "optimal_splits": <number>,
    "splitting_rationale": "Why this number of splits is optimal",
    "conflict_risk": "LOW|MEDIUM|HIGH",
    "can_parallelize": true/false,
    "reason_if_not": "Why it can't be safely parallelized (if applicable)",
    "subtasks": [
        {{
            "name": "short-branch-name",
            "description": "What this subtask accomplishes",
            "files_to_modify": ["file1.py"],
            "files_to_create": ["new_file.py"],
            "files_to_read_only": ["shared_config.py"],
            "prompt": "Detailed prompt for Claude Code - MUST specify exact files to touch",
            "dependencies": [],
            "estimated_complexity": "low|medium|high",
            "estimated_minutes": <number>
        }}
    ],
    "file_ownership": {{"file.py": "subtask-name"}},
    "merge_order": ["subtask1", "subtask2"],
    "potential_conflicts": ["description of any unavoidable conflicts"],
    "integration_notes": "How to integrate the subtasks after completion"
}}
"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text

        # Extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())

            # Validate no file conflicts
            subtasks = result.get('subtasks', [])
            if subtasks:
                validation = validate_no_file_conflicts(subtasks)
                result['validation'] = validation

                if not validation['valid']:
                    result['conflict_risk'] = 'HIGH'
                    result['validation_failed'] = True
                    result['conflict_details'] = validation['conflicts']
                    print("WARNING: File conflicts detected in proposed split!", file=sys.stderr)
                    for conflict in validation['conflicts']:
                        print(f"  - {conflict['file']}: {conflict['subtask1']} vs {conflict['subtask2']}", file=sys.stderr)

                # Enrich subtasks with agent/skill recommendations
                result['subtasks'] = enrich_subtasks_with_agents(subtasks, task)

                # Create agent summary
                agent_summary = {}
                for st in result['subtasks']:
                    agent = st.get('recommended_agent', 'general-purpose')
                    if agent not in agent_summary:
                        agent_summary[agent] = []
                    agent_summary[agent].append(st.get('name', 'unknown'))
                result['agent_assignments'] = agent_summary

            # Add overhead analysis to result
            result['overhead_analysis'] = asdict(overhead_analysis)
            result['complexity_analysis'] = asdict(complexity)

            # Validate resource constraints
            num_subtasks = len(subtasks)
            resource_check = validate_resource_constraints(num_subtasks, config)
            result['resource_validation'] = resource_check

            if not resource_check['valid']:
                result['resource_warning'] = resource_check['issues']

            return result
        else:
            return {"raw_response": response_text}

    except Exception as e:
        return {
            "error": str(e),
            "fallback": generate_fallback_split(task, overhead_analysis.recommended_splits)
        }


def generate_fallback_split(task: str, recommended_splits: int = 2) -> list:
    """Generate a basic task split without AI."""
    keywords = {
        "auth": ["auth-backend", "auth-frontend", "auth-tests"],
        "api": ["api-endpoints", "api-validation", "api-tests"],
        "ui": ["ui-components", "ui-styles", "ui-tests"],
        "test": ["unit-tests", "integration-tests", "e2e-tests"],
        "refactor": ["refactor-core", "refactor-utils", "update-tests"],
        "database": ["db-schema", "db-migrations", "db-queries"],
        "frontend": ["frontend-components", "frontend-state", "frontend-styles"],
        "backend": ["backend-routes", "backend-services", "backend-models"],
    }

    task_lower = task.lower()
    for key, branches in keywords.items():
        if key in task_lower:
            return [
                {"name": b, "description": f"Part of: {task}"}
                for b in branches[:recommended_splits]
            ]

    # Default split
    default_splits = [
        {"name": "implementation", "description": "Core implementation"},
        {"name": "tests", "description": "Tests and validation"},
        {"name": "integration", "description": "Integration and cleanup"},
    ]
    return default_splits[:recommended_splits]


# ============================================================================
# REPOSITORY ANALYSIS MODE
# ============================================================================

def analyze_repo(config: ParallelConfig = DEFAULT_CONFIG) -> dict:
    """Analyze repository for parallelization opportunities."""
    structure = get_repo_structure()
    recent = get_recent_changes()
    complexity = analyze_complexity(structure, recent)

    # Find independent modules
    modules = {}
    for path in structure.keys():
        if path in ['.', '']:
            continue
        top_level = path.split('/')[0]
        if top_level not in modules:
            modules[top_level] = {"files": 0, "recent_changes": 0}
        modules[top_level]["files"] += len(structure[path])
        modules[top_level]["recent_changes"] += sum(1 for f in recent if f.startswith(top_level))

    # Identify parallelization opportunities
    opportunities = []
    for module, data in modules.items():
        if data["files"] >= config.min_files_per_subtask and data["recent_changes"] < 3:
            opportunities.append({
                "module": module,
                "files": data["files"],
                "recent_changes": data["recent_changes"],
                "parallelization_safe": data["recent_changes"] == 0
            })

    # Sort by safety and size
    opportunities.sort(key=lambda x: (-x["parallelization_safe"], -x["files"]))

    return {
        "total_files": complexity.file_count,
        "estimated_loc": complexity.estimated_loc,
        "module_count": complexity.module_count,
        "complexity_score": complexity.total_score,
        "modules": modules,
        "recent_changes": recent[:10],
        "parallelization_opportunities": opportunities,
        "max_recommended_parallel": complexity.max_parallel_by_structure,
        "existing_worktrees": get_existing_worktrees(),
        "resource_limits": {
            "max_concurrent_sessions": config.max_concurrent_sessions,
            "max_worktrees": config.max_worktrees
        }
    }


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered task splitting with overhead optimization"
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="Task description to split"
    )
    parser.add_argument(
        "--check-conflicts",
        nargs="+",
        metavar="BRANCH",
        help="Check for conflicts between branches"
    )
    parser.add_argument(
        "--analyze-repo",
        action="store_true",
        help="Analyze repository for parallelization opportunities"
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="text",
        help="Output format"
    )
    parser.add_argument(
        "--max-splits",
        type=int,
        default=None,
        help="Maximum number of splits to consider"
    )
    parser.add_argument(
        "--task-scope",
        choices=["small", "medium", "large", "xlarge"],
        default="medium",
        help="Estimated task scope for time calculation"
    )
    parser.add_argument(
        "--show-overhead",
        action="store_true",
        help="Show detailed overhead analysis"
    )

    args = parser.parse_args()
    config = DEFAULT_CONFIG

    # Repository analysis mode
    if args.analyze_repo:
        result = analyze_repo(config)
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            print("\n" + "="*60)
            print("REPOSITORY ANALYSIS")
            print("="*60)
            print(f"\nTotal files: {result['total_files']}")
            print(f"Estimated LOC: {result['estimated_loc']:,}")
            print(f"Modules: {result['module_count']}")
            print(f"Complexity score: {result['complexity_score']:.2f}")
            print(f"Max recommended parallel: {result['max_recommended_parallel']}")
            print(f"\nModules:")
            for name, data in result['modules'].items():
                status = "✓" if data['recent_changes'] == 0 else f"⚠ {data['recent_changes']} recent"
                print(f"  {name}: {data['files']} files [{status}]")
            print(f"\nParallelization opportunities:")
            for opp in result['parallelization_opportunities'][:5]:
                safe = "SAFE" if opp['parallelization_safe'] else "CAUTION"
                print(f"  {opp['module']}: {opp['files']} files [{safe}]")
            print(f"\nResource limits:")
            print(f"  Existing worktrees: {result['existing_worktrees']}")
            print(f"  Max concurrent: {result['resource_limits']['max_concurrent_sessions']}")
        return

    # Conflict check mode
    if args.check_conflicts:
        conflicts = check_branch_conflicts(args.check_conflicts)
        if args.output == "json":
            print(json.dumps(conflicts, indent=2))
        else:
            if conflicts:
                print("\n" + "="*60)
                print("CONFLICT ANALYSIS")
                print("="*60)
                for pair, files in conflicts.items():
                    print(f"\n⚠ {pair}:")
                    for f in files:
                        print(f"    - {f}")
            else:
                print("\n✓ No conflicts detected between branches.")
        return

    # Task splitting mode
    if not args.task:
        parser.print_help()
        return

    print(f"\nAnalyzing task: {args.task}\n")

    # Gather data
    structure = get_repo_structure()
    recent = get_recent_changes()

    # Analyze complexity
    complexity = analyze_complexity(structure, recent, args.task, config)

    # Estimate task time
    estimated_time = estimate_task_time(complexity, args.task_scope)

    # Determine max splits
    max_splits = args.max_splits or complexity.max_parallel_by_structure

    # Calculate optimal parallelization
    overhead_analysis = find_optimal_splits(estimated_time, max_splits, config)

    # Show overhead analysis if requested
    if args.show_overhead or args.output == "text":
        print("="*60)
        print("OVERHEAD ANALYSIS")
        print("="*60)
        print(f"Estimated sequential time: {overhead_analysis.estimated_sequential_minutes:.0f} min")
        print(f"Recommended splits: {overhead_analysis.recommended_splits}")
        print(f"Break-even at: {overhead_analysis.break_even_splits} splits")
        if overhead_analysis.is_worth_parallelizing:
            print(f"Estimated parallel time: {overhead_analysis.estimated_parallel_minutes:.1f} min")
            print(f"Overhead: {overhead_analysis.overhead_minutes:.1f} min")
            print(f"Efficiency gain: {overhead_analysis.efficiency_gain_percent:.0f}%")
        print(f"Recommendation: {overhead_analysis.reasoning}")
        print()

    # Split the task
    result = split_task_with_claude(
        args.task, structure, recent, complexity, overhead_analysis, config
    )

    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            print(f"Warning: {result['error']}")
            if "fallback" in result:
                print("\nFallback split:")
                for subtask in result["fallback"]:
                    print(f"  - {subtask['name']}: {subtask['description']}")
        else:
            print("="*60)
            print("TASK ANALYSIS")
            print("="*60)
            if "analysis" in result:
                print(f"\n{result['analysis']}")

            if "splitting_rationale" in result:
                print(f"\nRationale: {result['splitting_rationale']}")

            print(f"\nConflict risk: {result.get('conflict_risk', 'UNKNOWN')}")
            print(f"Can parallelize: {result.get('can_parallelize', 'unknown')}")

            print("\n" + "="*60)
            print("SUBTASKS WITH AGENT RECOMMENDATIONS")
            print("="*60)
            for i, subtask in enumerate(result.get("subtasks", []), 1):
                print(f"\n{i}. {subtask['name']}")
                print(f"   Description: {subtask.get('description', 'N/A')}")
                print(f"   Files to modify: {', '.join(subtask.get('files_to_modify', [])) or 'None'}")
                print(f"   Files to create: {', '.join(subtask.get('files_to_create', [])) or 'None'}")
                print(f"   Complexity: {subtask.get('estimated_complexity', 'unknown')}")
                if 'estimated_minutes' in subtask:
                    print(f"   Estimated time: {subtask['estimated_minutes']} min")
                # Agent recommendation
                agent = subtask.get('recommended_agent', 'general-purpose')
                skill = subtask.get('recommended_skill', '/sc:implement')
                confidence = subtask.get('agent_confidence', 0)
                rationale = subtask.get('agent_rationale', '')
                conf_bar = "█" * int(confidence * 5) + "░" * (5 - int(confidence * 5))
                print(f"   🤖 Agent: {agent} [{conf_bar}] {confidence:.0%}")
                print(f"   ⚡ Skill: {skill}")
                if rationale:
                    print(f"   💡 Why: {rationale}")

            # Agent summary
            if result.get('agent_assignments'):
                print("\n" + "="*60)
                print("AGENT ASSIGNMENT SUMMARY")
                print("="*60)
                for agent, tasks in result['agent_assignments'].items():
                    print(f"\n  {agent}:")
                    for task_name in tasks:
                        print(f"    → {task_name}")

            if result.get("validation", {}).get("valid") == False:
                print("\n⚠ WARNING: File conflicts detected!")
                for conflict in result.get("conflict_details", []):
                    print(f"   {conflict['file']}: {conflict['subtask1']} vs {conflict['subtask2']}")

            if "merge_order" in result:
                print(f"\nMerge order: {' → '.join(result['merge_order'])}")

            if result.get("potential_conflicts"):
                print(f"\nPotential conflicts: {', '.join(result['potential_conflicts'])}")

            if "integration_notes" in result:
                print(f"\nIntegration: {result['integration_notes']}")

            # Resource validation
            if result.get("resource_warning"):
                print("\n⚠ RESOURCE WARNINGS:")
                for warning in result["resource_warning"]:
                    print(f"   - {warning}")

            # Print commands
            subtasks = result.get("subtasks", [])
            if subtasks and result.get('can_parallelize', False):
                print("\n" + "="*60)
                print("COMMANDS TO EXECUTE")
                print("="*60)
                branch_names = [s["name"] for s in subtasks]
                print(f"\n# Create worktrees:")
                print(f"setup-worktree.sh {' '.join(branch_names)}")
                print(f"\n# Run in parallel:")
                print(f"run-parallel.sh --tasks \"{','.join(branch_names)}\"")

                # Show agent-specific tmux commands
                print(f"\n# Or run with specialized agents (recommended):")
                print("tmux new-session -d -s claude-parallel")
                for i, subtask in enumerate(subtasks):
                    agent = subtask.get('recommended_agent', 'general-purpose')
                    skill = subtask.get('recommended_skill', '/sc:implement')
                    name = subtask.get('name', f'task-{i}')
                    worktree_path = f"../{name}"

                    if i == 0:
                        print(f"tmux send-keys 'cd {worktree_path} && claude --agent {agent}' Enter")
                    else:
                        print(f"tmux new-window -t claude-parallel -n '{name}'")
                        print(f"tmux send-keys -t claude-parallel:'{name}' 'cd {worktree_path} && claude --agent {agent}' Enter")

                print("tmux attach -t claude-parallel")

                # Show skill invocation for each task
                print(f"\n# Initial prompts per agent:")
                for subtask in subtasks:
                    name = subtask.get('name', 'unknown')
                    skill = subtask.get('recommended_skill', '/sc:implement')
                    desc = subtask.get('description', '')[:50]
                    print(f"#   {name}: {skill} \"{desc}...\"")

                # Show efficiency summary
                oa = result.get('overhead_analysis', {})
                if oa:
                    print(f"\n# Expected efficiency:")
                    print(f"#   Sequential: ~{oa.get('estimated_sequential_minutes', 0):.0f} min")
                    print(f"#   Parallel:   ~{oa.get('estimated_parallel_minutes', 0):.0f} min")
                    print(f"#   Savings:    ~{oa.get('efficiency_gain_percent', 0):.0f}%")

                    # Calculate potential additional gain from specialization
                    num_specialized = sum(1 for s in subtasks if s.get('agent_confidence', 0) > 0.6)
                    if num_specialized > 0:
                        specialization_bonus = num_specialized * 5  # ~5% per specialized agent
                        print(f"#   + Specialization bonus: ~{specialization_bonus}% (est.)")


if __name__ == "__main__":
    main()
