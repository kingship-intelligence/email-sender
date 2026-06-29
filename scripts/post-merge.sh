#!/bin/bash
set -e

pip install -q -r requirements.txt 2>/dev/null || true

python - <<'EOF'
import os, sys
os.environ.setdefault("SECRET_KEY", "post-merge-check")
os.environ.setdefault("DATABASE_URL", "sqlite:///mailblast.db")
sys.path.insert(0, ".")
from app import app, db
with app.app_context():
    db.create_all()
print("DB tables verified.")
EOF
