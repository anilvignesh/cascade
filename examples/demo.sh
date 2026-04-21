#!/bin/bash
# Cascade demo — runs three example tasks

cd "$(dirname "$0")/.."

echo "=== Demo 1: Simple script (expect local only) ==="
python run.py "write a Python function that converts celsius to fahrenheit with tests" --no-review

echo ""
echo "=== Demo 2: File task (programmer + reviewer) ==="
python run.py "write a Python script that counts word frequency in a text file and outputs top 10" --no-test

echo ""
echo "=== Demo 3: Full pipeline ==="
python run.py "write a Python class for a simple key-value store backed by a JSON file with get, set, delete methods"
