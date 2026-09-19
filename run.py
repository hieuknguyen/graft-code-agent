#!/usr/bin/env python3
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Thêm thư mục hiện tại vào sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from cli.main import run_cli

if __name__ == "__main__":
    run_cli()
