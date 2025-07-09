#!/bin/bash

# Archive Studio Launch Script for macOS
# This script activates the virtual environment and runs Archive Studio

cd "$(dirname "$0")"

echo "Starting Archive Studio..."
echo "Activating virtual environment..."

source venv/bin/activate

echo "Launching Archive Studio..."
python ArchiveStudio.py

echo "Archive Studio has been closed."