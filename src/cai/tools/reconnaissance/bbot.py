# bbot.py
"""
BBOT generic command tool for reconnaissance scans.

This version ENFORCES reading `bbot --help` BEFORE running any command.
If help fails, the command will NOT run.

Recommended usage patterns:

1) DEFAULT COMMAND (thường dùng nhất):
   - Mục tiêu: enum subdomain + web probing nhanh, xuất JSON, ít noise.
     bbot_cmd("-t {{Domain}} -p subdomain-enum,web-thorough -m crt,shodan_dns -o ~/bbot -y -n {{Domain}} --json --brief")

2) Subdomain recon (tối giản):
     bbot_cmd("-t {{Domain}} -p subdomain-enum -o ~/bbot -y -n {{Domain}}")

3) Live help:
     bbot_help()

Other common flags:
  -p web-thorough, -m crt,shodan_dns, -f someflag, --json, --brief, -v
"""
from __future__ import annotations

import time
from cai.sdk.agents import function_tool
from cai.tools.common import run_command_async  # pylint: disable=import-error

# Cache TTL for help output (seconds). We still SHOW help every run (preamble),
# but caching reduces the extra subprocess cost when runs happen back-to-back.
_HELP_TTL = 6 * 60 * 60  # 6 hours
_bbot_help_cache: dict[str, float | str] = {"ts": 0.0, "text": ""}


async def _get_bbot_help_text(force_refresh: bool = False) -> str:
    """Get (and cache) `bbot --help` text. Raise on failure so callers can decide behavior."""
    now = time.time()
    if not force_refresh and now - float(_bbot_help_cache.get("ts", 0.0)) < _HELP_TTL:
        cached = str(_bbot_help_cache.get("text", ""))
        if cached:
            return cached

    # Fetch fresh help
    help_text = await run_command_async("bbot --help", timeout=180, stream=False, tool_name="bbot")
    _bbot_help_cache["ts"] = now
    _bbot_help_cache["text"] = help_text
    return help_text


@function_tool
async def bbot_help() -> str:
    """
    Print live `bbot --help` output for the installed BBOT version.
    Always runs the real command (does not fail open).
    """
    return await _get_bbot_help_text(force_refresh=True)


@function_tool
async def bbot_cmd(args: str) -> str:
    """
    Run BBOT with raw CLI arguments, but ONLY AFTER printing `bbot --help` so the agent reads usage.

    DEFAULT COMMAND (khuyến nghị):
      bbot_cmd("-t example.com -p subdomain-enum,web-thorough -m crt,shodan_dns -o ~/bbot -y -n example.com --json --brief")

    Behavior:
      - Prepend the latest `bbot --help` output (preamble) so the model always “reads” guidance first.
      - If `bbot --help` fails, DO NOT run the main command; return the help error so the issue is fixed first.
    """
    # 1) Obtain help (and show it). If this fails, abort to avoid running with wrong assumptions.
    try:
        help_text = await _get_bbot_help_text(force_refresh=False)
    except Exception as e:  # noqa: BLE001
        return (
            "### BBOT --help (failed) ###\n"
            f"{str(e)}\n"
            "Refusing to run `bbot` because help could not be retrieved. "
            "Please ensure BBOT is installed and available in PATH.\n"
        )

    preamble = (
        "### BBOT --help (for context) ###\n"
        f"{help_text}\n"
        "### END HELP ###\n\n"
        ">>> Proceeding to run your BBOT command...\n"
    )

    cmd = f"bbot {args.strip()}" if args and args.strip() else "bbot"
    # 2) Run the command (streaming). We return preamble + streamed output.
    try:
        run_output = await run_command_async(cmd, timeout=8 * 60 * 60, stream=True, tool_name="bbot")
    except Exception as e:  # noqa: BLE001
        return f"{preamble}\n[BBOT RUN ERROR] {str(e)}"

    # 3) Combine and return
    return f"{preamble}\n{run_output}"
