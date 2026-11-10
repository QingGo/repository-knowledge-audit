#!/usr/bin/env python3
"""Compatibility entry point for the task-70 runner.

The implementation lives in coding_cf.py; this wrapper keeps the originally requested
`run_cf.py` path working for the team.

Usage: python3 run_cf.py --dry-run | --run | --regrade | --summary
"""
from coding_cf import main

if __name__ == "__main__":
    raise SystemExit(main())
