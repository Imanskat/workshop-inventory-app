// app.js — لایه‌ی مشترک ارتباط با API (Apps Script) برای همه‌ی صفحات

const API_BASE = "https://script.google.com/macros/s/AKfycbypLxCtrFW8zGrwiJpVLwhBF0B9FSHz_k-2AkxsqFl4aRTWfjsIRv3_QM-aw8rqKNub/exec";

async function api(action, params = {}) {
  const qs = new URLSearchParams({ action, ...params });
  const res = await fetch(`${API_BASE}?${qs.toString()}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || "خطای نامشخص از سرور");
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
