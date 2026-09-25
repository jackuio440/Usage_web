#!/bin/sh
# Daily SQLite backup (installed to /etc/cron.daily/usage-web-backup). Keeps 30 days.
set -eu
DB=/var/lib/usage-web/usage.db
OUT_DIR=/var/backups/usage-web
KEEP_DAYS=30

[ -f "$DB" ] || exit 0
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/usage-$(date +%Y%m%d).db"
/opt/usage-web/venv/bin/python - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)  # consistent copy even while the site is running
dst.close(); src.close()
PY
chmod 600 "$OUT"
find "$OUT_DIR" -name 'usage-*.db' -mtime +"$KEEP_DAYS" -delete
