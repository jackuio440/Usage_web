# GPU Server Booking

[中文](README.md) | **English**

A small website for a lab's shared GPU server: see live usage, book GPU time, and log in with your Linux account on the server.

| Page | What it does |
|---|---|
| **Live status** | Per-GPU utilization, memory, temperature, power, running processes and their owners; current and next booking; CPU, RAM, disk; announcements and maintenance windows. Refreshes every 10 s |
| **Schedule** | Two views: a GPU timeline (one row per GPU, 7 days) and a week calendar. Click an empty slot or drag to book, pick one or more GPUs, add a purpose. Change, cancel or end your own bookings early |
| **My bookings** | Your bookings and how much of this week's quota you have used |
| **Usage stats** | Per person and week: GPU-hours booked vs. GPU-hours actually used, and use without a booking |
| **Admin** (sudo group) | Booking rules (max hours per booking, weekly quota, how far ahead, max GPUs per booking), announcements, maintenance windows, activity log, cancel anyone's booking |

Built-in checks: a GPU can't be double-booked, nobody can book during maintenance, and quotas are enforced. The live status page marks processes running **without a booking in yellow** and processes **on someone else's booking in red**.

**Chinese / English:** switch with the button in the top-right corner of every page. The default follows the browser's language.

**Small jobs on local GPUs:** bookings ask for the estimated GPU memory. If the job fits on a local GPU (6 GB by default, e.g. an RTX 3050), the booking dialog suggests running it on your own machine. It's only a reminder, and you can still book. Admins can change the threshold (0 = off). Usage stats also show each person's peak GPU memory.

---

## For lab members

Log in with **your Linux account on the server** (the same username and password you use for SSH).

### Connecting

Unless the admins give you a direct address, open the site through an SSH tunnel. Run this on **your own computer** (PowerShell on Windows 10+, macOS or Linux):

```bash
ssh -N -L 8080:127.0.0.1:8080 your-username@server-address
```

Keep that window open and browse to **http://localhost:8080**.

If the server's SSH does not run on port 22, add `-p`, e.g. `ssh -p 2222 -N -L 8080:127.0.0.1:8080 your-username@server-address`.

- To get the tunnel every time you SSH in, add this to `~/.ssh/config`, then just run `ssh gpu`:
  ```
  Host gpu
      HostName server-address
      User your-username
      # Port 2222            <- only if SSH is not on port 22
      LocalForward 8080 127.0.0.1:8080
  ```
- **VS Code Remote-SSH:** after connecting, open the **Ports** panel, click **Forward a Port** and enter `8080`.
- Through a jump host: `ssh -N -J you@jump-host -L 8080:127.0.0.1:8080 you@server-address`

### How booking works

- **Schedule** page: click an empty slot on a GPU's row (timeline) or drag over a time range (week view). You can pick one or several GPUs.
- Enter the **estimated GPU memory** your job needs. If it fits on a local GPU, you'll see a reminder to run it on your own machine. You can still book.
- Nobody can book a GPU that is already booked for that time. There are limits per booking and per week; see **My bookings**.
- Click your own booking to change it, cancel it, or end it early.

---

## For admins

### 1. Where to host it

**On the GPU server itself.**

- No extra machine or cost
- The site reads GPU status from the NVIDIA driver and checks Linux passwords, so both have to happen on the same machine
- It uses very few resources and won't slow down experiments (see "Resource usage")

### 2. How people connect

There are two options. **Option A needs no extra firewall port**, so start with A.

#### Option A: SSH tunnel (no extra port, recommended)

