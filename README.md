# GPU 伺服器使用登記網站

給實驗室共用 GPU 伺服器用的小網站：看即時使用狀況、預約 GPU 時段，直接用伺服器的 Linux 帳號登入。

| 頁面 | 功能 |
|---|---|
| **即時狀態** | 每張 GPU 的使用率、記憶體、溫度、功耗、正在跑的程式與擁有者；目前 / 下一個預約者；CPU、RAM、硬碟；公告與維護時段。每 10 秒更新 |
| **預約時間表** | 「GPU 時間表」（每張卡一列，7 天）與「週曆」兩種檢視；點空白處或拖曳即可預約，可選多張卡、填用途；自己的預約可改時間 / 取消 / 提前結束 |
| **我的預約** | 自己的預約列表、本週已用配額 |
| **使用統計** | 每人每週「預約 GPU·小時」vs「實際使用 GPU·小時」，以及沒預約就使用的時數 |
| **管理**（sudo 群組） | 預約規則（單次上限、每週配額、可提前天數、單次最多幾張）、公告、維護時段、操作紀錄、取消任何人的預約 |

自動檢查：同一張 GPU 不能重複預約、不能預約維護時段、不能超過配額；儀表板會把「沒預約就在用」標黃、「用了別人預約的卡」標紅。

---

## 1. 架在哪裡？

**直接架在那台 GPU 伺服器上。**

- 不用另外準備機器或花錢
- 網站要讀 GPU 狀態（NVIDIA 驅動程式），也要用 Linux 帳號密碼登入，兩者都必須在同一台機器上
- 資源用量很小，不會影響大家跑實驗（見下方「資源用量」）

## 2. 大家怎麼連進來？（機房 port 的問題）

有兩種方式，**方案 A 不用申請任何 port**，建議先用 A。

### 方案 A：SSH 通道（不用申請 port，推薦）

大家本來就要用 SSH 連伺服器，網站可以借用 SSH 的連線。設定檔保持 `host = "127.0.0.1"`，網站只接受本機連線，外面看不到，也比較安全。

每個人在**自己的電腦**上執行（Windows 10 以上的 PowerShell、Mac、Linux 都可以）：

```bash
ssh -N -L 8080:127.0.0.1:8080 你的帳號@伺服器位址
```

保持這個視窗開著，然後瀏覽器打開 **http://localhost:8080**。

更方便的做法：
- **寫進 `~/.ssh/config`**，之後每次 `ssh gpu` 就自動帶上網站：
  ```
  Host gpu
      HostName 伺服器位址
      User 你的帳號
      LocalForward 8080 127.0.0.1:8080
  ```
- **用 VS Code Remote-SSH 的人**：連上伺服器後，在下方「連接埠 (Ports)」面板按「轉送連接埠」輸入 `8080`，就能直接開網頁。
- 如果 SSH 要先經過跳板機：`ssh -N -J 帳號@跳板機 -L 8080:127.0.0.1:8080 帳號@伺服器`

### 方案 B：申請一個 port，讓區網直接連

1. 向機房申請開放一個 TCP port（例如 8080），**只需要一個**，網頁、API、靜態檔案都走同一個 port
2. 修改 `/etc/usage-web/config.toml`：
   ```toml
   host = "0.0.0.0"
   port = 8080        # 改成申請到的 port
   ```
3. `sudo systemctl restart usage-web`
4. 大家用 `http://伺服器IP:8080` 連線

> 方案 B 的連線沒有加密（http）。只在內網 / VPN 使用還可以接受；如果要對外開放，請在前面加 HTTPS 反向代理（nginx / Caddy），並把 `cookie_secure = true`。

## 3. 安裝（在 GPU 伺服器上）

需求：Ubuntu / Debian / Rocky 等 Linux、Python 3.10 以上、NVIDIA 驅動程式。

```bash
git clone <這個 repo> usage-web && cd usage-web
sudo deploy/install.sh
```

