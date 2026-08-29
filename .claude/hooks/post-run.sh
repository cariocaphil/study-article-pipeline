#!/bin/bash
# Post-run hook: opens the most recently generated .docx in the output/ folder

LATEST=$(ls -t output/*.docx 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
  echo "[hook] No .docx found in output/"
  exit 0
fi

echo "[hook] Opening $LATEST"
open "$LATEST"  # macOS — use 'xdg-open' on Linux, 'start' on Windows