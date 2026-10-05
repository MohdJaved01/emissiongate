#!/usr/bin/env python3
"""Thin wrapper: the generator lives in the package so `emissiongate estate` works installed."""

from __future__ import annotations

import sys

from emissiongate.cli import app

if __name__ == "__main__":
    sys.argv = ["emissiongate", "estate", *sys.argv[1:]]
    app()
