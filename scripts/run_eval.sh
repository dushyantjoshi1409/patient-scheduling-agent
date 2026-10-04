#!/usr/bin/env bash
set -e

echo "Running Evaluation Harness & Improvement Loop"
echo "==============================================="

if [ ! -f .env ]; then
    echo "Error: .env file not found."
    exit 1
fi

pip install -q -r requirements.txt 2>/dev/null

python -m app.eval.cli "$@"
