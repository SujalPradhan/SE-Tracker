#!/usr/bin/env bash
# Nightly consistent SQLite snapshot → gs://$BACKUP_BUCKET/se-tracker/
set -euo pipefail
set -a; . /etc/se-tracker.env; set +a
[ -n "${BACKUP_BUCKET:-}" ] || { echo "BACKUP_BUCKET not set — skipping"; exit 0; }
DB="${DATABASE_URL#sqlite:///}"
STAMP=$(date -u +%Y%m%d-%H%M%S)
TMP=$(mktemp -d)
sqlite3 "$DB" ".backup '$TMP/se_tracker.db'"
gzip "$TMP/se_tracker.db"
gcloud storage cp "$TMP/se_tracker.db.gz" "gs://$BACKUP_BUCKET/se-tracker/se_tracker-$STAMP.db.gz" --quiet
rm -rf "$TMP"
echo "$(date -u) backup ok: se_tracker-$STAMP.db.gz"
