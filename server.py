import os
import asyncio
import signal
from pathlib import Path
import json
from typing import Dict, Any, List, Optional

from mcp.server.fastmcp import FastMCP

# Initialize the MCP server
"""
NOTE: This server uses MCP stdio transport. Do not print to stdout,
as it can corrupt the protocol. For visibility in MCP clients, we print
progress and logs to stderr with flush=True so they appear in real time.
"""

mcp = FastMCP("file-server")

# Set the base directory where we'll read and write files
BASE_DIR = "/data"  # This will be mapped to your local directory in Docker

# --- Configuration helpers ---
DEFAULT_MAX_LINES = 1000

def _parse_positive_int(value: Any) -> Optional[int]:
    try:
        n = int(str(value).strip())
        return n if n > 0 else None
    except Exception:
        return None

def _load_max_lines_from_config_file() -> Optional[int]:
    # Config path can be overridden via env var; else default alongside server.py
    cfg_path_env = os.getenv("FILE_SERVER_CONFIG_PATH")
    cfg_path = Path(cfg_path_env) if cfg_path_env else Path(__file__).with_name("config.json")
    try:
        if cfg_path.is_file():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                # Prefer nested run_command.max_lines, fallback to top-level max_lines
                rc = cfg.get("run_command")
                if isinstance(rc, dict):
                    ml = _parse_positive_int(rc.get("max_lines"))
                    if ml is not None:
                        return ml
                ml2 = _parse_positive_int(cfg.get("max_lines"))
                if ml2 is not None:
                    return ml2
    except Exception:
        # Ignore config errors and fall back to defaults/env
        pass
    return None

def _resolve_max_output_lines() -> int:
    # Env vars take precedence
    for env_name in ("RUN_COMMAND_MAX_LINES", "MAX_OUTPUT_LINES"):
        env_val = os.getenv(env_name)
        ml = _parse_positive_int(env_val) if env_val is not None else None
        if ml is not None:
            return ml
    # Then config file
    ml_cfg = _load_max_lines_from_config_file()
    if ml_cfg is not None:
        return ml_cfg
    # Default
    return DEFAULT_MAX_LINES

# Resolved at import time
MAX_OUTPUT_LINES = _resolve_max_output_lines()

@mcp.tool()
async def list_files(path: str = "") -> str:
    """List all files in the specified directory.
    
    Args:
        path: Optional subdirectory path relative to the base directory
    """
    target_dir = os.path.normpath(os.path.join(BASE_DIR, path))
    
    # Security check to prevent directory traversal
    if not target_dir.startswith(BASE_DIR):
        return f"Error: Cannot access directories outside of the base directory."
    
    try:
        files = os.listdir(target_dir)
        file_info = []
        
        for file in files:
            full_path = os.path.join(target_dir, file)
            is_dir = os.path.isdir(full_path)
            size = os.path.getsize(full_path) if not is_dir else "-"
            file_type = "Directory" if is_dir else "File"
            
            file_info.append({
                "name": file,
                "type": file_type,
                "size": size
            })
        
        return json.dumps(file_info, indent=2)
    except Exception as e:
        return f"Error listing files: {str(e)}"

@mcp.tool()
async def read_file(file_path: str) -> str:
    """Read the contents of a file.
    
    Args:
        file_path: Path to the file relative to the base directory
    """
    target_file = os.path.normpath(os.path.join(BASE_DIR, file_path))
    
    # Security check to prevent directory traversal
    if not target_file.startswith(BASE_DIR):
        return f"Error: Cannot access files outside of the base directory."
    
    try:
        if not os.path.isfile(target_file):
            return f"Error: File does not exist or is not a file: {file_path}"
        
        with open(target_file, 'r') as f:
            content = f.read()
        
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool()
async def write_file(file_path: str, content: str) -> str:
    """Write content to a file.
    
    Args:
        file_path: Path to the file relative to the base directory
        content: Content to write to the file
    """
    target_file = os.path.normpath(os.path.join(BASE_DIR, file_path))
    
    # Security check to prevent directory traversal
    if not target_file.startswith(BASE_DIR):
        return f"Error: Cannot access files outside of the base directory."
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        
        with open(target_file, 'w') as f:
            f.write(content)
        
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing to file: {str(e)}"

