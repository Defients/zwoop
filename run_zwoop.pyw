"""Zwoop launcher — works from any cwd and without PYTHONPATH.

Used by the tray's "Launch on login" command: the registry Run key has
no working-directory concept, so it must invoke a self-locating script.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zwoop.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