安裝腳本會：
- 建立系統帳號 `usageweb`，並加入 `shadow` 群組（PAM 驗證密碼需要）
- 建立 `/etc/pam.d/usage-web`
- 把程式放到 `/opt/usage-web`，建立 Python 虛擬環境
- 建立設定檔 `/etc/usage-web/config.toml`（已存在就不覆蓋）
- 安裝並啟動 systemd 服務 `usage-web`（開機自動啟動）
- 安裝每日備份 `/etc/cron.daily/usage-web-backup`

伺服器如果不能連外網裝 Python 套件，可以先在別台機器 `pip download -r requirements.txt -d wheels/`，複製過去後改用 `pip install --no-index --find-links wheels/ -r requirements.txt`。

**更新版本**：`git pull && sudo deploy/install.sh`（資料和設定都會保留）。

常用指令：
```bash
sudo systemctl status usage-web      # 狀態
sudo journalctl -u usage-web -f      # 看 log
sudo systemctl restart usage-web     # 改設定後重啟
```

## 4. 帳號與管理員

- **不用另外管理帳號**：有伺服器 Linux 帳號的人就能登入，密碼跟 SSH 相同。新成員只要 `sudo adduser 名字` 就好
- **管理員**：屬於 `sudo`（或 `wheel`）群組的人。想讓不是 sudo 的人當網站管理員，可以建立 `gpuadmin` 群組，並加到設定檔的 `admin_groups`
- 只想讓部分人使用：在 `allowed_groups` 填入群組名稱
- 連續輸錯密碼 5 次會鎖 10 分鐘；登入狀態保留 7 天

## 5. 資源用量

| 項目 | 用量 |
|---|---|
| 記憶體 | 約 50–100 MB（systemd 另外限制最多 512 MB） |
| CPU | 閒置時接近 0%；服務以較低優先權執行，最多用半顆核心 |
| GPU | **不佔用**。透過 NVML 只讀驅動程式資訊，不建立 CUDA context、不佔顯示記憶體 |
| 硬碟 | 程式 < 50 MB；使用紀錄按小時彙總，一年約數 MB |

GPU 狀態在後端快取 5 秒，30 個人同時開網頁也只會查一次。

## 6. 備份與還原

每天自動備份到 `/var/backups/usage-web/usage-YYYYMMDD.db`，保留 30 天。

還原：
```bash
sudo systemctl stop usage-web
sudo cp /var/backups/usage-web/usage-20260101.db /var/lib/usage-web/usage.db
sudo chown usageweb:usageweb /var/lib/usage-web/usage.db
sudo systemctl start usage-web
```

## 7. 常見問題

- **帳號密碼正確卻登入失敗**：看 `journalctl -u usage-web`。通常是服務讀不到 `/etc/shadow`；確認 `id usageweb` 有 `shadow` 群組。若使用 LDAP / NIS 帳號，PAM 設定會沿用系統的 `common-auth`，一般不需要額外設定
- **儀表板顯示「讀不到 GPU」**：在伺服器上確認 `nvidia-smi` 能執行
- **程式擁有者顯示「?」**：系統開了 `/proc` 的 `hidepid`，網站看不到其他使用者的程式
- **時間不對**：網頁以瀏覽器的時區顯示，每週配額以設定檔的 `timezone` 計算（週一 00:00 起算）

## 開發

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                                   # 測試
USAGE_WEB_MOCK=1 .venv/bin/python -m app           # 測試模式：假 GPU，任何帳號用密碼 test 登入
```

測試模式下，帳號以 `admin` 開頭的是管理員。程式結構：

```
app/
  main.py      網站、登入、頁面      api.py      GPU 狀態 / 預約 / 統計 API
  auth.py      PAM 登入、登入鎖定    admin.py    管理 API
  bookings.py  預約規則（衝突、配額、維護時段）
  gpu.py       NVML / nvidia-smi 讀取 GPU      sampler.py  每分鐘記錄實際使用者
  db.py        SQLite 資料表         config.py   設定檔
  templates/   頁面                  static/     CSS、JS、FullCalendar（已內含，不需連外網）
deploy/        install.sh、systemd 服務、備份腳本
```
