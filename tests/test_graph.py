"""End-to-end test runner for Capstone 2 — delegates to run_all_tests.py.

Runs all 38 cases covering: base functionality, multi-turn memory,
sanitization, write guard, guardrail, intent classification, and RBAC.

Run with: python tests/test_graph.py
Regression gate: 37/38 baseline — AMT3 is a known pre-existing guardrail
relevance-check flake, tracked separately (see run_all_tests.py). Anything
below 37 is a real regression.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.run_all_tests import main

if __name__ == "__main__":
    main()
