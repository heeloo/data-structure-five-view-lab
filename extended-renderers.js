(() => {
  if (typeof RendererRegistry === "undefined") return;

  const card = (label, value, extra="") => `<span class="ext-card ${extra}"><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b></span>`;

  function renderHeap(snap) {
    const cells=(snap.array||[]).filter(x=>x.active),v=snap.values||{};
    const levels=[];cells.forEach((x,i)=>{const d=Math.floor(Math.log2(i+1));(levels[d]??=[]).push(x);});
    structureGraphEl.innerHTML=`<div class="ext-visual"><div class="ext-legend">MAX HEAP · parent=(i−1)/2 · children=2i+1,2i+2</div><div class="heap-levels">${levels.map((level,d)=>`<div class="heap-level"><em>level ${d}</em>${level.map(x=>card(`[${x.index}]`,x.value,x.index===Number(v.current)?"focus":"")).join("")}</div>`).join("")}</div><div class="ext-array-row">${(snap.array||[]).map(x=>card(x.index,x.value,`${x.active?"active":"unused"} ${x.index===Number(v.current)?"focus":""}`)).join("")}</div><div class="ext-meta">size ${v.size}/${v.capacity} · current ${v.current} · parent ${v.parent} · ${Number(v.operation)===1?"PUSH":Number(v.operation)===2?"EXTRACT-MAX":"BUILD"}</div></div>`;
  }

  function renderHash(snap) {
    const v=snap.values||{},names=["EMPTY","OCCUPIED","TOMBSTONE"];
    structureGraphEl.innerHTML=`<div class="ext-visual"><div class="ext-legend">${Number(v.mode)===2?"QUADRATIC h+i²":"LINEAR h+i"} · key=${v.key} · probe=${v.probe}</div><div class="hash-grid">${(snap.hash||[]).map(x=>`<div class="hash-slot state-${x.state} ${x.index===Number(v.probe)?"focus":""}"><small>[${x.index}] ${names[x.state]}</small><b>${x.state===1?x.key:x.state===2?"×":"—"}</b><span>${escapeHtml(shortAddress(x.address))}</span></div>`).join("")}</div><div class="ext-meta">length ${v.length}/${v.capacity} · ${Number(v.status)===1?"发生冲突":Number(v.status)===2?"墓碑删除":"状态稳定"}</div></div>`;
  }

  function renderDsu(snap) {
    const v=snap.values||{},items=snap.dsu||[];
    structureGraphEl.innerHTML=`<div class="ext-visual"><div class="ext-legend">UNION-FIND · parent + rank</div><div class="dsu-grid"><div class="dsu-label">element</div>${items.map(x=>card("i",x.index,x.index===Number(v.current)?"focus":"")).join("")}<div class="dsu-label">parent</div>${items.map(x=>card("p",x.parent,x.parent===x.index?"root":"")).join("")}<div class="dsu-label">rank</div>${items.map(x=>card("r",x.rank)).join("")}</div><div class="dsu-paths">${items.map(x=>`<span>${x.index}${x.parent===x.index?" ROOT":` → ${x.parent}`}</span>`).join("")}</div><div class="ext-meta">${Number(v.operation)===2?"FIND + PATH COMPRESSION":"UNION BY RANK"} · root_a=${v.root_a} · root_b=${v.root_b}</div></div>`;
  }

  function renderTrie(snap) {
    const trie=snap.trie||{},nodes=trie.nodes||[],edges=trie.edges||[],v=snap.values||{};
    const children=new Map(nodes.map(n=>[n.id,[]]));edges.forEach(e=>children.get(e.from)?.push(e));
    const layer=new Map([[0,0]]);for(let pass=0;pass<nodes.length;pass++)edges.forEach(e=>layer.set(e.to,(layer.get(e.from)||0)+1));
    structureGraphEl.innerHTML=`<div class="ext-visual"><div class="ext-legend">TRIE · character edges · terminal markers</div><div class="trie-levels">${[...new Set([...layer.values()])].sort().map(d=>`<div class="trie-level"><em>depth ${d}</em>${nodes.filter(n=>layer.get(n.id)===d).map(n=>`<span class="trie-node ${n.id===Number(v.current)?"focus":""} ${n.terminal?"terminal":""}"><b>${n.id===0?"ROOT":escapeHtml(n.char)}</b><small>#${n.id} ${n.terminal?"· WORD":""}</small><small>${escapeHtml(shortAddress(n.address))}</small></span>`).join("")}</div>`).join("")}</div><div class="trie-edges">${edges.map(e=>`<span>#${e.from} ─${escapeHtml(e.char)}→ #${e.to}</span>`).join("")}</div><div class="ext-meta">nodes=${v.node_count} · current=#${v.current} · char_index=${v.char_index} · ${Number(v.status)?"MATCH / TERMINAL":"TRAVERSING"}</div></div>`;
  }

  RendererRegistry["binary-heap"]=renderHeap;
  RendererRegistry["hash-table"]=renderHash;
  RendererRegistry["union-find"]=renderDsu;
  RendererRegistry.trie=renderTrie;
})();
