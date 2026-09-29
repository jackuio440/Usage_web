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
systemctl stop usage-web 2>/dev/null || true

conf_value() {  # first `key = value` in the config file, quotes stripped
  grep -E "^\s*$1\s*=" "$CONF_DIR/config.toml" | head -1 | sed -E 's/^[^=]*=\s*//; s/\s*#.*$//; s/"//g'
}
HOST=$(conf_value host); HOST=${HOST:-127.0.0.1}
PORT=$(conf_value port | tr -dc '0-9'); PORT=${PORT:-8080}

echo "==> 檢查 port $PORT 是否被其他服務佔用"
if command -v ss >/dev/null && [ -n "$(ss -ltnH "sport = :$PORT")" ]; then
  echo "!! port $PORT 已經被下面的程式佔用，網站沒有啟動："
  ss -ltnpH "sport = :$PORT" | sed -E 's/.*users:\(\("([^"]+)".*/   \1/' | sort -u
  echo "   請在 $CONF_DIR/config.toml 換一個沒被佔用、防火牆有開放的 port，"
  echo "   或停掉佔用的服務，再重新執行 sudo deploy/install.sh"
  exit 1
fi

systemctl start usage-web
sleep 2
if ! curl -fs "http://127.0.0.1:$PORT/healthz" >/dev/null; then
  echo "!! 服務沒有正常回應，請看：journalctl -u usage-web -n 50"
  exit 1
fi

echo "==> 完成！網站在 port $PORT 執行中"
if [ "$HOST" = "127.0.0.1" ] || [ "$HOST" = "localhost" ]; then
  echo "    目前只接受本機連線，大家用 SSH 通道連：ssh -p <SSH port> -N -L 8080:127.0.0.1:$PORT 帳號@伺服器IP"
  echo "    然後打開 http://localhost:8080"
else
  IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [ "$PORT" = 80 ]; then echo "    網址：http://${IP:-伺服器IP}"; else echo "    網址：http://${IP:-伺服器IP}:$PORT"; fi
fi
