const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "https://data-structure-five-view-lab.onrender.com";
const statusEl = document.getElementById("backend-status");
const runButton = document.getElementById("run-demo");
const pseudoEl = document.getElementById("pseudo-output");
const cEl = document.getElementById("c-output");
const storageEl = document.getElementById("storage-output");
const pointerEl = document.getElementById("pointer-output");
const executionEl = document.getElementById("execution-output");
const stdoutEl = document.getElementById("stdout-output");
const slider = document.getElementById("snapshot-slider");
const counterEl = document.getElementById("snapshot-counter");
const noteEl = document.getElementById("snapshot-note");

let snapshots = [];
let runMeta = {};

function api(path) {
  return `${BACKEND_URL.replace(/\/$/, "")}${path}`;
}

async function checkBackend() {
  try {
    const r = await fetch(api("/health"), { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json().catch(() => ({}));
    statusEl.textContent = data.version
      ? `后端：已连接 · v${data.version} · LLDB检测中`
      : "后端：已连接 · LLDB检测中";

    try {
      const dr = await fetch(api("/api/debugger-capability"), { cache: "no-store" });
      const dbg = await dr.json();
      if (dr.ok && dbg.available) {
        statusEl.textContent = `后端：已连接 · v${data.version || "?"} · LLDB可用`;
      } else {
        statusEl.textContent = `后端：已连接 · v${data.version || "?"} · LLDB受限`;
      }
    } catch (debugError) {
      console.warn("Debugger capability check failed:", debugError);
      statusEl.textContent = `后端：已连接 · v${data.version || "?"} · LLDB未确认`;
    }
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
  storageEl.textContent = `MAIN STACK VARIABLES\n${stackLines || "(empty)"}\n\nHEAP\n${heapLines || "(empty)"}`;

  const edges = (snap.pointer_edges || [])
    .map(edge => `${edge.from}  ──▶  ${edge.to}`)
    .join("\n");
  pointerEl.textContent = `${valueLines}\n\n${edges || "暂无指针边"}`;

  const dbg = snap.debugger || {};
  const engineLine = runMeta.execution_engine === "lldb"
    ? `LLDB BREAKPOINT ${dbg.hit || index + 1}/${runMeta.lldb_breakpoint_hits || snapshots.length}`
    : `ENGINE ${runMeta.execution_engine || "unknown"}`;
  const frameLine = dbg.frame_variables_read ? "frame variable: 已读取" : "frame variable: 未确认";
  executionEl.textContent = `${engineLine}\n${frameLine}\n\nSTEP ${index + 1}\n${snap.step}\n\n当前堆结点数: ${(snap.heap || []).length}`;
}

async function runDemo() {
  runButton.disabled = true;
  runButton.textContent = "正在 Clang + LLDB 调试运行…";
  try {
    const r = await fetch(api("/api/run-demo"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo_id: "linked-list-insert" }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(data));

    pseudoEl.textContent = (data.pseudo || []).join("\n");
    cEl.textContent = data.display_source || "后端白名单源码";
    snapshots = data.snapshots || [];
    runMeta = data;

    const engineText = data.execution_engine === "lldb"
      ? `LLDB 驱动 · 断点命中 ${data.lldb_breakpoint_hits || 0} 次 · frame read ${data.lldb_frame_reads || 0} 次`
      : `回退模式：${data.execution_engine || "unknown"}`;
    stdoutEl.textContent = `${engineText}\nstdout: ${data.stdout || "（无输出）"}`;
    noteEl.textContent = [data.storage_semantics, data.address_note].filter(Boolean).join(" ") || "运行完成";

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
    runButton.textContent = "再次运行 LLDB 演示";
  }
}

slider.addEventListener("input", () => renderSnapshot(Number(slider.value)));
runButton.addEventListener("click", runDemo);
checkBackend();
