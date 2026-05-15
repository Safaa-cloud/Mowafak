#!/usr/bin/env bash

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DB_FILE="$PROJECT_ROOT/mowafak.db"
AUDIT_LOG="$PROJECT_ROOT/responsible_ai/audit_log.jsonl"
UPLOAD_DIR="$PROJECT_ROOT/data/uploads"

echo "============================================"
echo "  Mowafak AI Pre-Screen — Reset Script"
echo "============================================"
echo ""
echo "This will permanently delete:"
echo "  - Database:  $DB_FILE"
echo "  - Audit log: $AUDIT_LOG"
echo "  - Uploads:   $UPLOAD_DIR/*"
echo ""

read -p "Are you sure? Type 'yes' to confirm: " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Reset cancelled."
    exit 0
fi

echo ""
echo "Resetting..."

rm -f "$DB_FILE" && echo "  [✓] Database deleted."
rm -f "$AUDIT_LOG" && echo "  [✓] Audit log deleted."

find "$UPLOAD_DIR" -type f -delete 2>/dev/null || true
echo "  [✓] Uploaded files cleared."

mkdir -p "$UPLOAD_DIR"
mkdir -p "$PROJECT_ROOT/responsible_ai"
mkdir -p "$PROJECT_ROOT/outputs"
echo "  [✓] Required directories recreated."

echo ""
echo "============================================"
echo "  Reset complete. Ready for a clean demo."
echo "============================================"