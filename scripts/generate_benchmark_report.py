#!/usr/bin/env python3
"""Backward-compatible wrapper for `brainstem report`."""

from __future__ import annotations

import sys

from brainstem.cli import main as cli_main


def main() -> int:
    return cli_main(["report", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
