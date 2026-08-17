"""End-to-end test runner for Capstone 2 — delegates to run_all_tests.py.

Runs all 40 cases covering: base functionality, multi-turn memory,
sanitization, write guard, guardrail/jailbreak resistance, intent
classification, and RBAC.

Run with: python tests/test_graph.py
Regression gate: 40/40 — AMT3's guardrail history-passthrough bypass is now
fixed (agents/guardrail.py), not a flake to route around. GRD4/GRD5 are the
new jailbreak-resistance regression cases for that fix.

Output guardrail (prompt/schema leak detection) is a separate, zero-API-cost
test — see tests/test_output_guardrail.py.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.run_all_tests import main

if __name__ == "__main__":
    main()
