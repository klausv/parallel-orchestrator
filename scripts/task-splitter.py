#!/usr/bin/env python3
"""
task-splitter.py - AI-powered task decomposition with conflict detection

Uses Claude API to analyze a task and split it into non-conflicting subtasks
that can be executed in parallel without merge conflicts.

Usage:
    python3 task-splitter.py "Implement user authentication with tests"
    python3 task-splitter.py --check-conflicts feature-a feature-b
    python3 task-splitter.py --analyze-repo
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


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
            # Truncate deep paths
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


def check_branch_conflicts(branches: list) -> dict:
    """Check for potential conflicts between branches."""
    conflicts = {}

    for i, branch1 in enumerate(branches):
        for branch2 in branches[i+1:]:
            # Get files modified in each branch
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


def validate_no_file_conflicts(subtasks: list) -> dict:
    """
    CRITICAL: Validate that subtasks don't have overlapping files.
    Returns validation result with any conflicts found.
    """
    conflicts = []
    file_assignments = {}  # file -> subtask that owns it

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


def split_task_with_claude(task: str, repo_structure: dict, recent_files: list) -> dict:
    """Use Claude API to split task into parallel subtasks."""
    if not HAS_ANTHROPIC:
        return {
            "error": "anthropic package not installed. Run: pip install anthropic",
            "fallback": generate_fallback_split(task)
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not set",
            "fallback": generate_fallback_split(task)
        }

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Analyze this development task and split it into 2-3 independent subtasks
that can be executed in parallel by different AI agents WITHOUT CAUSING MERGE CONFLICTS.

TASK: {task}

REPOSITORY STRUCTURE:
{json.dumps(repo_structure, indent=2)}

RECENTLY MODIFIED FILES (STRICTLY AVOID - high conflict risk):
{json.dumps(recent_files, indent=2)}

CRITICAL REQUIREMENTS FOR CONFLICT-FREE SPLITTING:
1. Each subtask MUST modify COMPLETELY DIFFERENT FILES
2. NO file should appear in more than one subtask's files_to_modify or files_to_create
3. If a task cannot be split without file overlap, return fewer subtasks or just one
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
    "analysis": "Brief analysis of the task",
    "conflict_risk": "LOW|MEDIUM|HIGH",
    "can_parallelize": true/false,
    "reason_if_not": "Why it can't be safely parallelized",
    "subtasks": [
        {{
            "name": "short-branch-name",
            "description": "What this subtask accomplishes",
            "files_to_modify": ["file1.py"],
            "files_to_create": ["new_file.py"],
            "files_to_read_only": ["shared_config.py"],
            "prompt": "Detailed prompt for Claude Code - MUST mention which files to touch",
            "dependencies": [],
            "estimated_complexity": "low|medium|high"
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
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract JSON from response
        response_text = message.content[0].text

        # Try to find JSON in response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())

            # CRITICAL: Validate no file conflicts in the proposed split
            subtasks = result.get('subtasks', [])
            if subtasks:
                validation = validate_no_file_conflicts(subtasks)
                result['validation'] = validation

                if not validation['valid']:
                    result['conflict_risk'] = 'HIGH'
                    result['validation_failed'] = True
                    result['conflict_details'] = validation['conflicts']

                    # Try to fix by removing conflicting subtasks
                    print("WARNING: File conflicts detected in proposed split!", file=sys.stderr)
                    for conflict in validation['conflicts']:
                        print(f"  - {conflict['file']}: {conflict['subtask1']} vs {conflict['subtask2']}", file=sys.stderr)

            return result
        else:
            return {"raw_response": response_text}

    except Exception as e:
        return {
            "error": str(e),
            "fallback": generate_fallback_split(task)
        }


def generate_fallback_split(task: str) -> list:
    """Generate a basic task split without AI."""
    # Simple heuristic-based splitting
    keywords = {
        "auth": ["auth-backend", "auth-frontend", "auth-tests"],
        "api": ["api-endpoints", "api-validation", "api-tests"],
        "ui": ["ui-components", "ui-styles", "ui-tests"],
        "test": ["unit-tests", "integration-tests", "e2e-tests"],
        "refactor": ["refactor-core", "refactor-utils", "update-tests"],
    }

    task_lower = task.lower()
    for key, branches in keywords.items():
        if key in task_lower:
            return [{"name": b, "description": f"Part of: {task}"} for b in branches]

    # Default split
    return [
        {"name": "implementation", "description": "Core implementation"},
        {"name": "tests", "description": "Tests and validation"},
    ]


def analyze_repo() -> dict:
    """Analyze repository for parallelization opportunities."""
    structure = get_repo_structure()
    recent = get_recent_changes()

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

    return {
        "total_files": sum(len(v) for v in structure.values()),
        "modules": modules,
        "recent_changes": recent[:10],
        "parallelization_opportunities": [
            m for m, data in modules.items()
            if data["files"] > 5 and data["recent_changes"] < 3
        ]
    }


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered task splitting for parallel execution"
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

    args = parser.parse_args()

    if args.analyze_repo:
        result = analyze_repo()
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            print("\n=== Repository Analysis ===")
            print(f"Total files: {result['total_files']}")
            print(f"\nModules:")
            for name, data in result['modules'].items():
                print(f"  {name}: {data['files']} files, {data['recent_changes']} recent changes")
            print(f"\nGood for parallel work: {', '.join(result['parallelization_opportunities'])}")
        return

    if args.check_conflicts:
        conflicts = check_branch_conflicts(args.check_conflicts)
        if args.output == "json":
            print(json.dumps(conflicts, indent=2))
        else:
            if conflicts:
                print("\n=== Potential Conflicts ===")
                for pair, files in conflicts.items():
                    print(f"\n{pair}:")
                    for f in files:
                        print(f"  - {f}")
            else:
                print("\nNo conflicts detected between branches.")
        return

    if not args.task:
        parser.print_help()
        return

    # Split the task
    print(f"\nAnalyzing task: {args.task}\n")

    structure = get_repo_structure()
    recent = get_recent_changes()

    result = split_task_with_claude(args.task, structure, recent)

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
            print("=== Task Analysis ===")
            if "analysis" in result:
                print(f"\n{result['analysis']}\n")

            print("=== Subtasks ===")
            for i, subtask in enumerate(result.get("subtasks", []), 1):
                print(f"\n{i}. {subtask['name']}")
                print(f"   Description: {subtask.get('description', 'N/A')}")
                print(f"   Files to modify: {', '.join(subtask.get('files_to_modify', []))}")
                print(f"   Complexity: {subtask.get('estimated_complexity', 'unknown')}")

            if "merge_order" in result:
                print(f"\nMerge order: {' -> '.join(result['merge_order'])}")

            if result.get("potential_conflicts"):
                print(f"\nPotential conflicts: {', '.join(result['potential_conflicts'])}")

            if "integration_notes" in result:
                print(f"\nIntegration: {result['integration_notes']}")

            # Print commands to execute
            print("\n=== Commands to Execute ===")
            subtasks = result.get("subtasks", [])
            if subtasks:
                branch_names = [s["name"] for s in subtasks]
                print(f"\n# Create worktrees:")
                print(f"setup-worktree.sh {' '.join(branch_names)}")
                print(f"\n# Run in parallel:")
                print(f"run-parallel.sh --tasks \"{','.join(branch_names)}\"")


if __name__ == "__main__":
    main()
