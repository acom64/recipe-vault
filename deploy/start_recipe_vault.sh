#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/recipe-vault"
GUNICORN_CMD="$APP_DIR/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:9000 wsgi:app"

cd "$APP_DIR"

if ! pgrep -u "$USER" -f "gunicorn --workers 3 --bind 127.0.0.1:9000 wsgi:app" >/dev/null; then
    nohup $GUNICORN_CMD > "$APP_DIR/gunicorn.log" 2>&1 < /dev/null &
fi

for _ in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:9000/ >/dev/null; then
        break
    fi

    sleep 1
done

curl -sS \
    -X DELETE \
    http://127.0.0.1:2019/config/apps/http/servers/recipe_vault >/dev/null || true

curl -fsS \
    -X PUT \
    -H "Content-Type: application/json" \
    --data-binary @"$APP_DIR/deploy/caddy-recipe-vault-8999.json" \
    http://127.0.0.1:2019/config/apps/http/servers/recipe_vault >/dev/null
