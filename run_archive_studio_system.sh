#!/bin/bash

# Archive Studio Launch Script using system Python (Anaconda)
# This script uses the system Python that already has most dependencies

cd "$(dirname "$0")"

echo "Starting Archive Studio with system Python..."

# Install missing dependencies if needed
echo "Checking for missing dependencies..."
python3 -c "import google.genai" 2>/dev/null || { echo "Installing google-genai..."; pip3 install google-genai; }

echo "Launching Archive Studio..."
python3 ArchiveStudio.py

echo "Archive Studio has been closed."