@mcp.tool()
async def delete_file(file_path: str) -> str:
    """Delete a file.
    
    Args:
        file_path: Path to the file relative to the base directory
    """
    target_file = os.path.normpath(os.path.join(BASE_DIR, file_path))
    
    # Security check to prevent directory traversal
    if not target_file.startswith(BASE_DIR):
        return f"Error: Cannot access files outside of the base directory."
    
    try:
        if not os.path.exists(target_file):
            return f"Error: File does not exist: {file_path}"
        
        if os.path.isdir(target_file):
            os.rmdir(target_file)
            return f"Successfully deleted directory: {file_path}"
        else:
            os.remove(target_file)
            return f"Successfully deleted file: {file_path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"

@mcp.tool()
async def run_command(
    command: str,
    stdin: Optional[str] = None,
    cwd: str = "",
    timeout: Optional[float] = None,
    timeout_ms: Optional[float] = None,
) -> str:
    """Run a shell command and return stdout and stderr as text.

    Args:
        command: The shell command to execute (e.g., 'hostname', 'ls -al', 'echo "hello"').
        stdin: Optional text to pass to the command via STDIN (e.g., for 'cat >> file.txt' or REPLs).
        cwd: Optional subdirectory (relative to base) to run the command in.
        timeout: Optional timeout in seconds. If not provided, defaults to 60s.
        timeout_ms: Optional timeout in milliseconds (alternative to `timeout`).

    Notes:
        - Commands run inside the container using the POSIX shell and are constrained to the base directory.
        - Redirection and pipes are supported because commands run through a shell.
    """

    # Resolve working directory under BASE_DIR
    working_dir = BASE_DIR
    if cwd:
        candidate = os.path.normpath(os.path.join(BASE_DIR, cwd))
        if not candidate.startswith(BASE_DIR):
            return json.dumps({
                "error": "Cannot use cwd outside of the base directory",
                "cwd": cwd,
            }, indent=2)
        working_dir = candidate

    # Determine effective timeout in seconds
    def _to_float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    timeout_secs: Optional[float]
    if timeout is not None or timeout_ms is not None:
        secs = _to_float(timeout)
        if secs is None:
            ms = _to_float(timeout_ms)
            secs = (ms / 1000.0) if ms is not None else None
        timeout_secs = secs if (secs is not None and secs > 0) else None
    else:
        timeout_secs = 60.0

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            start_new_session=True,  # ensure a new process group for robust termination
            env=os.environ.copy(),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin.encode("utf-8") if stdin is not None else None),
                timeout=timeout_secs,
            )
        except asyncio.TimeoutError:
            # Kill the entire process group to ensure children are terminated
            try:
                if hasattr(os, "killpg"):
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except Exception:
                # Fallback to killing the process itself
                try:
                    proc.kill()
                except Exception:
                    pass
            # Ensure process is cleaned up
            try:
                await proc.communicate()
            except Exception:
                pass
            return json.dumps({
                "stdout": "",
                "stderr": "Command timed out",
                "exit_code": None,
                "cwd": working_dir,
                "command": command,
                "timeout_seconds": timeout_secs,
                "timed_out": True,
                "truncated": False,
                "stdout_truncated": False,
                "stderr_truncated": False,
                "max_lines": MAX_OUTPUT_LINES,
            }, indent=2)

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        # Truncate outputs to a maximum number of lines
        def _truncate_lines(text: str, max_lines: int) -> (str, bool):
            if not text:
                return text, False
            lines = text.split("\n")
            if len(lines) <= max_lines:
                return text, False
            truncated_text = "\n".join(lines[:max_lines])
            return truncated_text, True

        stdout_truncated_text, stdout_truncated = _truncate_lines(stdout, MAX_OUTPUT_LINES)
        stderr_truncated_text, stderr_truncated = _truncate_lines(stderr, MAX_OUTPUT_LINES)
        any_truncated = stdout_truncated or stderr_truncated

        return json.dumps({
            "stdout": stdout_truncated_text,
            "stderr": stderr_truncated_text,
            "exit_code": proc.returncode,
            "cwd": working_dir,
            "command": command,
            "timeout_seconds": timeout_secs,
            "timed_out": False,
            "truncated": any_truncated,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "max_lines": MAX_OUTPUT_LINES,
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Error running command: {str(e)}",
            "cwd": working_dir,
            "command": command,
            "truncated": False,
            "stdout_truncated": False,
            "stderr_truncated": False,
            "max_lines": MAX_OUTPUT_LINES,
        }, indent=2)

if __name__ == "__main__":
    # Initialize and run the server with stdio transport
    mcp.run(transport='stdio')
