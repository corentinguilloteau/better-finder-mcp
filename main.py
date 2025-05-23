#!/usr/bin/env python3
"""Enhanced Finder - A better macOS finder with intelligent search."""

import sys
import asyncio
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from enhanced_finder.cli import main

if __name__ == "__main__":
    main()