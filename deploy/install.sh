#!/bin/bash
# Install or update the site on the GPU server. Run from the repo root: sudo deploy/install.sh
set -euo pipefail

APP_DIR=/opt/usage-web
CONF_DIR=/etc/usage-web
DATA_DIR=/var/lib/usage-web
SVC_USER=usageweb

if [ "$(id -u)" -ne 0 ]; then echo "請用 sudo 執行：sudo deploy/install.sh"; exit 1; fi
cd "$(dirname "$0")/.."

echo "==> 建立系統帳號 $SVC_USER"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SVC_USER"

RUN_AS_ROOT=0
if getent group shadow >/dev/null; then
  usermod -aG shadow "$SVC_USER"
else
  # RHEL/Rocky: /etc/shadow is mode 000, only root can check passwords.
  echo "!! 沒有 shadow 群組（RHEL 系統），服務將以 root 身分執行才能驗證密碼"
  RUN_AS_ROOT=1
fi

echo "==> PAM 設定 /etc/pam.d/usage-web"
if [ ! -f /etc/pam.d/usage-web ]; then
  if [ -f /etc/pam.d/common-auth ]; then
    printf '@include common-auth\n@include common-account\n' > /etc/pam.d/usage-web
  elif [ -f /etc/pam.d/password-auth ]; then
    printf 'auth include password-auth\naccount include password-auth\n' > /etc/pam.d/usage-web
  else
    printf 'auth include login\naccount include login\n' > /etc/pam.d/usage-web
  fi
fi

echo "==> 複製程式到 $APP_DIR"
mkdir -p "$APP_DIR" "$CONF_DIR" "$DATA_DIR"
rm -rf "$APP_DIR/app"
cp -r app requirements.txt "$APP_DIR/"
find "$APP_DIR/app" -name __pycache__ -prune -exec rm -rf {} +

echo "==> 建立 Python 虛擬環境並安裝套件"
[ -x "$APP_DIR/venv/bin/python" ] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

if [ ! -f "$CONF_DIR/config.toml" ]; then
  echo "==> 建立設定檔 $CONF_DIR/config.toml"
  cp config.example.toml "$CONF_DIR/config.toml"
fi
chown -R "$SVC_USER:$SVC_USER" "$DATA_DIR"
chmod 700 "$DATA_DIR"

echo "==> 安裝 systemd 服務與每日備份"
cp deploy/usage-web.service /etc/systemd/system/usage-web.service
if [ "$RUN_AS_ROOT" = 1 ]; then
  sed -i -e '/^User=/d' -e '/^Group=/d' -e '/^SupplementaryGroups=/d' /etc/systemd/system/usage-web.service
fi
install -m 755 deploy/backup.sh /etc/cron.daily/usage-web-backup
systemctl daemon-reload
systemctl enable usage-web >/dev/null
systemctl restart usage-web

sleep 2
PORT=$(grep -E '^\s*port\s*=' "$CONF_DIR/config.toml" | head -1 | tr -dc '0-9')
if curl -fs "http://127.0.0.1:${PORT:-8080}/healthz" >/dev/null; then
  echo "==> 完成！網站在 port ${PORT:-8080} 執行中"
else
  echo "!! 服務沒有正常回應，請看：journalctl -u usage-web -n 50"
fi
