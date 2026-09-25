"""UI text in Traditional Chinese and English. Pages pick the language from the
`lang` cookie (set by the header toggle), falling back to the browser's language."""

from __future__ import annotations

from fastapi import Request

LANGS = ("zh", "en")

# key: (zh, en). Placeholders use {name}; JS reads the same table.
STRINGS: dict[str, tuple[str, str]] = {
    # ---- layout / nav
    "site.title": ("GPU 伺服器使用登記", "GPU Server Booking"),
    "nav.dashboard": ("即時狀態", "Live status"),
    "nav.calendar": ("預約時間表", "Schedule"),
    "nav.my": ("我的預約", "My bookings"),
    "nav.stats": ("使用統計", "Usage stats"),
    "nav.admin": ("管理", "Admin"),
    "nav.logout": ("登出", "Log out"),
    "badge.admin": ("管理員", "Admin"),
    "badge.mock": ("測試模式", "Test mode"),
    "lang.switch": ("English", "中文"),
    # ---- login
    "login.title": ("登入", "Log in"),
    "login.help": ("請用伺服器的 Linux 帳號密碼登入（跟 SSH 登入相同）。",
                   "Log in with your Linux account on the server (same as SSH)."),
    "login.mock": ("測試模式：任意帳號，密碼 test；帳號以 admin 開頭者為管理員。",
                   "Test mode: any username with password test; usernames starting with admin are admins."),
    "login.username": ("帳號", "Username"),
    "login.password": ("密碼", "Password"),
    "login.submit": ("登入", "Log in"),
    # ---- common
    "common.loading": ("讀取中…", "Loading…"),
    "common.close": ("關閉", "Close"),
    "common.save": ("儲存", "Save"),
    "common.delete": ("刪除", "Delete"),
    "common.cancel": ("取消", "Cancel"),
    "common.start": ("開始", "Start"),
    "common.end": ("結束", "End"),
    "common.hours": ("時數", "Hours"),
    "common.new_booking": ("＋ 新增預約", "+ New booking"),
    "common.error_status": ("錯誤 {status}", "Error {status}"),
    "common.login_first": ("請先登入", "Please log in"),
    "common.update_failed": ("更新失敗：{msg}", "Update failed: {msg}"),
    "gpu.label": ("GPU {list}", "GPU {list}"),
    # ---- dashboard
    "dash.cpu": ("CPU", "CPU"),
    "dash.cpu_sub": ("{cores} 核心 · 負載 {load}", "{cores} cores · load {load}"),
    "dash.ram": ("記憶體 (RAM)", "Memory (RAM)"),
    "dash.disk": ("硬碟 {path}", "Disk {path}"),
    "dash.disk_sub": ("剩 {free} GB / 共 {total} GB", "{free} GB free of {total} GB"),
    "dash.ssh": ("SSH 登入中", "Logged in via SSH"),
    "dash.legend_unbooked": ("沒預約就在用", "running without a booking"),
    "dash.legend_conflict": ("用了別人預約的卡", "running on someone else's booking"),
    "dash.chip_unbooked": ("⚠ 未預約", "⚠ Not booked"),
    "dash.chip_unbooked_title": ("這張卡目前沒人預約", "Nobody has booked this GPU right now"),
    "dash.chip_conflict": ("✕ 佔用", "✕ Conflict"),
    "dash.chip_conflict_title": ("這張卡目前是別人預約的", "Someone else has booked this GPU right now"),
    "dash.booked_by": ("已預約：{user}", "Booked: {user}"),
    "dash.in_use": ("使用中", "In use"),
    "dash.idle": ("● 空閒", "● Free"),
    "dash.booked_until": ("{user} 預約到 {time}", "{user} until {time}"),
    "dash.no_booking": ("目前沒有預約", "No booking right now"),
    "dash.next": ("下一個：{user}，{range}", "Next: {user}, {range}"),
    "dash.no_procs": ("沒有程式在跑", "No processes"),
    "dash.util": ("使用率", "Utilization"),
    "dash.mem": ("記憶體", "Memory"),
    "dash.temp": ("溫度", "Temp"),
    "dash.power": ("功耗", "Power"),
    "dash.book_this": ("預約這張", "Book this GPU"),
    "dash.no_gpus": ("沒有偵測到 GPU", "No GPUs detected"),
    "dash.updated": ("更新於 {time}（每 10 秒）", "Updated {time} (every 10 s)"),
    "dash.maintenance": ("🛠 維護時段：{range}　{reason}", "🛠 Maintenance: {range}  {reason}"),
    "gpu.error.none": ("讀不到 GPU（找不到 NVIDIA 驅動程式 / nvidia-smi）",
                       "Cannot read GPUs (NVIDIA driver / nvidia-smi not found)"),
    "gpu.error.read": ("讀取 GPU 失敗：{detail}", "Failed to read GPUs: {detail}"),
    # ---- calendar
    "cal.title": ("預約時間表", "Schedule"),
    "cal.help": ("在空白處按一下（時間表）或拖曳選取時段（週曆）即可預約；點自己的預約可以修改或取消。",
                 "Click an empty slot (timeline) or drag over a time range (week view) to book. Click your own booking to change or cancel it."),
    "cal.tab_timeline": ("GPU 時間表", "GPU timeline"),
    "cal.tab_week": ("週曆", "Week"),
    "cal.legend_mine": ("我的預約", "My bookings"),
    "cal.legend_other": ("其他人", "Others"),
    "cal.legend_maint": ("維護時段", "Maintenance"),
    "cal.prev": ("‹ 前 7 天", "‹ Previous 7 days"),
    "cal.today": ("今天", "Today"),
    "cal.next": ("後 7 天 ›", "Next 7 days ›"),
    "cal.filter_all": ("不勾 = 全部", "none ticked = all"),
    "cal.quota_admin": ("本週已預約 {used} GPU·小時（管理員不受配額限制）",
                        "{used} GPU-hours booked this week (admins have no quota)"),
    "cal.quota": ("本週已預約 {used} / {max} GPU·小時 · 單次最長 {per} 小時 · 可預約 {days} 天內",
                  "{used} / {max} GPU-hours booked this week · max {per} h per booking · up to {days} days ahead"),
    "cal.maint_short": ("維護", "Maint."),
    "cal.maint_title": ("維護：{reason}", "Maintenance: {reason}"),
    "cal.needs_mem": ("需 {gb} GB", "needs {gb} GB"),
    "cal.dlg_new": ("新增預約", "New booking"),
    "cal.dlg_edit": ("修改預約", "Edit booking"),
    "cal.dlg_owner": ("預約者：{user}（管理員修改）", "Booked by {user} (editing as admin)"),
    "cal.dlg_gpus": ("GPU（可同時選兩張；劃線 = 該時段已被預約）", "GPUs (you can pick several; struck through = already booked)"),
    "cal.dlg_mem": ("預估需要的 GPU 記憶體（每張卡，GB）", "Estimated GPU memory needed (per GPU, GB)"),
    "cal.dlg_mem_ph": ("例如 12", "e.g. 12"),
    "cal.dlg_local_hint": ("💡 預估在 {limit} GB 以內，本地顯卡應該跑得動，可以的話請先在自己的電腦上跑，把伺服器留給需要大記憶體的實驗。（僅提醒，仍可直接預約）",
                           "💡 This fits in {limit} GB, so your local GPU can probably run it. If possible, please run it on your own machine and leave the server for jobs that need more memory. (Just a reminder — you can still book.)"),
    "cal.dlg_purpose": ("用途 / 備註", "Purpose / notes"),
    "cal.dlg_purpose_ph": ("例如：訓練 ResNet 實驗、論文實驗", "e.g. ResNet training for my thesis"),
    "cal.busy_by": ("已被 {user} 預約", "Booked by {user}"),
    "cal.cancel_booking": ("取消預約", "Cancel booking"),
    "cal.end_now": ("提前結束", "End now"),
    "cal.confirm_cancel": ("確定要取消這個預約？", "Cancel this booking?"),
    "cal.confirm_end": ("確定要現在結束這個預約？", "End this booking now?"),
    "cal.cancelled": ("已取消預約", "Booking cancelled"),
    "cal.ended": ("已提前結束", "Booking ended"),
    "cal.updated": ("已更新預約", "Booking updated"),
    "cal.saved_new": ("已預約：{gpus}，{range}（{hours} 小時）", "Booked {gpus}, {range} ({hours} h)"),
    "cal.saved_edit": ("已更新：{gpus}，{range}（{hours} 小時）", "Updated {gpus}, {range} ({hours} h)"),
    "cal.past": ("不能預約過去的時間", "You can't book a time in the past"),
    # ---- my bookings
    "my.title": ("我的預約", "My bookings"),
    "my.week_used": ("本週已預約", "Booked this week"),
    "my.gpu_hours": ("{n} GPU·小時", "{n} GPU-hours"),
    "my.admin_no_quota": ("管理員不受配額限制", "Admins have no quota"),
    "my.limit": ("上限 {n}", "limit {n}"),
    "my.per_booking": ("單次最長", "Max per booking"),
    "my.hours_n": ("{n} 小時", "{n} hours"),
    "my.ahead": ("可提前預約", "Book ahead"),
    "my.days_n": ("{n} 天", "{n} days"),
    "my.max_gpus": ("單次最多", "GPUs per booking"),
    "my.gpus_n": ("{n} 張 GPU", "{n} GPUs"),
    "my.gpus_any": ("不限張數", "No limit"),
    "my.list_title": ("近 30 天與未來的預約", "Last 30 days and upcoming"),
    "my.col_state": ("狀態", "Status"),
    "my.col_purpose": ("用途", "Purpose"),
    "my.state_ended": ("已結束", "Ended"),
    "my.state_running": ("● 進行中", "● Running"),
    "my.state_upcoming": ("即將開始", "Upcoming"),
    "my.empty": ("還沒有預約，", "No bookings yet. "),
    "my.go_book": ("去預約", "Book a GPU"),
    # ---- stats
    "stats.title": ("使用統計", "Usage stats"),
    "stats.show": ("顯示", "Show"),
    "stats.week1": ("本週", "This week"),
    "stats.week4": ("近 4 週", "Last 4 weeks"),
    "stats.week12": ("近 12 週", "Last 12 weeks"),
    "stats.help": ("「預約」= 預約的 GPU·小時；「實際使用」= 每分鐘檢查一次，該使用者在 GPU 上有程式在跑的 GPU·小時；「未預約使用」= 實際使用中，沒有對應預約的部分；「最高顯存」= 單張卡上看到的最高 GPU 記憶體用量。",
                   "Booked = GPU-hours booked. Used = GPU-hours the user actually had processes on a GPU (checked every minute). Unbooked = the part of Used without a matching booking. Peak memory = highest GPU memory seen on one GPU."),
    "stats.booked": ("預約", "Booked"),
    "stats.used": ("實際使用", "Used"),
    "stats.col_user": ("使用者", "User"),
    "stats.col_booked": ("預約 (GPU·時)", "Booked (GPU-h)"),
    "stats.col_used": ("實際使用 (GPU·時)", "Used (GPU-h)"),
    "stats.col_unbooked": ("未預約使用", "Unbooked"),
    "stats.col_peak": ("最高顯存", "Peak memory"),
    "stats.bar_title": ("預約 {b}／實際 {u} GPU·小時", "Booked {b} / used {u} GPU-hours"),
    "stats.local_ok": ("本地可跑？", "Fits locally?"),
    "stats.local_ok_title": ("最高用量不到 {limit} GB，本地顯卡可能就跑得動", "Peak under {limit} GB; a local GPU could probably run it"),
    "stats.empty": ("這週沒有紀錄", "No records this week"),
    # ---- admin
    "admin.title": ("管理", "Admin"),
    "admin.rules": ("預約規則", "Booking rules"),
    "admin.rules_help": ("管理員不受配額限制，但仍不能與別人的預約重疊。", "Admins have no quota but still can't overlap other bookings."),
    "admin.r_hours": ("單次預約最長（小時）", "Max hours per booking"),
    "admin.r_week": ("每人每週上限（GPU·小時 = 小時 × 張數）", "Weekly limit per person (GPU-hours = hours × GPUs)"),
    "admin.r_days": ("最多可提前幾天預約", "How many days ahead people can book"),
    "admin.r_gpus": ("單次最多幾張 GPU（0 = 不限）", "Max GPUs per booking (0 = no limit)"),
    "admin.r_local": ("本地顯卡記憶體（GB）：預估用量在這以下時，提醒改在本地跑（僅提醒；0 = 不提醒）",
                      "Local GPU memory (GB): remind people to run smaller jobs locally (reminder only; 0 = off)"),
    "admin.r_flag": ("在沒人預約的卡上跑程式也標示「未預約」", "Flag processes on GPUs nobody has booked as \"Not booked\""),
    "admin.save_rules": ("儲存規則", "Save rules"),
    "admin.rules_saved": ("規則已儲存", "Rules saved"),
    "admin.ann": ("公告", "Announcements"),
    "admin.ann_ph": ("例如：9/30 18:00 起停機更新驅動程式", "e.g. Server down from 9/30 18:00 for a driver update"),
    "admin.ann_post": ("發布公告", "Post"),
    "admin.ann_posted": ("已發布", "Posted"),
    "admin.ann_empty": ("沒有公告", "No announcements"),
    "admin.ann_confirm": ("刪除這則公告？", "Delete this announcement?"),
    "admin.maint": ("維護時段", "Maintenance windows"),
    "admin.maint_help": ("維護時段內所有 GPU 都不能預約。已存在的預約不會自動刪除，會列出來讓你決定。",
                         "No GPU can be booked during maintenance. Existing bookings are not removed automatically; they are listed so you can decide."),
    "admin.maint_reason": ("原因", "Reason"),
    "admin.maint_reason_ph": ("例如：更新 CUDA / 機房停電", "e.g. CUDA upgrade / power outage"),
    "admin.maint_add": ("新增維護時段", "Add maintenance window"),
    "admin.maint_added": ("已新增維護時段", "Maintenance window added"),
    "admin.maint_empty": ("沒有維護時段", "No maintenance windows"),
    "admin.maint_confirm": ("刪除這個維護時段？", "Delete this maintenance window?"),
    "admin.maint_conflicts": ("以下預約與維護時段重疊：", "These bookings overlap the maintenance window:"),
    "admin.cancel_this": ("取消這筆", "Cancel it"),
    "admin.cancelled": ("已取消", "Cancelled"),
    "admin.audit": ("操作紀錄", "Activity log"),
    "admin.col_time": ("時間", "Time"),
    "admin.col_user": ("使用者", "User"),
    "admin.col_action": ("動作", "Action"),
    "admin.col_detail": ("內容", "Details"),
    "audit.create_booking": ("新增預約", "New booking"),
    "audit.update_booking": ("修改預約", "Edited booking"),
    "audit.delete_booking": ("取消預約", "Cancelled booking"),
    "audit.end_booking_early": ("提前結束", "Ended early"),
    "audit.update_rules": ("修改規則", "Changed rules"),
    "audit.create_blackout": ("新增維護", "Added maintenance"),
    "audit.delete_blackout": ("刪除維護", "Removed maintenance"),
    "audit.create_announcement": ("發布公告", "Posted announcement"),
    "audit.delete_announcement": ("刪除公告", "Deleted announcement"),
    # ---- server errors
    "err.login_first": ("請先登入", "Please log in"),
    "err.admin_only": ("需要管理員權限", "Admins only"),
    "err.login_locked": ("登入失敗次數過多，請 {minutes} 分鐘後再試", "Too many failed logins; try again in {minutes} minutes"),
    "err.login_bad": ("帳號或密碼錯誤（請使用伺服器的 Linux 帳號）", "Wrong username or password (use your Linux account on the server)"),
    "err.no_gpu": ("請至少選一張 GPU", "Pick at least one GPU"),
    "err.bad_gpu": ("GPU {bad} 不存在（本機共 {count} 張，編號 0–{last}）", "GPU {bad} doesn't exist (this server has {count}: 0–{last})"),
    "err.end_before_start": ("結束時間必須晚於開始時間", "End must be after start"),
    "err.ended_readonly": ("已結束的預約不能修改", "Finished bookings can't be changed"),
    "err.started_only_end": ("已開始的預約只能調整結束時間", "Only the end time of a running booking can be changed"),
    "err.end_in_past": ("結束時間不能早於現在；要提前結束請按「提前結束」", "End can't be in the past; use \"End now\" to finish early"),
    "err.past": ("不能預約過去的時間", "You can't book a time in the past"),
    "err.too_long": ("單次預約最多 {max} 小時（這次 {hours} 小時）", "A booking can be at most {max} hours (this one is {hours})"),
    "err.too_far": ("最多只能預約 {days} 天內的時段", "You can book at most {days} days ahead"),
    "err.too_many_gpus": ("單次預約最多 {max} 張 GPU", "At most {max} GPUs per booking"),
    "err.mem_required": ("請填寫預估需要的 GPU 記憶體（GB）", "Please enter the estimated GPU memory (GB)"),
    "err.quota": ("超過每週配額：{week} 起這週已預約 {used} GPU·小時，加上這次 {new}，上限 {max}",
                  "Weekly limit exceeded: the week from {week} already has {used} GPU-hours booked, this adds {new}, the limit is {max}"),
    "err.blackout": ("與維護時段衝突：{start}–{end} {reason}", "Overlaps maintenance {start}–{end} {reason}"),
    "err.conflict": ("GPU {gpus} 在 {start}–{end} 已被 {user} 預約", "GPU {gpus} is booked by {user} from {start} to {end}"),
    "err.bad_time": ("時間格式錯誤：{value}", "Invalid time: {value}"),
    "err.booking_not_found": ("找不到這筆預約", "Booking not found"),
    "err.not_owner": ("只能修改自己的預約", "You can only change your own bookings"),
    "err.ended_keep": ("已結束的預約會保留作為紀錄，不能刪除", "Finished bookings are kept as history and can't be deleted"),
    "err.blackout_not_found": ("找不到維護時段", "Maintenance window not found"),
    "err.announcement_not_found": ("找不到公告", "Announcement not found"),
}


def get_lang(request: Request) -> str:
    lang = request.cookies.get("lang")
    if lang in LANGS:
        return lang
    accept = request.headers.get("accept-language", "").lower()
    first = accept.split(",")[0].strip()
    return "zh" if first.startswith("zh") or not first else "en"


def tr(lang: str, key: str, **params) -> str:
    pair = STRINGS.get(key)
    if pair is None:
        return key
    text = pair[LANGS.index(lang) if lang in LANGS else 0]
    return text.format(**params) if params else text


def table(lang: str) -> dict[str, str]:
    i = LANGS.index(lang)
    return {k: v[i] for k, v in STRINGS.items()}


class AppError(Exception):
    """An error whose message is shown to the user in their language."""

    status = 400

    def __init__(self, key: str, status: int | None = None, **params):
        super().__init__(key)
        self.key = key
        self.params = params
        if status is not None:
            self.status = status

    def message(self, lang: str) -> str:
        return tr(lang, self.key, **self.params)
