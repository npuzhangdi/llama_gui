# -*- coding: utf-8 -*-
"""Check whether the existing .venv was built by the interpreter the user picked.

Exit code 0 -> compatible, first_run.bat may reuse the venv.
Exit code 1 -> mismatch or broken, first_run.bat should rebuild with --clear.

Standard library only; runs with the venv interpreter before pip is available.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / ".venv" / "pyvenv.cfg"
PROBE = "import sys;print(sys.base_prefix);print('%d.%d'%sys.version_info[:2])"


def configured_home() -> str:
    try:
        for line in CFG.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() == "home":
                return value.strip().strip('"')
    except OSError:
        pass
    return ""


def selected_info(executable: str) -> tuple[str, str]:
    result = subprocess.run(
        [executable, "-c", PROBE],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("interpreter probe failed")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError("unexpected probe output")
    return lines[0], lines[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", required=True)
    args = parser.parse_args()

    if not CFG.is_file():
        return 1
    try:
        base, version = selected_info(args.selected)
    except Exception:
        return 1

    current = "%d.%d" % sys.version_info[:2]
    if current != version:
        return 1
    home = configured_home()
    if home and Path(home).is_dir():
        try:
            if Path(home).resolve() != Path(base).resolve():
                return 1
        except OSError:
            return 1
    elif home:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
