#!/usr/bin/env python3
"""
Subprocess Execution Utilities

Shared utilities for running commands with proper error handling and logging.
Extracted from test_executor.py and various other modules.
"""

import subprocess
import logging
import time
from pathlib import Path
from typing import Optional, List, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of command execution with complete context."""
    stdout: str
    stderr: str
    exit_code: int
    duration: float
    command: str
    cwd: Optional[str] = None
    timed_out: bool = False
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if command succeeded (exit_code == 0)"""
        return self.exit_code == 0

    @property
    def failed(self) -> bool:
        """Check if command failed (exit_code != 0)"""
        return self.exit_code != 0

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else f"FAILED({self.exit_code})"
        return f"CommandResult({status}, duration={self.duration:.1f}s)"


def run_command(
    cmd: Union[str, List[str]],
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    check: bool = False,
    env: Optional[dict] = None,
    input_text: Optional[str] = None
) -> CommandResult:
    """
    Run a command and return comprehensive result.

    Args:
        cmd: Command to run (string or list of args)
        cwd: Working directory for command
        timeout: Optional timeout in seconds
        check: If True, raise exception on non-zero exit code
        env: Optional environment variables
        input_text: Optional stdin input

    Returns:
        CommandResult with all execution details

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
        subprocess.TimeoutExpired: If command exceeds timeout
    """
    start_time = time.time()

    # Convert string command to list if needed
    if isinstance(cmd, str):
        cmd_str = cmd
        cmd_list = cmd.split()
    else:
        cmd_str = ' '.join(cmd)
        cmd_list = cmd

    # Convert Path to str for cwd
    cwd_str = str(cwd) if cwd else None

    logger.debug(f"Running command: {cmd_str}" + (f" in {cwd_str}" if cwd_str else ""))

    try:
        result = subprocess.run(
            cmd_list,
            cwd=cwd_str,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            env=env,
            input=input_text
        )

        duration = time.time() - start_time
        exit_code = result.returncode

        logger.debug(
            f"Command completed: exit_code={exit_code}, duration={duration:.1f}s"
        )

        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=exit_code,
            duration=duration,
            command=cmd_str,
            cwd=cwd_str,
            timed_out=False
        )

    except subprocess.TimeoutExpired as e:
        duration = time.time() - start_time
        logger.warning(f"Command timed out after {duration:.1f}s: {cmd_str}")

        return CommandResult(
            stdout=e.stdout.decode() if e.stdout else "",
            stderr=e.stderr.decode() if e.stderr else "",
            exit_code=124,  # Standard timeout exit code
            duration=duration,
            command=cmd_str,
            cwd=cwd_str,
            timed_out=True,
            error_message=f"Command exceeded {timeout}s timeout"
        )

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        logger.error(f"Command failed: {cmd_str} (exit_code={e.returncode})")

        return CommandResult(
            stdout=e.stdout if e.stdout else "",
            stderr=e.stderr if e.stderr else "",
            exit_code=e.returncode,
            duration=duration,
            command=cmd_str,
            cwd=cwd_str,
            error_message=str(e)
        )

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Command execution error: {e}")

        return CommandResult(
            stdout="",
            stderr=str(e),
            exit_code=1,
            duration=duration,
            command=cmd_str,
            cwd=cwd_str,
            error_message=str(e)
        )


def run_command_async(
    cmd: Union[str, List[str]],
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[dict] = None
) -> subprocess.Popen:
    """
    Run a command asynchronously (non-blocking).

    Args:
        cmd: Command to run (string or list of args)
        cwd: Working directory for command
        env: Optional environment variables

    Returns:
        Popen object for process control

    Example:
        proc = run_command_async("python script.py", cwd="/path")
        # Do other work...
        proc.wait()  # Wait for completion
    """
    # Convert string command to list if needed
    if isinstance(cmd, str):
        cmd_list = cmd.split()
    else:
        cmd_list = cmd

    # Convert Path to str for cwd
    cwd_str = str(cwd) if cwd else None

    logger.debug(f"Starting async command: {' '.join(cmd_list)}")

    return subprocess.Popen(
        cmd_list,
        cwd=cwd_str,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )


def run_script(
    script_path: Union[str, Path],
    args: Optional[List[str]] = None,
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    check: bool = False
) -> CommandResult:
    """
    Run a script file (bash, python, etc.) with arguments.

    Args:
        script_path: Path to script file
        args: Optional script arguments
        cwd: Working directory
        timeout: Optional timeout in seconds
        check: If True, raise exception on failure

    Returns:
        CommandResult with execution details
    """
    script = Path(script_path)

    if not script.exists():
        logger.error(f"Script not found: {script}")
        return CommandResult(
            stdout="",
            stderr=f"Script not found: {script}",
            exit_code=1,
            duration=0.0,
            command=str(script),
            cwd=str(cwd) if cwd else None,
            error_message="Script not found"
        )

    # Build command
    cmd = [str(script)]
    if args:
        cmd.extend(args)

    return run_command(cmd, cwd=cwd, timeout=timeout, check=check)


def run_shell_script(
    script_content: str,
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[float] = None,
    shell: str = "/bin/bash"
) -> CommandResult:
    """
    Run shell script from string content (useful for dynamic scripts).

    Args:
        script_content: Script content as string
        cwd: Working directory
        timeout: Optional timeout in seconds
        shell: Shell to use (default: /bin/bash)

    Returns:
        CommandResult with execution details
    """
    cmd = [shell, "-c", script_content]

    return run_command(cmd, cwd=cwd, timeout=timeout)


class CommandRunner:
    """
    Stateful command runner with default settings.

    Useful for running multiple commands with same configuration.
    """

    def __init__(
        self,
        default_cwd: Optional[Union[str, Path]] = None,
        default_timeout: Optional[float] = None,
        default_env: Optional[dict] = None,
        check: bool = False
    ):
        """
        Initialize command runner with defaults.

        Args:
            default_cwd: Default working directory
            default_timeout: Default timeout in seconds
            default_env: Default environment variables
            check: Default check behavior
        """
        self.default_cwd = default_cwd
        self.default_timeout = default_timeout
        self.default_env = default_env
        self.check = check
        self.command_history: List[CommandResult] = []

    def run(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
        env: Optional[dict] = None,
        check: Optional[bool] = None
    ) -> CommandResult:
        """
        Run command with default settings.

        Args override defaults if provided.
        """
        result = run_command(
            cmd=cmd,
            cwd=cwd or self.default_cwd,
            timeout=timeout or self.default_timeout,
            env=env or self.default_env,
            check=check if check is not None else self.check
        )

        self.command_history.append(result)
        return result

    def get_last_result(self) -> Optional[CommandResult]:
        """Get result of last command run."""
        return self.command_history[-1] if self.command_history else None

    def get_failed_commands(self) -> List[CommandResult]:
        """Get all failed commands from history."""
        return [r for r in self.command_history if r.failed]

    def clear_history(self) -> None:
        """Clear command history."""
        self.command_history.clear()
