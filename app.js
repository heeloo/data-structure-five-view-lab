const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "https://data-structure-five-view-lab.onrender.com";
const statusEl = document.getElementById("backend-status");
const runButton = document.getElementById("run-demo");
const pseudoEl = document.getElementById("pseudo-output");
const cEl = document.getElementById("c-output");
const storageEl = document.getElementById("storage-output");
const pointerEl = document.getElementById("pointer-output");
const pointerGraphEl = document.getElementById("pointer-graph");
const executionEl = document.getElementById("execution-output");
const stdoutEl = document.getElementById("stdout-output");
const slider = document.getElementById("snapshot-slider");
const counterEl = document.getElementById("snapshot-counter");
const noteEl = document.getElementById("snapshot-note");
const prevButton = document.getElementById("prev-step");
const nextButton = document.getElementById("next-step");
const playButton = document.getElementById("play-step");
const speedSelect = document.getElementById("play-speed");

let snapshots = [];
let runMeta = {};
let displaySource = "";
let playTimer = null;

function api(path) {
  return `${BACKEND_URL.replace(/\/$/, "")}${path}`;
}

async function checkBackend() {
  try {
    const r = await fetch(api("/health"), { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json().catch(() => ({}));
    statusEl.textContent = data.version ? `后端：已连接 · v${data.version} · LLDB检测中` : "后端：已连接 · LLDB检测中";
    try {
      const dr = await fetch(api("/api/debugger-capability"), { cache: "no-store" });
      const dbg = await dr.json();
      statusEl.textContent = dr.ok && dbg.available
        ? `后端：已连接 · v${data.version || "?"} · LLDB可用`
        : `后端：已连接 · v${data.version || "?"} · LLDB受限`;
    } catch (debugError) {
      console.warn("Debugger capability check failed:", debugError);
      statusEl.textContent = `后端：已连接 · v${data.version || "?"} · LLDB未确认`;
    }
  } catch (e) {
    console.error("Backend health check failed:", e);
    statusEl.textContent = "后端：连接失败";
  }
}

function escapeHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderSource(activeLine) {
  const lines = displaySource.split("\n");
  cEl.innerHTML = lines.map((line, i) => {
    const n = i + 1;
    const safe = escapeHtml(line);
    const mark = n === activeLine ? "▶" : " ";
    const cls = n === activeLine ? "active-source-line" : "";
    return `<span class="${cls}">${mark} ${String(n).padStart(2, " ")} | ${safe}</span>`;
  }).join("\n");
}

function isNullPointer(value) {
  return !value || value === "(nil)" || value === "0x0" || value === "0" || value === "NULL";
}

function shortAddress(value) {
  if (isNullPointer(value)) return "NULL";
  const s = String(value);
  return s.length > 13 ? `${s.slice(0, 6)}…${s.slice(-5)}` : s;
}

function renderPointerGraph(snap) {
  const heap = snap.heap || [];
  const values = snap.values || {};
  if (!heap.length) {
    pointerGraphEl.innerHTML = '<div class="pointer-empty">当前没有堆结点</div>';
    return;
  }

  const byAddress = new Map(heap.map(node => [String(node.address), node]));
  const ordered = [];
  const visited = new Set();
  let cursor = values.head;
  while (!isNullPointer(cursor) && byAddress.has(String(cursor)) && !visited.has(String(cursor))) {
    const node = byAddress.get(String(cursor));
    ordered.push(node);
    visited.add(String(cursor));
    cursor = node.next;
  }
  for (const node of heap) {
    if (!visited.has(String(node.address))) ordered.push(node);
  }

  const width = Math.max(520, ordered.length * 190 + 150);
  const height = 250;
  const y = 105;
  const nodeW = 130;
  const nodeH = 72;
  const gap = 60;
  const startX = 105;

  const indexByAddr = new Map(ordered.map((node, i) => [String(node.address), i]));
  const pieces = [
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="链表指针关系动态图">`,
    '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="svg-arrow-head"/></marker></defs>'
  ];

  ordered.forEach((node, i) => {
    const x = startX + i * (nodeW + gap);
    pieces.push(`<g class="heap-node ${String(node.address) === String(values.head) ? "head-node" : ""}">`);
    pieces.push(`<rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="12"/>`);
    pieces.push(`<line x1="${x + 70}" y1="${y}" x2="${x + 70}" y2="${y + nodeH}"/>`);
    pieces.push(`<text x="${x + 35}" y="${y + 29}" text-anchor="middle" class="svg-label">data</text>`);
    pieces.push(`<text x="${x + 35}" y="${y + 52}" text-anchor="middle" class="svg-value">${escapeHtml(node.data)}</text>`);
    pieces.push(`<text x="${x + 100}" y="${y + 29}" text-anchor="middle" class="svg-label">next</text>`);
    pieces.push(`<text x="${x + 100}" y="${y + 52}" text-anchor="middle" class="svg-address">${escapeHtml(shortAddress(node.next))}</text>`);
    pieces.push(`<text x="${x + nodeW / 2}" y="${y + nodeH + 21}" text-anchor="middle" class="svg-address">${escapeHtml(node.name)} @ ${escapeHtml(shortAddress(node.address))}</text>`);
    pieces.push('</g>');

    if (!isNullPointer(node.next) && indexByAddr.has(String(node.next))) {
      const j = indexByAddr.get(String(node.next));
      const tx = startX + j * (nodeW + gap);
      const fromX = x + nodeW;
      const toX = tx;
      if (j > i) {
        pieces.push(`<line class="svg-edge" x1="${fromX}" y1="${y + 36}" x2="${toX - 8}" y2="${y + 36}" marker-end="url(#arrow)"/>`);
      } else {
        pieces.push(`<path class="svg-edge" d="M ${fromX - 18} ${y + 8} C ${fromX + 25} ${y - 45}, ${toX - 25} ${y - 45}, ${toX + 15} ${y + 4}" marker-end="url(#arrow)"/>`);
      }
    } else if (isNullPointer(node.next)) {
      pieces.push(`<text x="${x + nodeW + 24}" y="${y + 42}" class="svg-null">NULL</text>`);
    }
  });

  if (!isNullPointer(values.head) && indexByAddr.has(String(values.head))) {
    const i = indexByAddr.get(String(values.head));
    const x = startX + i * (nodeW + gap) + nodeW / 2;
    pieces.push(`<text x="${x}" y="34" text-anchor="middle" class="svg-pointer-name">head</text>`);
    pieces.push(`<line class="svg-head-edge" x1="${x}" y1="45" x2="${x}" y2="${y - 8}" marker-end="url(#arrow)"/>`);
  }

  if (!isNullPointer(values.s) && indexByAddr.has(String(values.s)) && String(values.s) !== String(values.head)) {
    const i = indexByAddr.get(String(values.s));
    const x = startX + i * (nodeW + gap) + nodeW / 2;
    pieces.push(`<text x="${x}" y="34" text-anchor="middle" class="svg-pointer-name secondary">s</text>`);
    pieces.push(`<line class="svg-secondary-edge" x1="${x}" y1="45" x2="${x}" y2="${y - 8}" marker-end="url(#arrow)"/>`);
  }

  pieces.push('</svg>');
  pointerGraphEl.innerHTML = pieces.join("");
}

function updateControls(index) {
  const enabled = snapshots.length > 0;
  prevButton.disabled = !enabled || index <= 0;
  nextButton.disabled = !enabled || index >= snapshots.length - 1;
  playButton.disabled = snapshots.length <= 1;
}

function renderSnapshot(index) {
  if (!snapshots.length) return;
  const snap = snapshots[index];
  const dbg = snap.debugger || {};
  slider.value = index;
  counterEl.textContent = `${index + 1} / ${snapshots.length}`;
  noteEl.textContent = snap.step;
  renderSource(dbg.display_source_line || 0);

  const stackLines = Object.entries(snap.stack || {}).map(([k, v]) => `${k.padEnd(10)} ${v}`).join("\n");
  const valueLines = Object.entries(snap.values || {}).map(([k, v]) => `${k.padEnd(10)} -> ${v}`).join("\n");
  const heapLines = (snap.heap || []).map(node => `${node.name}@${node.address}\n  data=${node.data}\n  next=${node.next}`).join("\n\n");
  storageEl.textContent = `MAIN STACK VARIABLES\n${stackLines || "(empty)"}\n\nHEAP\n${heapLines || "(empty)"}`;

  const edges = (snap.pointer_edges || []).map(edge => `${edge.from}  ──▶  ${edge.to}`).join("\n");
  pointerEl.textContent = `${valueLines}\n\n${edges || "暂无指针边"}`;
  renderPointerGraph(snap);

  const engineLine = runMeta.execution_engine?.startsWith("lldb")
    ? `LLDB SOURCE BREAKPOINT ${dbg.breakpoint_hit || index + 1}/${runMeta.lldb_breakpoint_hits || snapshots.length}`
    : `ENGINE ${runMeta.execution_engine || "unknown"}`;
  const sourceLine = dbg.display_source_line ? `C LINE ${dbg.display_source_line}: ${dbg.display_source_text || ""}` : "C LINE: 未确认";
  const frameLine = dbg.frame_variables_read ? "frame variable head/a/s: 已读取" : "frame variable: 未确认";
  executionEl.textContent = `${engineLine}\n${sourceLine}\n${frameLine}\n\nSTEP ${index + 1}\n${snap.step}\n\n当前堆结点数: ${(snap.heap || []).length}`;
  updateControls(index);
}

function stopPlayback() {
  if (playTimer) clearInterval(playTimer);
  playTimer = null;
  playButton.textContent = "▶ 自动播放";
}

function moveSnapshot(delta) {
  if (!snapshots.length) return;
  const next = Math.max(0, Math.min(snapshots.length - 1, Number(slider.value) + delta));
  renderSnapshot(next);
}

function togglePlayback() {
  if (playTimer) {
    stopPlayback();
    return;
  }
  if (Number(slider.value) >= snapshots.length - 1) renderSnapshot(0);
  playButton.textContent = "Ⅱ 暂停";
  playTimer = setInterval(() => {
    const current = Number(slider.value);
    if (current >= snapshots.length - 1) {
      stopPlayback();
      return;
    }
    renderSnapshot(current + 1);
  }, Number(speedSelect.value));
}

async function runDemo() {
  stopPlayback();
  runButton.disabled = true;
  runButton.textContent = "正在 Clang + LLDB 源码级调试…";
  try {
    const r = await fetch(api("/api/run-demo"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo_id: "linked-list-insert" }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(data));

    pseudoEl.textContent = (data.pseudo || []).join("\n");
    displaySource = data.display_source || "";
    snapshots = data.snapshots || [];
    runMeta = data;
    renderSource(0);

    const engineText = data.execution_engine?.startsWith("lldb")
      ? `LLDB 源码级驱动 · 断点 ${data.lldb_breakpoint_hits || 0} 次 · frame ${data.lldb_frame_reads || 0} 组`
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

slider.addEventListener("input", () => {
  stopPlayback();
  renderSnapshot(Number(slider.value));
});
prevButton.addEventListener("click", () => { stopPlayback(); moveSnapshot(-1); });
nextButton.addEventListener("click", () => { stopPlayback(); moveSnapshot(1); });
playButton.addEventListener("click", togglePlayback);
speedSelect.addEventListener("change", () => {
  if (playTimer) {
    stopPlayback();
    togglePlayback();
  }
});
runButton.addEventListener("click", runDemo);
window.fiveViewPrev = () => moveSnapshot(-1);
window.fiveViewNext = () => moveSnapshot(1);
checkBackend();
