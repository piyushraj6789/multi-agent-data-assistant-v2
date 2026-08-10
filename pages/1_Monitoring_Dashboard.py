"""Streamlit multipage entry — makes dashboard/monitoring.py show up in
app.py's sidebar nav instead of running as a separate `streamlit run`
process on its own port. All rendering logic still lives in
dashboard/monitoring.py; this file just invokes it."""

from dashboard.monitoring import main

main()
