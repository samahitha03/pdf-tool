#!/bin/bash
# Launch the local PDF Tool. First run sets up a virtual env automatically.
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "First run — setting up (one-time, ~30s)..."
  python3 -m venv .venv
  .venv/bin/pip install --quiet -r requirements.txt
fi

# The dependency list grows between updates; top up a venv made before it did.
.venv/bin/python -c "import flask, pypdf, PIL, cryptography" 2>/dev/null ||
  .venv/bin/pip install --quiet -r requirements.txt

exec .venv/bin/python app.py
