#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/recipe-vault}"
APP_MODULE="${APP_MODULE:-wsgi:app}"
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-9000}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_REF="${GIT_REF:-origin/main}"
CADDY_ADMIN_URL="${CADDY_ADMIN_URL:-http://127.0.0.1:2019}"
CADDY_SERVER_NAME="${CADDY_SERVER_NAME:-recipe_vault}"
VENV_DIR="$APP_DIR/venv"
PID_FILE="$APP_DIR/gunicorn.pid"
LOG_FILE="$APP_DIR/gunicorn.log"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
GUNICORN_BIN="$VENV_DIR/bin/gunicorn"
DB_FILE="$APP_DIR/instance/recipes.db"
DB_BACKUP=""

cd "$APP_DIR"

if [ -f "$DB_FILE" ]; then
    DB_BACKUP="$(mktemp "$APP_DIR/instance/recipes.db.deploy.XXXXXX")"
    cp "$DB_FILE" "$DB_BACKUP"
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git fetch "$GIT_REMOTE"
    git checkout --force --detach "$GIT_REF"
fi

if [ -n "$DB_BACKUP" ]; then
    mkdir -p "$APP_DIR/instance"
    mv "$DB_BACKUP" "$DB_FILE"
fi

if [ ! -x "$PYTHON_BIN" ]; then
    python3 -m venv "$VENV_DIR"
fi

"$PIP_BIN" install --upgrade pip
"$PIP_BIN" install -r requirements.txt

mkdir -p "$APP_DIR/instance"
"$PYTHON_BIN" init_db.py

if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE")"

    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
        kill "$old_pid"

        for _ in $(seq 1 20); do
            if ! kill -0 "$old_pid" 2>/dev/null; then
                break
            fi

            sleep 1
        done
    fi

    rm -f "$PID_FILE"
fi

pkill -u "$USER" -f "$GUNICORN_BIN.*--bind $APP_HOST:$APP_PORT.*$APP_MODULE" 2>/dev/null || true

nohup "$GUNICORN_BIN" \
    --workers 3 \
    --bind "$APP_HOST:$APP_PORT" \
    --pid "$PID_FILE" \
    "$APP_MODULE" > "$LOG_FILE" 2>&1 < /dev/null &

for _ in $(seq 1 20); do
    if curl -fsS "http://$APP_HOST:$APP_PORT/" >/dev/null; then
        break
    fi

    sleep 1
done

curl -fsS "http://$APP_HOST:$APP_PORT/" >/dev/null

curl -sS \
    -X DELETE \
    "$CADDY_ADMIN_URL/config/apps/http/servers/$CADDY_SERVER_NAME" >/dev/null || true

curl -fsS \
    -X PUT \
    -H "Content-Type: application/json" \
    --data-binary @"$APP_DIR/deploy/caddy-recipe-vault-8999.json" \
    "$CADDY_ADMIN_URL/config/apps/http/servers/$CADDY_SERVER_NAME" >/dev/null
