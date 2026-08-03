"""End-to-end test runner for Capstone 2 — delegates to run_all_tests.py.

Runs all 38 cases covering: base functionality, multi-turn memory,
sanitization, write guard, guardrail, intent classification, and RBAC.

Run with: python tests/test_graph.py
Last result: 38/38 passed
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.run_all_tests import main

if __name__ == "__main__":
    main()
