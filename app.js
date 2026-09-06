const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "https://data-structure-five-view-lab.onrender.com";
const el = document.getElementById("backend-status");

async function checkBackend() {
  try {
    const r = await fetch(`${BACKEND_URL.replace(/\/$/, "")}/health`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json().catch(() => ({}));
    el.textContent = data.status ? `后端：已连接（${data.status}）` : "后端：已连接";
  } catch (e) {
    console.error("Backend health check failed:", e);
    el.textContent = "后端：连接失败";
  }
}

checkBackend();
