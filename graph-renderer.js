(() => {
  if (typeof RendererRegistry === "undefined") return;

  const graphPositions = {
    0: {x: 450, y: 76},
    1: {x: 245, y: 210},
    2: {x: 655, y: 210},
    3: {x: 300, y: 370},
    4: {x: 600, y: 370},
  };

  function renderGraph(snap) {
    const graph = snap.graph || {};
    const vertices = graph.vertices || [];
    const edges = graph.edges || [];
    const values = snap.values || {};
    const mode = runMeta.graph_mode || snap.model?.visualization?.mode || "bfs";
    if (!vertices.length) {
      structureGraphEl.innerHTML = '<div class="pointer-empty">没有图快照</div>';
      return;
    }

    const labels = new Map(vertices.map(vertex => [Number(vertex.id), vertex.label]));
    const parents = new Set(vertices.filter(vertex => Number(vertex.parent) >= 0).map(vertex => `${Math.min(vertex.id, vertex.parent)}-${Math.max(vertex.id, vertex.parent)}`));
    const svg = ['<svg class="graph-canvas" viewBox="0 0 900 450" role="img" aria-label="图遍历结构图">'];

    edges.forEach(edge => {
      const from = graphPositions[edge.from], to = graphPositions[edge.to];
      if (!from || !to) return;
      const key = `${Math.min(edge.from, edge.to)}-${Math.max(edge.from, edge.to)}`;
      svg.push(`<line class="graph-edge${parents.has(key) ? " is-tree-edge" : ""}" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"/>`);
    });

    vertices.forEach(vertex => {
      const pos = graphPositions[vertex.id];
      if (!pos) return;
      const state = Number(vertex.state);
      const classes = ["graph-node", state === 0 ? "is-unseen" : state === 1 ? (mode === "bfs" ? "is-frontier" : "is-active") : (mode === "bfs" ? "is-visited" : "is-finished")];
      if (Number(vertex.id) === Number(values.current)) classes.push("is-current");
      const stateText = state === 0 ? "unseen" : state === 1 ? (mode === "bfs" ? "frontier" : "active") : (mode === "bfs" ? "visited" : "finished");
      svg.push(`<g class="${classes.join(" ")}">`);
      svg.push(`<circle cx="${pos.x}" cy="${pos.y}" r="39"/>`);
      svg.push(`<text class="graph-node-label" x="${pos.x}" y="${pos.y + 5}" text-anchor="middle">${escapeHtml(vertex.label)}</text>`);
      svg.push(`<text class="graph-node-state" x="${pos.x}" y="${pos.y + 58}" text-anchor="middle">${stateText}</text>`);
      svg.push(`<text class="graph-node-address" x="${pos.x}" y="${pos.y + 72}" text-anchor="middle">${escapeHtml(shortAddress(vertex.address))}</text>`);
      if (Number(vertex.metric) >= 0) svg.push(`<text class="graph-node-metric" x="${pos.x + 31}" y="${pos.y - 27}" text-anchor="middle">${mode === "bfs" ? "d" : "z"}=${vertex.metric}</text>`);
      if (Number(vertex.id) === Number(values.current)) svg.push(`<text class="graph-current-label" x="${pos.x}" y="${pos.y - 55}" text-anchor="middle">current</text>`);
      svg.push('</g>');
    });
    svg.push('</svg>');

    const activeItems = (snap.worklist?.items || []).filter(item => item.active);
    const worklistName = mode === "bfs" ? "BFS QUEUE" : "DFS RECURSION STACK";
    const worklist = activeItems.length
      ? activeItems.map((item, index) => `<span class="graph-work-item${index === 0 ? " first" : ""}${index === activeItems.length - 1 ? " last" : ""}">${escapeHtml(labels.get(Number(item.vertex)) ?? "?")}<small>slot ${item.slot}</small></span>`).join('<i>→</i>')
      : '<span class="graph-work-empty">空</span>';
    const order = (snap.order || []).map(id => `<span>${escapeHtml(labels.get(Number(id)) ?? "?")}</span>`).join('<i>→</i>') || '<em>尚未访问</em>';
    const callStack = snap.debugger?.call_stack || [];

    const shell = document.createElement("div");
    shell.className = `graph-visual mode-${mode}`;
    shell.innerHTML = `
      <div class="graph-legend">
        <span><i class="graph-swatch unseen"></i>unseen</span>
        <span><i class="graph-swatch pending"></i>${mode === "bfs" ? "frontier" : "active"}</span>
        <span><i class="graph-swatch done"></i>${mode === "bfs" ? "visited" : "finished"}</span>
        <span><i class="graph-swatch current"></i>current</span>
        <span><i class="graph-line-swatch"></i>遍历生成树</span>
      </div>
      ${svg.join("")}
      <div class="graph-runtime">
        <section class="graph-worklist">
          <strong>${worklistName}</strong>
          <div>${worklist}</div>
          <small>${mode === "bfs" ? `front=${values.front} · rear=${values.rear}` : `stack_size=${values.stack_size}`}</small>
        </section>
        <section class="graph-order">
          <strong>VISIT ORDER</strong>
          <div>${order}</div>
          <small>visited=${values.visit_count}</small>
        </section>
        ${mode === "dfs" ? `<section class="graph-debug-stack"><strong>LLDB CALL STACK</strong><div>${callStack.map(frame => `<span class="graph-frame ${frame.function === "dfs" ? "recursive" : ""}">#${frame.index} ${escapeHtml(frame.function)}</span>`).join('<i>←</i>')}</div></section>` : ""}
      </div>
    `;
    structureGraphEl.replaceChildren(shell);
  }

  RendererRegistry.graph = renderGraph;
})();
