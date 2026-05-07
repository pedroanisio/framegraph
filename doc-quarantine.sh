#!/usr/bin/env bash
set -euo pipefail

# Doc-Hygiene Quarantine Script
# Generated: 2026-05-07T13:54:42-03:00
# Review every command before executing.

QUARANTINE_DIR=".doc-quarantine"
mkdir -p "$QUARANTINE_DIR"

# --- DEPRECATED docs ---
mkdir -p "$QUARANTINE_DIR/deprecated/docs"
# mv docs/bar.md "$QUARANTINE_DIR/deprecated/docs/bar.md"
# mv docs/solution-plan.md "$QUARANTINE_DIR/deprecated/docs/solution-plan.md"

echo "Quarantine complete. Review .doc-quarantine/ before committing."
