#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/recipe-vault}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
GIT_REF="${GIT_REF:-$GIT_REMOTE/$GIT_BRANCH}"

cd "$APP_DIR"

echo "Updating Recipe Vault from $GIT_REF..."
git fetch "$GIT_REMOTE" "$GIT_BRANCH"

GIT_REMOTE="$GIT_REMOTE" GIT_REF="$GIT_REF" bash deploy/start_recipe_vault.sh

echo "Recipe Vault is now running from $GIT_REF."