Everyone already uses SSH to reach the server, and the site can ride on that connection. Keep `host = "127.0.0.1"` in the config: the site only accepts local connections, so it is invisible from outside. Users follow [Connecting](#connecting) above.

#### Option B: open a port so people can use a browser directly

1. Make sure the firewall allows one TCP port. **One is enough**: pages, API and static files all use the same port
2. Check on the server whether something else already uses that port (no output = free), e.g. for port 80:
   ```bash
   sudo ss -ltnp | grep -E ':80\b'
   ```
   - **If 80 is free, use 80**: the URL needs no port (`http://server-ip`). The service is already allowed to bind port 80 without running as root
   - If 80 is taken (e.g. by nginx / Apache), pick another port the firewall allows
3. Edit `/etc/usage-web/config.toml`:
   ```toml
   host = "0.0.0.0"
   port = 80          # the port you chose
   ```
4. Run `sudo deploy/install.sh` (or `sudo systemctl restart usage-web`). install.sh checks the port first; if something else is listening there it names the program and does not start
5. People open `http://server-ip` (port 80) or `http://server-ip:port`

> Option B is plain http (not encrypted). That's acceptable on an internal network or VPN. To expose it more widely, put an HTTPS reverse proxy (nginx / Caddy) in front and set `cookie_secure = true`.

### 3. Installing (on the GPU server)

Requirements: Linux (Ubuntu / Debian / Rocky, …), Python 3.10+, NVIDIA driver.

```bash
git clone <this repo> usage-web && cd usage-web
sudo deploy/install.sh
```

The install script:
- creates the system account `usageweb` and adds it to the `shadow` group (PAM needs this to check passwords)
- creates `/etc/pam.d/usage-web`
- copies the app to `/opt/usage-web` and creates a Python virtual environment
- creates the config file `/etc/usage-web/config.toml` (an existing one is kept)
- installs and starts the systemd service `usage-web` (starts on boot)
- installs a daily backup at `/etc/cron.daily/usage-web-backup`

If the server can't reach the internet to install Python packages, run `pip download -r requirements.txt -d wheels/` on another machine, copy `wheels/` over, and use `pip install --no-index --find-links wheels/ -r requirements.txt`.

**Updating:** `git pull && sudo deploy/install.sh` (data and config are kept).

Useful commands:
```bash
sudo systemctl status usage-web      # status
sudo journalctl -u usage-web -f      # logs
sudo systemctl restart usage-web     # restart after changing the config
```

### 4. Accounts and admins

- **No separate accounts to manage:** anyone with a Linux account on the server can log in with their SSH password. For a new member, just `sudo adduser name`
- **Admins:** members of the `sudo` (or `wheel`) group. To make someone a site admin without sudo, create a `gpuadmin` group and add it to `admin_groups` in the config
- To limit who can log in, list groups in `allowed_groups`
- 5 wrong passwords in a row lock the account for 10 minutes; logins last 7 days

### 5. Resource usage

| | Usage |
|---|---|
| Memory | about 50–100 MB (systemd caps it at 512 MB) |
| CPU | close to 0% when idle; runs at low priority and is capped at half a core |
| GPU | **none**. NVML only reads driver info: no CUDA context, no GPU memory |
| Disk | app < 50 MB; usage history is aggregated per hour, a few MB per year |

GPU status is cached for 5 seconds, so even 30 people with the page open cause only one query.

### 6. Backup and restore

A backup is written every day to `/var/backups/usage-web/usage-YYYYMMDD.db` and kept for 30 days.

To restore:
```bash
sudo systemctl stop usage-web
sudo cp /var/backups/usage-web/usage-20260101.db /var/lib/usage-web/usage.db
sudo chown usageweb:usageweb /var/lib/usage-web/usage.db
sudo systemctl start usage-web
```

### 7. Troubleshooting

- **Correct password but login fails:** check `journalctl -u usage-web`. Usually the service can't read `/etc/shadow`; make sure `id usageweb` lists the `shadow` group. LDAP / NIS accounts work through the system's `common-auth` PAM config and normally need nothing extra
- **Live status says it can't read the GPUs:** make sure `nvidia-smi` works on the server
- **Process owner shows "?":** `/proc` is mounted with `hidepid`, so the site can't see other users' processes
- **Times look wrong:** pages use the browser's time zone; weekly quotas use the config's `timezone` (weeks start Monday 00:00)

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                                   # tests
USAGE_WEB_MOCK=1 .venv/bin/python -m app           # test mode: fake GPUs, any username with password "test"
```

In test mode, usernames starting with `admin` are admins. Layout:

```
app/
  main.py      site, login, pages          api.py      GPU status / booking / stats API
  auth.py      PAM login, lockout          admin.py    admin API
  bookings.py  booking rules (conflicts, quotas, maintenance)
  gpu.py       reads GPUs via NVML / nvidia-smi      sampler.py  records actual users every minute
  db.py        SQLite tables               config.py   config file
  i18n.py      all UI text in Chinese and English
  templates/   pages                       static/     CSS, JS, FullCalendar (bundled, no internet needed)
deploy/        install.sh, systemd service, backup script
```

To change or add UI text, edit `app/i18n.py`. Each entry holds the Chinese and English text side by side.

## License

This project is licensed under the [MIT License](LICENSE). The bundled FullCalendar (`app/static/vendor/fullcalendar/`) is also MIT-licensed; its license file is kept in that folder.
