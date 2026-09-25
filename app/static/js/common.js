// Shared helpers for all pages.
(function () {
  const pad = (n) => String(n).padStart(2, "0");

  async function api(method, url, body) {
    const opts = { method, headers: { "X-Requested-With": "fetch" } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (res.status === 401) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname);
      throw new Error("請先登入");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let msg = data.detail;
      if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join("；");
      throw new Error(msg || `錯誤 ${res.status}`);
    }
    return data;
  }

  let toastTimer;
  function toast(msg, isError) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "show" + (isError ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.className = ""), isError ? 6000 : 2500);
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
  function fmtTime(d) { d = new Date(d); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  function fmtDate(d) { d = new Date(d); return `${d.getMonth() + 1}/${d.getDate()}（${WEEKDAYS[d.getDay()]}）`; }
  function fmtDateTime(d) { return `${fmtDate(d)} ${fmtTime(d)}`; }
  function sameDay(a, b) { a = new Date(a); b = new Date(b); return a.toDateString() === b.toDateString(); }
  function fmtRange(s, e) {
    return sameDay(s, e) ? `${fmtDateTime(s)}–${fmtTime(e)}` : `${fmtDateTime(s)} → ${fmtDateTime(e)}`;
  }
  function hours(s, e) { return (new Date(e) - new Date(s)) / 3.6e6; }
  // <input type="datetime-local"> value <-> Date
  function toInput(d) { d = new Date(d); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  function fromInput(v) { return new Date(v); }
  function gpuLabel(list) { return "GPU " + list.join(", "); }

  window.U = { api, toast, esc, fmtTime, fmtDate, fmtDateTime, fmtRange, hours, toInput, fromInput, gpuLabel, pad };
})();
