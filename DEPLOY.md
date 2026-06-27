# Deploy Recipe Vault on an Ubuntu LTS VPS

These steps assume an Ubuntu LTS VPS, Caddy, Gunicorn, and this app running from `~/recipe-vault`.

## 1. Install server packages

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git curl caddy
```

## 2. Put the app on the server

Clone or copy this project to the server:

```bash
cd ~
git clone https://github.com/acom64/recipe-vault.git recipe-vault
cd recipe-vault
```

If you are copying files manually instead of using Git, make sure the project contains `app/`, `wsgi.py`, `requirements.txt`, `init_db.py`, and `run.py`.

## 3. Start or update the app

The deploy script creates the virtual environment, installs dependencies, initializes or updates the database, restarts Gunicorn on `127.0.0.1:9000`, and configures Caddy to serve the app on port `8999`.

```bash
cd ~/recipe-vault
bash deploy/start_recipe_vault.sh
```

Open the app at:

```text
http://YOUR_SERVER_IP:8999
```

The SQLite database is stored at `instance/recipes.db`.

## Updating the app

From the server, update to the latest GitHub `main` and restart the app with:

```bash
cd ~/recipe-vault
bash deploy/update_from_github_main.sh
```

From this Windows machine, run the same server update over SSH:

```powershell
.\deploy\update-server-from-main.ps1 -Server user@YOUR_SERVER_IP
```

## Optional environment overrides

Set these before running the script when you need different paths or ports:

```bash
export APP_DIR="$HOME/recipe-vault"
export APP_HOST="127.0.0.1"
export APP_PORT="9000"
export GIT_REF="origin/main"
export CADDY_ADMIN_URL="http://127.0.0.1:2019"
bash deploy/start_recipe_vault.sh
```

## Firewall

If you use UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 8999/tcp
sudo ufw enable
```

## Useful checks

```bash
tail -n 100 ~/recipe-vault/gunicorn.log
curl -fsS http://127.0.0.1:9000/
curl -fsS http://127.0.0.1:8999/
sudo systemctl status caddy
```

## Optional HTTPS

If you want HTTPS on a domain instead of port `8999`, point the domain to the VPS and use a normal Caddy site config such as:

```caddyfile
YOUR_DOMAIN {
    reverse_proxy 127.0.0.1:9000
}
```
