(function () {
  const { api, toast, esc, fmtRange, fmtTime, toInput, fromInput, gpuLabel, hours } = U;
  const HOUR_W = 20; // px per hour in the GPU timeline
  const DAYS = 7;
  const DAY_MS = 864e5;

  let me = null;
  let tlStart = startOfDay(new Date());
  let tlData = { bookings: [], blackouts: [] };
  let calendar = null;
  let gpuFilter = new Set();

  function startOfDay(d) { d = new Date(d); d.setHours(0, 0, 0, 0); return d; }
  function nextHalfHour() { const d = new Date(); d.setSeconds(0, 0); d.setMinutes(d.getMinutes() < 30 ? 30 : 60); return d; }
  const isMine = (b) => b.username === APP.username;
  const canEdit = (b) => (isMine(b) || APP.isAdmin) && new Date(b.end) > new Date();
  const eventsUrl = (s, e) => `/api/events?start=${encodeURIComponent(new Date(s).toISOString())}&end=${encodeURIComponent(new Date(e).toISOString())}`;

  async function loadMe() {
    me = await api("GET", "/api/me");
    const r = me.rules;
    document.getElementById("quota").textContent = APP.isAdmin
      ? T("cal.quota_admin", { used: me.week_gpu_hours })
      : T("cal.quota", { used: me.week_gpu_hours, max: r.max_gpu_hours_per_week, per: r.max_hours_per_booking, days: r.max_days_ahead });
  }

  // ---------------- GPU timeline ----------------
  async function loadTimeline() {
    const end = new Date(tlStart.getTime() + DAYS * DAY_MS);
    tlData = await api("GET", eventsUrl(tlStart, end));
    renderTimeline();
  }

  function xOf(t) { return ((new Date(t) - tlStart) / 3.6e6) * HOUR_W; }

  function renderTimeline() {
    const width = DAYS * 24 * HOUR_W;
    const dayW = 24 * HOUR_W;
    const grid = `background-image: repeating-linear-gradient(to right, var(--axis) 0 1px, transparent 1px ${dayW}px), repeating-linear-gradient(to right, var(--grid) 0 1px, transparent 1px ${HOUR_W * 3}px);`;
    let head = `<div class="tl-head" style="height:44px"><div class="tl-label">GPU</div><div class="tl-days" style="width:${width}px;height:44px">`;
    for (let d = 0; d < DAYS; d++) {
      const day = new Date(tlStart.getTime() + d * DAY_MS);
      head += `<div class="tl-day" style="left:${d * dayW}px;width:${dayW}px"><b>${U.fmtDate(day)}</b>`;
      for (let h = 3; h < 24; h += 3) head += `<span class="tl-hour-label num" style="left:${h * HOUR_W}px">${U.pad(h)}</span>`;
      head += `</div>`;
    }
    head += `</div></div>`;

    const now = new Date();
    const nowX = xOf(now);
    const nowLine = nowX >= 0 && nowX <= width ? `<div class="tl-now" style="left:${nowX}px"></div>` : "";

    let rows = "";
    for (let g = 0; g < me.gpu_count; g++) {
      let bars = "";
      for (const bo of tlData.blackouts) {
        const l = Math.max(0, xOf(bo.start)), r = Math.min(width, xOf(bo.end));
        if (r > l) bars += `<div class="tl-bar maint" style="left:${l}px;width:${r - l}px" title="${esc(T("cal.maint_title", { reason: bo.reason }))}">${r - l > 60 ? T("cal.maint_short") : ""}</div>`;
      }
      for (const b of tlData.bookings) {
        if (!b.gpus.includes(g)) continue;
        const l = Math.max(0, xOf(b.start)), r = Math.min(width, xOf(b.end));
        if (r <= l) continue;
        const title = [b.username, fmtRange(b.start, b.end), gpuLabel(b.gpus), b.mem_gb ? T("cal.needs_mem", { gb: b.mem_gb }) : "", b.purpose].filter(Boolean).join(" | ");
        bars += `<div class="tl-bar ${isMine(b) ? "mine" : ""}" data-id="${b.id}" style="left:${l}px;width:${Math.max(r - l, 3)}px" title="${esc(title)}">${esc(b.username)}</div>`;
      }
      rows += `<div class="tl-row"><div class="tl-label">GPU ${g}</div><div class="tl-lane" data-gpu="${g}" style="width:${width}px;${grid}">${bars}${nowLine}</div></div>`;
    }
    document.getElementById("timeline").innerHTML = head + rows;
  }

  document.getElementById("timeline").addEventListener("click", (ev) => {
    const bar = ev.target.closest(".tl-bar");
    if (bar && bar.dataset.id) {
      const b = tlData.bookings.find((x) => String(x.id) === bar.dataset.id);
      if (b) openBooking(b);
      return;
    }
    if (bar) return; // maintenance
    const lane = ev.target.closest(".tl-lane");
    if (!lane) return;
    const x = ev.clientX - lane.getBoundingClientRect().left;
    const halfHours = Math.floor(x / (HOUR_W / 2));
    let start = new Date(tlStart.getTime() + halfHours * 18e5);
    if (start < new Date()) start = nextHalfHour();
    openDialog({ start, end: new Date(start.getTime() + 2 * 36e5), gpus: [Number(lane.dataset.gpu)] });
  });

  function shiftTimeline(days) {
    tlStart = days === 0 ? startOfDay(new Date()) : new Date(tlStart.getTime() + days * DAY_MS);
    loadTimeline().catch((e) => toast(e.message, true));
  }
  document.getElementById("tl-prev").onclick = () => shiftTimeline(-DAYS);
  document.getElementById("tl-next").onclick = () => shiftTimeline(DAYS);
  document.getElementById("tl-today").onclick = () => shiftTimeline(0);

  function scrollTimelineToNow() {
    const el = document.getElementById("timeline-scroll");
    el.scrollLeft = Math.max(0, xOf(new Date()) - 3 * HOUR_W);
  }

  // ---------------- week calendar (FullCalendar) ----------------
  function renderGpuFilter() {
    const box = document.getElementById("gpu-filter");
    let html = "";
    for (let g = 0; g < me.gpu_count; g++) {
      html += `<label><input type="checkbox" value="${g}" ${gpuFilter.has(g) ? "checked" : ""}> GPU ${g}</label>`;
    }
    box.innerHTML = html + `<span class="small muted" style="align-self:center">${T("cal.filter_all")}</span>`;
    box.onchange = () => {
      gpuFilter = new Set([...box.querySelectorAll("input:checked")].map((i) => Number(i.value)));
      calendar && calendar.refetchEvents();
    };
  }

  function initCalendar() {
    calendar = new FullCalendar.Calendar(document.getElementById("calendar"), {
      locale: U.ZH ? "zh-tw" : "en",
      initialView: window.innerWidth < 700 ? "timeGridDay" : "timeGridWeek",
      firstDay: 1,
      headerToolbar: { left: "prev,next today", center: "title", right: "timeGridWeek,timeGridDay,listWeek" },
      nowIndicator: true,
      selectable: true,
      selectMirror: true,
      slotDuration: "00:30:00",
      scrollTime: `${U.pad(Math.max(0, new Date().getHours() - 2))}:00:00`,
      height: Math.max(520, window.innerHeight - 260),
      allDaySlot: false,
      slotEventOverlap: false,
      eventTimeFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
      slotLabelFormat: { hour: "2-digit", minute: "2-digit", hour12: false },
      events: async (info, ok, fail) => {
        try {
          const d = await api("GET", eventsUrl(info.start, info.end));
          const evs = d.bookings
            .filter((b) => !gpuFilter.size || b.gpus.some((g) => gpuFilter.has(g)))
            .map((b) => ({
              id: String(b.id),
              title: `${b.username} · ${gpuLabel(b.gpus)}${b.purpose ? " · " + b.purpose : ""}`,
              start: b.start,
              end: b.end,
              classNames: [isMine(b) ? "mine" : "other"],
              editable: canEdit(b) && new Date(b.start) > new Date(),
              extendedProps: { booking: b },
            }));
          for (const bo of d.blackouts) {
            evs.push({ start: bo.start, end: bo.end, display: "background", classNames: ["maint-bg"], title: T("cal.maint_title", { reason: bo.reason }) });
          }
          ok(evs);
        } catch (e) { fail(e); toast(e.message, true); }
      },
      select: (info) => {
        calendar.unselect();
        let start = info.start;
        if (info.end <= new Date()) return toast(T("cal.past"), true);
        if (start < new Date()) start = nextHalfHour();
        openDialog({ start, end: info.end, gpus: gpuFilter.size === 1 ? [...gpuFilter] : [] });
      },
      eventClick: (info) => { const b = info.event.extendedProps.booking; if (b) openBooking(b); },
      eventDrop: moved,
      eventResize: moved,
    });
    calendar.render();
  }

  async function moved(info) {
    const b = info.event.extendedProps.booking;
    try {
      await api("PATCH", `/api/bookings/${b.id}`, { gpus: b.gpus, start: info.event.start.toISOString(), end: info.event.end.toISOString(), purpose: b.purpose, mem_gb: b.mem_gb });
      toast(T("cal.updated"));
      reloadAll();
    } catch (e) { info.revert(); toast(e.message, true); }
  }

  // ---------------- tabs ----------------
  function showView(view) {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    document.getElementById("timeline-view").hidden = view !== "timeline";
    document.getElementById("timeline-nav").hidden = view !== "timeline";
    document.getElementById("week-view").hidden = view !== "week";
    document.getElementById("gpu-filter").hidden = view !== "week";
    if (view === "week") { if (!calendar) initCalendar(); else calendar.updateSize(); }
    try { localStorage.setItem("calendar-view", view); } catch (e) { /* storage unavailable */ }
  }
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showView(b.dataset.view)));

  function reloadAll() {
    loadTimeline().catch((e) => toast(e.message, true));
    if (calendar) calendar.refetchEvents();
    loadMe().catch(() => {});
  }

  // ---------------- dialog ----------------
  const dlg = document.getElementById("booking-dialog");
  const f = {
    start: document.getElementById("f-start"),
    end: document.getElementById("f-end"),
    gpus: document.getElementById("f-gpus"),
    purpose: document.getElementById("f-purpose"),
    error: document.getElementById("dlg-error"),
    del: document.getElementById("dlg-delete"),
    title: document.getElementById("dlg-title"),
    owner: document.getElementById("dlg-owner"),
    save: document.getElementById("dlg-save"),
    mem: document.getElementById("f-mem"),
    localHint: document.getElementById("local-hint"),
  };
  const localLimit = () => (me && me.rules.local_gpu_mem_gb) || 0;

  function updateLocalHint() {
    const limit = localLimit(), mem = Number(f.mem.value);
    f.localHint.textContent = T("cal.dlg_local_hint", { limit });
    f.localHint.hidden = !(limit > 0 && mem > 0 && mem <= limit);
  }
  f.mem.addEventListener("input", updateLocalHint);
  let editing = null;

  function openBooking(b) {
    if (!canEdit(b)) {
      toast([b.username, fmtRange(b.start, b.end), gpuLabel(b.gpus), b.mem_gb ? T("cal.needs_mem", { gb: b.mem_gb }) : "", b.purpose].filter(Boolean).join(" | "));
      return;
    }
    openDialog({ booking: b, start: new Date(b.start), end: new Date(b.end), gpus: b.gpus, purpose: b.purpose });
  }

  function openDialog({ booking = null, start, end, gpus = [], purpose = "" }) {
    editing = booking;
    const started = booking && new Date(booking.start) <= new Date();
    f.title.textContent = T(booking ? "cal.dlg_edit" : "cal.dlg_new");
    f.owner.hidden = !(booking && !isMine(booking));
    f.owner.textContent = booking ? T("cal.dlg_owner", { user: booking.username }) : "";
    f.start.value = toInput(start);
    f.end.value = toInput(end);
    f.start.disabled = !!started;
    f.purpose.value = purpose;
    f.mem.value = booking && booking.mem_gb != null ? booking.mem_gb : "";
    f.mem.required = localLimit() > 0 && !APP.isAdmin;
    updateLocalHint();
    f.error.hidden = true;
    f.del.hidden = !booking;
    f.del.textContent = T(started ? "cal.end_now" : "cal.cancel_booking");
    let html = "";
    for (let g = 0; g < me.gpu_count; g++) {
      html += `<label data-gpu="${g}"><input type="checkbox" value="${g}" ${gpus.includes(g) ? "checked" : ""} ${started ? "disabled" : ""}> GPU ${g}</label>`;
    }
    f.gpus.innerHTML = html;
    dlg.showModal();
    markBusy();
  }

  let busyTimer;
  function markBusy() {
    clearTimeout(busyTimer);
    busyTimer = setTimeout(async () => {
      const s = fromInput(f.start.value), e = fromInput(f.end.value);
      if (!(e > s)) return;
      try {
        const d = await api("GET", eventsUrl(s, e));
        const busy = new Map();
        for (const b of d.bookings) {
          if (editing && b.id === editing.id) continue;
          for (const g of b.gpus) busy.set(g, b.username);
        }
        f.gpus.querySelectorAll("label").forEach((l) => {
          const g = Number(l.dataset.gpu);
          l.classList.toggle("busy", busy.has(g));
          l.title = busy.has(g) ? T("cal.busy_by", { user: busy.get(g) }) : "";
        });
      } catch (err) { /* informational only */ }
    }, 200);
  }
  f.start.addEventListener("change", markBusy);
  f.end.addEventListener("change", markBusy);
  document.getElementById("dlg-close").onclick = () => dlg.close();

  document.getElementById("booking-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const s = fromInput(f.start.value), e = fromInput(f.end.value);
    const body = {
      gpus: [...f.gpus.querySelectorAll("input:checked")].map((i) => Number(i.value)),
      start: s.toISOString(),
      end: e.toISOString(),
      purpose: f.purpose.value,
      mem_gb: f.mem.value ? Number(f.mem.value) : null,
    };
    f.save.disabled = true;
    try {
      if (editing) await api("PATCH", `/api/bookings/${editing.id}`, body);
      else await api("POST", "/api/bookings", body);
      dlg.close();
      toast(T(editing ? "cal.saved_edit" : "cal.saved_new", { gpus: gpuLabel(body.gpus), range: fmtRange(s, e), hours: hours(s, e).toFixed(1) }));
      reloadAll();
    } catch (err) {
      f.error.textContent = err.message;
      f.error.hidden = false;
    } finally { f.save.disabled = false; }
  });

  f.del.onclick = async () => {
    const started = new Date(editing.start) <= new Date();
    if (!confirm(T(started ? "cal.confirm_end" : "cal.confirm_cancel"))) return;
    try {
      await api("DELETE", `/api/bookings/${editing.id}`);
      dlg.close();
      toast(T(started ? "cal.ended" : "cal.cancelled"));
      reloadAll();
    } catch (err) { f.error.textContent = err.message; f.error.hidden = false; }
  };

  document.getElementById("new-btn").onclick = () => {
    const s = nextHalfHour();
    openDialog({ start: s, end: new Date(s.getTime() + 2 * 36e5) });
  };

  // ---------------- start ----------------
  (async () => {
    try {
      await loadMe();
      renderGpuFilter();
      await loadTimeline();
      scrollTimelineToNow();
      let view = "timeline";
      try { view = localStorage.getItem("calendar-view") || view; } catch (e) { /* storage unavailable */ }
      showView(view);
      const gpu = new URLSearchParams(location.search).get("gpu");
      if (gpu !== null && Number(gpu) < me.gpu_count) {
        const s = nextHalfHour();
        openDialog({ start: s, end: new Date(s.getTime() + 2 * 36e5), gpus: [Number(gpu)] });
      }
    } catch (e) { toast(e.message, true); }
  })();
  setInterval(() => { if (!document.hidden && !dlg.open) reloadAll(); }, 60000);
})();
