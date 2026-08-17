// app.js — لایه‌ی مشترک ارتباط با API (Apps Script) برای همه‌ی صفحات

const API_BASE = "https://script.google.com/macros/s/AKfycbypLxCtrFW8zGrwiJpVLwhBF0B9FSHz_k-2AkxsqFl4aRTWfjsIRv3_QM-aw8rqKNub/exec";
const SESSION_KEY = "inv_session";

// محل نگهداری پیش‌فرض — هر جا انبار مشخص نشده باشد همین انتخاب می‌شود.
// باید مو‌به‌مو با DEFAULT_WAREHOUSE در webapp/Code.gs و tools/sheets_client.py یکی باشد.
const DEFAULT_WAREHOUSE = "انبار شماره ۱";

/** انبار کاربر؛ اگر ثبت نشده باشد، محل نگهداری پیش‌فرض. */
function warehouseOf(session) {
  return (session && session.warehouse ? session.warehouse : "").trim() || DEFAULT_WAREHOUSE;
}

function getSession() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch (e) {
    return null;
  }
}

function setSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function logout() {
  clearSession();
  window.location.href = "index.html";
}

/** اگر نشست نیست، به صفحه‌ی ورود برمی‌گرداند؛ وگرنه مقدار نشست را برمی‌گرداند. */
function requireSession() {
  const session = getSession();
  if (!session || !session.token) {
    window.location.href = "index.html";
    return null;
  }
  return session;
}

async function api(action, params = {}) {
  const session = getSession();
  const query = new URLSearchParams({ action, ...params });
  if (session && session.token && action !== "login") query.set("token", session.token);

  const res = await fetch(`${API_BASE}?${query.toString()}`);
  const json = await res.json();
  if (!json.success) {
    if (json.authError) {
      clearSession();
      window.location.href = "index.html";
    }
    throw new Error(json.error || "خطای نامشخص از سرور");
  }
  return json.data;
}

function toast(message, type = "ok") {
  let stack = document.querySelector(".toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "toast-stack";
    document.body.appendChild(stack);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${type === "ok" ? "ok" : "err"}`;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function setLoading(btn, loading, labelWhileLoading = "در حال ارسال...") {
  if (loading) {
    btn.dataset.originalText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${labelWhileLoading}`;
  } else {
    btn.disabled = false;
    btn.textContent = btn.dataset.originalText || btn.textContent;
  }
}

function fmtQty(q) {
  const n = Number(q);
  return Number.isInteger(n) ? n.toString() : n.toFixed(2);
}

function escapeHtml(str) {
  return (str ?? "").toString().replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function emptyRow(colspan, text) {
  return `<tr><td colspan="${colspan}" class="empty-row">${escapeHtml(text)}</td></tr>`;
}
