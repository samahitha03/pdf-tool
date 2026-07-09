#!/bin/bash
# Launch the local PDF Tool. First run sets up a virtual env automatically.
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run — setting up (one-time, ~30s)..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r requirements.txt
fi

exec .venv/bin/python app.py
