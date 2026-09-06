const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "";
const el = document.getElementById("backend-status");

async function checkBackend() {
  if (!BACKEND_URL) {
    el.textContent = "后端：等待 Render URL";
    return;
  }
  try {
    const r = await fetch(`${BACKEND_URL.replace(/\/$/, "")}/health`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    el.textContent = "后端：已连接";
  } catch (e) {
    el.textContent = "后端：连接失败";
  }
}

checkBackend();
