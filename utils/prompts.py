"""Interactive Q&A prompts — mirrors HFAlgoBot's utils/prompts.py style:
each helper loops until it gets valid input and shows defaults in [brackets]."""

from __future__ import annotations

import os
from datetime import date, datetime

from config import Config


def pick_first_login() -> bool:
    return input("First login? (y/n): ").strip().lower() == "y"


def pick_date(label: str) -> date:
    while True:
        raw = input(f"{label} (YYYY-MM-DD): ").strip()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Invalid format. Use YYYY-MM-DD (e.g. 2026-02-09)")


def pick_output() -> tuple[str, bool]:
    """Return (path, append). 'append' adds to/resumes an existing file;
    otherwise we write a fresh file at the path."""
    raw = input("Output: (n)ew file or (a)ppend to existing? [n]: ").strip().lower()
    append = raw == "a"
    default = Config.OUTPUT_XLSX
    while True:
        path = input(f"Output file path [{default}]: ").strip() or default
        if append and not os.path.exists(path):
            print(f"  '{path}' does not exist — choose an existing file to append to.")
            continue
        if not append and os.path.exists(path):
            ow = input(f"  '{path}' exists. Overwrite as a new file? (y/n): ").strip().lower()
            if ow != "y":
                continue
        return path, append
