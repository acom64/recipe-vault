# Deploy Recipe Vault on a VPS

These steps assume an Ubuntu/Debian VPS, Nginx, Gunicorn, systemd, and this app running from `/var/www/recipe-vault`.

## 1. Install server packages

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip nginx git
```

## 2. Put the app on the server

Clone or copy this project to the server:

```bash
sudo mkdir -p /var/www
sudo chown "$USER":"$USER" /var/www
cd /var/www
git clone YOUR_REPO_URL recipe-vault
cd recipe-vault
```

If you are copying files manually instead of using Git, make sure the project contains `app/`, `wsgi.py`, `requirements.txt`, `init_db.py`, and `run.py`.

## 3. Create the virtual environment

```bash
cd /var/www/recipe-vault
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Initialize the database

```bash
cd /var/www/recipe-vault
source venv/bin/activate
python init_db.py
```

The SQLite database will be created in `instance/recipes.db`.

## 5. Test Gunicorn

```bash
cd /var/www/recipe-vault
source venv/bin/activate
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

Visit `http://YOUR_SERVER_IP:8000` only if your firewall allows it. Press `Ctrl+C` after the test.

## 6. Create a systemd service

Create `/etc/systemd/system/recipe-vault.service`:

```ini
[Unit]
Description=Recipe Vault Flask app
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/recipe-vault
Environment="PATH=/var/www/recipe-vault/venv/bin"
ExecStart=/var/www/recipe-vault/venv/bin/gunicorn --workers 3 --bind unix:/var/www/recipe-vault/recipe-vault.sock wsgi:app

[Install]
WantedBy=multi-user.target
```

Give `www-data` access to the app and SQLite database:

```bash
sudo chown -R www-data:www-data /var/www/recipe-vault
```

Start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable recipe-vault
sudo systemctl start recipe-vault
sudo systemctl status recipe-vault
```

## 7. Configure Nginx

Create `/etc/nginx/sites-available/recipe-vault`:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_SERVER_IP;

    location /static {
        alias /var/www/recipe-vault/app/static;
    }

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/recipe-vault/recipe-vault.sock;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/recipe-vault /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 8. Open the firewall

If you use UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 9. Optional HTTPS

After your domain points to the VPS:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN
```

## Updating the app

```bash
cd /var/www/recipe-vault
sudo -u www-data git pull
sudo -u www-data /var/www/recipe-vault/venv/bin/pip install -r requirements.txt
sudo systemctl restart recipe-vault
```

## Useful checks

```bash
sudo journalctl -u recipe-vault -n 100 --no-pager
sudo systemctl status recipe-vault
sudo nginx -t
```
