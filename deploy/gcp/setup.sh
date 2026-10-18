#!/usr/bin/env bash
# One-time VM setup for SE-Tracker on a fresh Debian 12 GCE instance.
# Run as root:  sudo bash setup.sh https://github.com/SujalPradhan/SE-Tracker.git
set -euo pipefail

REPO_URL="${1:?usage: setup.sh <git repo url>}"
APP_DIR=/srv/se-tracker
APP_USER=setracker

echo "==> 1 GB swapfile (e2-micro has 1 GB RAM)"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "==> Packages"
apt-get update
apt-get install -y python3-venv python3-pip git sqlite3 debian-keyring debian-archive-keyring apt-transport-https curl gnupg
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi

echo "==> App user and code"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
mkdir -p /var/lib/se-tracker
chown -R "$APP_USER:$APP_USER" "$APP_DIR" /var/lib/se-tracker
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Environment file"
if [ ! -f /etc/se-tracker.env ]; then
  cp "$APP_DIR/deploy/gcp/se-tracker.env.example" /etc/se-tracker.env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')|" /etc/se-tracker.env
  chmod 600 /etc/se-tracker.env
  echo "!! Edit /etc/se-tracker.env (SITE_ADDRESS, GOOGLE_CLIENT_ID/SECRET, BACKUP_BUCKET) before starting."
fi

echo "==> systemd + Caddy + backups"
cp "$APP_DIR/deploy/gcp/se-tracker.service" /etc/systemd/system/se-tracker.service
cp "$APP_DIR/deploy/gcp/Caddyfile" /etc/caddy/Caddyfile
mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironmentFile=/etc/se-tracker.env\n' > /etc/systemd/system/caddy.service.d/env.conf
install -m 755 "$APP_DIR/deploy/gcp/backup.sh" /usr/local/bin/se-tracker-backup
echo '30 21 * * * root /usr/local/bin/se-tracker-backup >> /var/log/se-tracker-backup.log 2>&1' > /etc/cron.d/se-tracker-backup
systemctl daemon-reload
systemctl enable se-tracker caddy

echo "==> Done. After editing /etc/se-tracker.env:"
echo "    sudo systemctl restart se-tracker caddy"
