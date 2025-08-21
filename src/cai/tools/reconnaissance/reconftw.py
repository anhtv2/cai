# reconftw.py
"""
ReconFTW generic command tool for reconnaissance workflows.

This version ENFORCES reading `<script> -h` BEFORE running any command.
If help fails, the command will NOT run.

Recommended usage patterns:

1) DEFAULT COMMAND (thường dùng nhất):
   - Mục tiêu: full recon theo mặc định của script.
     reconftw_cmd("-d {{Domain}} -r")

   (Kết quả mặc định thường nằm trong ~/reconftw/Recon/{{Domain}})

2) Live help:
     reconftw_help()

Script path resolution order:
  1) explicit `script_path` arg if provided
  2) $RECONFTW_PATH env
  3) /home/user/reconftw/reconftw.sh
  4) reconftw.sh (cwd)
"""
from __future__ import annotations

import os
import shlex
import time
from typing import Optional, List

from cai.sdk.agents import function_tool
from cai.tools.common import run_command_async  # pylint: disable=import-error

# Cache TTL for help output (seconds)
_HELP_TTL = 6 * 60 * 60  # 6 hours
_recon_help_cache: dict[str, float | str] = {"ts": 0.0, "text": "", "key": ""}


def _resolve_script_path(override: Optional[str] = None) -> str:
    candidates: List[str] = []
    if override:
        candidates.append(override)
    env_path = os.getenv("RECONFTW_PATH")
    if env_path:
        candidates.append(env_path)
    candidates += [
        "/home/user/reconftw/reconftw.sh",
        "reconftw.sh",
    ]
    for p in candidates:
        if p and os.path.exists(p) and os.access(p, os.X_OK):
            return p
    # Fall back to the best hint for error messages
    return override or env_path or "reconftw.sh"


async def _get_reconftw_help_text(script: str, force_refresh: bool = False) -> str:
    """
    Get (and cache) `<script> -h` text. Cache key depends on script path so we don't mix outputs.
    Raise on failure so callers can decide behavior.
    """
    key = f"help::{os.path.abspath(script)}"
    now = time.time()
    if not force_refresh and _recon_help_cache.get("key") == key and now - float(_recon_help_cache.get("ts", 0.0)) < _HELP_TTL:
        cached = str(_recon_help_cache.get("text", ""))
        if cached:
            return cached

    # Validate executability early for a clearer error
    if not os.path.exists(script):
        raise FileNotFoundError(f"ReconFTW script not found at: {script}")
    if not os.access(script, os.X_OK):
        raise PermissionError(f"ReconFTW script is not executable: {script}")

    # Fetch fresh help
    cmd = f"{shlex.quote(script)} -h"
    help_text = await run_command_async(cmd, timeout=180, stream=False, tool_name="reconftw")
    _recon_help_cache["ts"] = now
    _recon_help_cache["text"] = help_text
    _recon_help_cache["key"] = key
    return help_text


@function_tool
async def reconftw_help(script_path: Optional[str] = None) -> str:
    """
    Print live help for your installed reconftw.sh (runs `<script> -h`).
    Always runs the real command (does not fail open).
    """
    script = _resolve_script_path(script_path)
    return await _get_reconftw_help_text(script, force_refresh=True)


@function_tool
async def reconftw_cmd(args: str, script_path: Optional[str] = None) -> str:
    """
    Run reconftw.sh with raw CLI args, but ONLY AFTER printing `<script> -h` so the agent reads usage.

    DEFAULT COMMAND (khuyến nghị):
      reconftw_cmd("-d example.com -r")

    Behavior:
      - Prepend the latest `<script> -h` output (preamble) so the model always “reads” guidance first.
      - If help fails, DO NOT run the main command; return the help error so the issue is fixed first.
    """
    script = _resolve_script_path(script_path)

    # 1) Obtain help (and show it). If this fails, abort to avoid running with wrong assumptions.
    try:
        help_text = await _get_reconftw_help_text(script, force_refresh=False)
    except Exception as e:  # noqa: BLE001
        return (
            f"### ReconFTW help for {script} (failed) ###\n"
            f"{str(e)}\n"
            "Refusing to run reconftw because help could not be retrieved. "
            "Please ensure the script path is correct and executable.\n"
        )

    preamble = (
        f"### {os.path.basename(script)} -h (for context) ###\n"
        f"{help_text}\n"
        "### END HELP ###\n\n"
        ">>> Proceeding to run your ReconFTW command...\n"
    )

    tail = args.strip() if args else ""
    cmd = f"{shlex.quote(script)} {tail}".strip()

    # 2) Run the command (streaming). We return preamble + streamed output.
    try:
        run_output = await run_command_async(cmd, timeout=8 * 60 * 60, stream=True, tool_name="reconftw")
    except Exception as e:  # noqa: BLE001
        return f"{preamble}\n[RECONFTW RUN ERROR] {str(e)}"

    # 3) Combine and return
    return f"{preamble}\n{run_output}"
