const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "https://data-structure-five-view-lab.onrender.com";
const statusEl = document.getElementById("backend-status");
const runButton = document.getElementById("run-demo");
const pseudoEl = document.getElementById("pseudo-output");
const storageEl = document.getElementById("storage-output");
const pointerEl = document.getElementById("pointer-output");
const executionEl = document.getElementById("execution-output");
const stdoutEl = document.getElementById("stdout-output");
const slider = document.getElementById("snapshot-slider");
const counterEl = document.getElementById("snapshot-counter");
const noteEl = document.getElementById("snapshot-note");

let snapshots = [];

function api(path) {
  return `${BACKEND_URL.replace(/\/$/, "")}${path}`;
}

async function checkBackend() {
  try {
    const r = await fetch(api("/health"), { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json().catch(() => ({}));
    statusEl.textContent = data.version
      ? `后端：已连接 · v${data.version}`
      : "后端：已连接";
  } catch (e) {
    console.error("Backend health check failed:", e);
    statusEl.textContent = "后端：连接失败";
  }
}

function renderSnapshot(index) {
  if (!snapshots.length) return;
  const snap = snapshots[index];
  counterEl.textContent = `${index + 1} / ${snapshots.length}`;
  noteEl.textContent = snap.step;

  const stackLines = Object.entries(snap.stack || {})
    .map(([k, v]) => `${k.padEnd(10)} ${v}`)
    .join("\n");
  const valueLines = Object.entries(snap.values || {})
    .map(([k, v]) => `${k.padEnd(10)} -> ${v}`)
    .join("\n");
  const heapLines = (snap.heap || [])
    .map(node => `${node.name}@${node.address}\n  data=${node.data}\n  next=${node.next}`)
    .join("\n\n");
  storageEl.textContent = `STACK\n${stackLines || "(empty)"}\n\nHEAP\n${heapLines || "(empty)"}`;

  const edges = (snap.pointer_edges || [])
    .map(edge => `${edge.from}  ──▶  ${edge.to}`)
    .join("\n");
  pointerEl.textContent = `${valueLines}\n\n${edges || "暂无指针边"}`;

  executionEl.textContent = `STEP ${index + 1}\n${snap.step}\n\n当前堆结点数: ${(snap.heap || []).length}`;
}

async function runDemo() {
  runButton.disabled = true;
  runButton.textContent = "正在 Clang 编译并运行…";
  try {
    const r = await fetch(api("/api/run-demo"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo_id: "linked-list-insert" }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(data));

    pseudoEl.textContent = (data.pseudo || []).join("\n");
    snapshots = data.snapshots || [];
    stdoutEl.textContent = `stdout: ${data.stdout || "（无输出）"}`;
    noteEl.textContent = data.address_note || "运行完成";

    slider.disabled = snapshots.length <= 1;
    slider.min = 0;
    slider.max = Math.max(0, snapshots.length - 1);
    slider.value = 0;
    if (snapshots.length) renderSnapshot(0);
  } catch (e) {
    console.error(e);
    executionEl.textContent = `运行失败\n${e.message}`;
  } finally {
    runButton.disabled = false;
    runButton.textContent = "再次运行真实 C 演示";
  }
}

slider.addEventListener("input", () => renderSnapshot(Number(slider.value)));
runButton.addEventListener("click", runDemo);
checkBackend();
