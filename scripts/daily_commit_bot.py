#!/usr/bin/env python3
"""Daily commit bot for ai-stock-system.

Keeps the repository alive by:
1. Running the daily_judge engine in mock mode (cheap, deterministic)
2. Committing any new report as a daily shadow run
3. Committing a fix-style message if the engine fails

Usage:
    python3 scripts/daily_commit_bot.py            # run and commit if changed
    python3 scripts/daily_commit_bot.py --dry-run  # print what would happen
    python3 scripts/daily_commit_bot.py --install-cron  # add crontab entry

Design:
  - Uses --mock-jev and --mock-search to avoid burning real API quota daily.
  - Only stages reports/ (and this script's own changes if it changes).
  - Never stages user-modified files under src/ or p*-audit/.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "src", "engine", "daily_judge.py")
REPORTS_DIR = os.path.join(ROOT, "reports", "shadow")


def run(cmd: list[str], cwd: str = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess with UTF-8 text capture."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], check=check)


def has_git_repo() -> bool:
    return os.path.isdir(os.path.join(ROOT, ".git"))


def run_engine(today: str, dry_run: bool) -> tuple[bool, str]:
    """Run the engine in mock mode; returns (success, log)."""
    cmd = [
        sys.executable,
        ENGINE,
        "--date", today,
        "--mock-jev",
        "--mock-search",
        "--json",
    ]
    proc = run(cmd, check=False)
    log = proc.stdout + proc.stderr
    success = proc.returncode == 0
    return success, log


def has_report_changes() -> bool:
    """Whether reports/ has uncommitted changes."""
    if not has_git_repo():
        return False
    out = run(["git", "status", "--porcelain", "--", "reports/"], check=False)
    return bool(out.stdout.strip())


def stage_and_commit(message: str, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] would commit: {message}")
        return
    git("add", "--", "reports/")
    git("commit", "-m", message, check=False)


def install_cron() -> int:
    """Add a daily crontab entry for this bot, idempotently."""
    cron_line = (
        "0 13 * * * cd /Users/xiashuang/AI-股票系统 && "
        "/usr/bin/python3 /Users/xiashuang/AI-股票系统/scripts/daily_commit_bot.py "
        ">> /Users/xiashuang/AI-股票系统/scratch/daily_commit_bot.log 2>&1"
    )
    marker = "# ── AI股票系统 daily commit bot ──"
    proc = run(["crontab", "-l"], check=False)
    current = proc.stdout if proc.returncode == 0 else ""

    if marker in current and cron_line in current:
        print("Crontab entry already exists.")
        return 0

    lines = current.rstrip("\n").splitlines()
    if marker not in current:
        lines.append(marker)
    lines.append(cron_line)
    new_cron = "\n".join(lines) + "\n"
    proc = subprocess.run(["crontab"], input=new_cron, text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"Failed to install crontab: {proc.stderr}", file=sys.stderr)
        return 1
    print("Installed crontab entry for daily commit bot.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print actions without running git")
    parser.add_argument("--install-cron", action="store_true", help="install daily crontab entry")
    args = parser.parse_args()

    if args.install_cron:
        return install_cron()

    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")

    if not has_git_repo():
        print("Not a git repository; skipping daily commit bot.", file=sys.stderr)
        return 1

    print(f"=== daily_commit_bot {today} ===")
    success, log = run_engine(today, args.dry_run)

    if success:
        print("Engine OK")
        if not has_report_changes():
            print("No report changes; skipping commit.")
            return 0
        stage_and_commit(f"chore: daily shadow run {today}", args.dry_run)
    else:
        print("Engine FAILED")
        print(log[-2000:])
        stage_and_commit(f"fix: daily engine health check failed on {today}", args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
