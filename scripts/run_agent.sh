#!/usr/bin/env bash
set -e

echo "Starting City Health Clinic Scheduling Agent..."
echo "================================================"

if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

if [ ! -f .env ]; then
    echo "Error: .env file not found. Copy .env.example to .env and add your API keys."
    exit 1
fi

pip install -q -r requirements.txt 2>/dev/null

echo "Starting server on http://localhost:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
