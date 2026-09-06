const BACKEND_URL = window.FIVE_VIEW_BACKEND_URL || "https://data-structure-five-view-lab.onrender.com";
const statusEl = document.getElementById("backend-status");
const runButton = document.getElementById("run-demo");
const demoSelect = document.getElementById("demo-select");
const demoTitleEl = document.getElementById("demo-title");
const demoSubtitleEl = document.getElementById("demo-subtitle");
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
let demos = [];

function api(path) { return `${BACKEND_URL.replace(/\/$/, "")}${path}`; }
function escapeHtml(text) { return String(text).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function isNullPointer(value) { return !value || ["(nil)","0x0","0","NULL"].includes(String(value)); }
function shortAddress(value) { if (isNullPointer(value)) return "NULL"; const s=String(value); return s.length>13?`${s.slice(0,6)}…${s.slice(-5)}`:s; }

async function checkBackend() {
  try {
    const r = await fetch(api("/health"), {cache:"no-store"});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json().catch(()=>({}));
    statusEl.textContent = data.version ? `后端：已连接 · v${data.version} · LLDB检测中` : "后端：已连接 · LLDB检测中";
    await loadDemos();
    try {
      const dr = await fetch(api("/api/debugger-capability"), {cache:"no-store"});
      const dbg = await dr.json();
      statusEl.textContent = dr.ok && dbg.available ? `后端：已连接 · v${data.version||"?"} · LLDB可用` : `后端：已连接 · v${data.version||"?"} · LLDB受限`;
    } catch (_) { statusEl.textContent = `后端：已连接 · v${data.version||"?"} · LLDB未确认`; }
  } catch (e) {
    console.error(e); statusEl.textContent = "后端：连接失败";
  }
}

async function loadDemos() {
  try {
    const r = await fetch(api("/api/demos"), {cache:"no-store"});
    const data = await r.json();
    if (!r.ok || !Array.isArray(data)) return;
    demos = data;
    demoSelect.innerHTML = data.map(d=>`<option value="${escapeHtml(d.id)}">${escapeHtml(d.title)}</option>`).join("");
    updateDemoHeader();
  } catch (e) { console.warn("demo list unavailable", e); }
}

function updateDemoHeader() {
  const demo = demos.find(d=>d.id===demoSelect.value);
  if (!demo) return;
  demoTitleEl.textContent = demo.title;
  demoSubtitleEl.textContent = demo.subtitle || "LLDB 源码级教学实验";
}

function resetViews() {
  stopPlayback(); snapshots=[]; runMeta={}; displaySource="";
  pseudoEl.textContent="等待运行…"; cEl.textContent="后端白名单源码"; storageEl.textContent="等待运行…";
  pointerEl.textContent="等待运行…"; pointerGraphEl.innerHTML='<div class="pointer-empty">等待运行…</div>';
  executionEl.textContent="等待运行…"; stdoutEl.textContent="stdout: （尚无输出）"; counterEl.textContent="0 / 0";
  slider.value=0; slider.max=0; slider.disabled=true; prevButton.disabled=true; nextButton.disabled=true; playButton.disabled=true;
}

function renderSource(activeLine) {
  const lines=displaySource.split("\n");
  cEl.innerHTML=lines.map((line,i)=>{const n=i+1;const cls=n===activeLine?"active-source-line":"";const mark=n===activeLine?"▶":" ";return `<span class="${cls}">${mark} ${String(n).padStart(2," ")} | ${escapeHtml(line)}</span>`;}).join("\n");
}

function renderPointerGraph(snap) {
  const heap=snap.heap||[], values=snap.values||{}, pointerNames=runMeta.pointer_names||["head"];
  if (!heap.length) { pointerGraphEl.innerHTML='<div class="pointer-empty">当前没有仍存活的堆结点</div>'; return; }
  const byAddress=new Map(heap.map(n=>[String(n.address),n])); const ordered=[]; const visited=new Set(); let cursor=values.head;
  while(!isNullPointer(cursor)&&byAddress.has(String(cursor))&&!visited.has(String(cursor))){const node=byAddress.get(String(cursor));ordered.push(node);visited.add(String(cursor));cursor=node.next;}
  for(const node of heap) if(!visited.has(String(node.address))) ordered.push(node);
  const width=Math.max(760,ordered.length*220+200), height=290, y=120, nodeW=140, nodeH=76, gap=80, startX=120;
  const indexByAddr=new Map(ordered.map((n,i)=>[String(n.address),i]));
  const pieces=[`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="链表指针关系动态图">`,'<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="svg-arrow-head"/></marker></defs>'];
  ordered.forEach((node,i)=>{
    const x=startX+i*(nodeW+gap); const isHead=String(node.address)===String(values.head);
    pieces.push(`<g class="heap-node ${isHead?"head-node":""}"><rect x="${x}" y="${y}" width="${nodeW}" height="${nodeH}" rx="12"/><line x1="${x+74}" y1="${y}" x2="${x+74}" y2="${y+nodeH}"/><text x="${x+37}" y="${y+30}" text-anchor="middle" class="svg-label">data</text><text x="${x+37}" y="${y+56}" text-anchor="middle" class="svg-value">${escapeHtml(node.data)}</text><text x="${x+107}" y="${y+30}" text-anchor="middle" class="svg-label">next</text><text x="${x+107}" y="${y+55}" text-anchor="middle" class="svg-address">${escapeHtml(shortAddress(node.next))}</text><text x="${x+nodeW/2}" y="${y+nodeH+24}" text-anchor="middle" class="svg-address">${escapeHtml(node.name)} @ ${escapeHtml(shortAddress(node.address))}</text></g>`);
    if(!isNullPointer(node.next)&&indexByAddr.has(String(node.next))){const j=indexByAddr.get(String(node.next));const tx=startX+j*(nodeW+gap);if(j>i)pieces.push(`<line class="svg-edge" x1="${x+nodeW}" y1="${y+38}" x2="${tx-10}" y2="${y+38}" marker-end="url(#arrow)"/>`);else pieces.push(`<path class="svg-edge" d="M ${x+nodeW-18} ${y+8} C ${x+nodeW+28} ${y-48}, ${tx-30} ${y-48}, ${tx+16} ${y+4}" marker-end="url(#arrow)"/>`);} else if(isNullPointer(node.next)){pieces.push(`<text x="${x+nodeW+28}" y="${y+44}" class="svg-null">NULL</text>`);}
  });
  pointerNames.forEach((name,idx)=>{
    const value=values[name]; if(isNullPointer(value)||!indexByAddr.has(String(value))) return;
    const i=indexByAddr.get(String(value)), x=startX+i*(nodeW+gap)+nodeW/2, top=32+idx*30, secondary=idx>0;
    pieces.push(`<text x="${x}" y="${top}" text-anchor="middle" class="svg-pointer-name ${secondary?"secondary":""}">${escapeHtml(name)}</text>`);
    pieces.push(`<line class="${secondary?"svg-secondary-edge":"svg-head-edge"}" x1="${x}" y1="${top+8}" x2="${x}" y2="${y-8}" marker-end="url(#arrow)"/>`);
  });
  pieces.push("</svg>"); pointerGraphEl.innerHTML=pieces.join("");
}

function updateControls(index){const enabled=snapshots.length>0;prevButton.disabled=!enabled||index<=0;nextButton.disabled=!enabled||index>=snapshots.length-1;playButton.disabled=snapshots.length<=1;}
function renderSnapshot(index){if(!snapshots.length)return;const snap=snapshots[index],dbg=snap.debugger||{};slider.value=index;counterEl.textContent=`${index+1} / ${snapshots.length}`;noteEl.textContent=snap.step;renderSource(dbg.display_source_line||0);
  const stackLines=Object.entries(snap.stack||{}).map(([k,v])=>`${k.padEnd(10)} ${v}`).join("\n");const valueLines=Object.entries(snap.values||{}).map(([k,v])=>`${k.padEnd(10)} -> ${v}`).join("\n");const heapLines=(snap.heap||[]).map(n=>`${n.name}@${n.address}\n  data=${n.data}\n  next=${n.next}`).join("\n\n");storageEl.textContent=`MAIN STACK VARIABLES\n${stackLines||"(empty)"}\n\nHEAP\n${heapLines||"(empty)"}`;
  const edges=(snap.pointer_edges||[]).map(e=>`${e.from}  ──▶  ${e.to}`).join("\n");pointerEl.textContent=`${valueLines}\n\n${edges||"暂无指针边"}`;renderPointerGraph(snap);
  const engineLine=runMeta.execution_engine?.startsWith("lldb")?`LLDB SOURCE BREAKPOINT ${dbg.breakpoint_hit||index+1}/${runMeta.lldb_breakpoint_hits||snapshots.length}`:`ENGINE ${runMeta.execution_engine||"unknown"}`;const sourceLine=dbg.display_source_line?`C LINE ${dbg.display_source_line}: ${dbg.display_source_text||""}`:"C LINE: 未确认";const frameLine=dbg.frame_variables_read?"frame variables: 已读取":"frame variables: 未确认";executionEl.textContent=`${engineLine}\n${sourceLine}\n${frameLine}\n\nSTEP ${index+1}\n${snap.step}\n\n当前存活堆结点数: ${(snap.heap||[]).length}`;updateControls(index);
}

function stopPlayback(){if(playTimer)clearInterval(playTimer);playTimer=null;playButton.textContent="▶ 自动播放";}
function moveSnapshot(delta){if(!snapshots.length)return;renderSnapshot(Math.max(0,Math.min(snapshots.length-1,Number(slider.value)+delta)));}
function togglePlayback(){if(playTimer){stopPlayback();return;}if(Number(slider.value)>=snapshots.length-1)renderSnapshot(0);playButton.textContent="Ⅱ 暂停";playTimer=setInterval(()=>{const current=Number(slider.value);if(current>=snapshots.length-1){stopPlayback();return;}renderSnapshot(current+1);},Number(speedSelect.value));}

async function runDemo(){stopPlayback();runButton.disabled=true;demoSelect.disabled=true;runButton.textContent="正在 Clang + LLDB 源码级调试…";try{const r=await fetch(api("/api/run-demo"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({demo_id:demoSelect.value})});const data=await r.json();if(!r.ok)throw new Error(JSON.stringify(data));pseudoEl.textContent=(data.pseudo||[]).join("\n");displaySource=data.display_source||"";snapshots=data.snapshots||[];runMeta=data;demoTitleEl.textContent=data.title||demoTitleEl.textContent;demoSubtitleEl.textContent=data.subtitle||demoSubtitleEl.textContent;renderSource(0);const engineText=data.execution_engine?.startsWith("lldb")?`LLDB 源码级驱动 · 断点 ${data.lldb_breakpoint_hits||0} 次 · frame ${data.lldb_frame_reads||0} 组`:`回退模式：${data.execution_engine||"unknown"}`;stdoutEl.textContent=`${engineText}\nstdout: ${data.stdout||"（无输出）"}`;noteEl.textContent=[data.storage_semantics,data.address_note].filter(Boolean).join(" ")||"运行完成";slider.disabled=snapshots.length<=1;slider.min=0;slider.max=Math.max(0,snapshots.length-1);slider.value=0;if(snapshots.length)renderSnapshot(0);}catch(e){console.error(e);executionEl.textContent=`运行失败\n${e.message}`;}finally{runButton.disabled=false;demoSelect.disabled=false;runButton.textContent="再次运行当前算法";}}

slider.addEventListener("input",()=>{stopPlayback();renderSnapshot(Number(slider.value));});prevButton.addEventListener("click",()=>{stopPlayback();moveSnapshot(-1);});nextButton.addEventListener("click",()=>{stopPlayback();moveSnapshot(1);});playButton.addEventListener("click",togglePlayback);speedSelect.addEventListener("change",()=>{if(playTimer){stopPlayback();togglePlayback();}});runButton.addEventListener("click",runDemo);demoSelect.addEventListener("change",()=>{updateDemoHeader();resetViews();});checkBackend();
