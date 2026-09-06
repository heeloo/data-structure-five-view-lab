(() => {
  if (typeof RendererRegistry === "undefined") return;

  function renderStack(snap) {
    const cells = snap.stack_array || [];
    const values = snap.values || {};
    if (!cells.length) {
      structureGraphEl.innerHTML = '<div class="pointer-empty">没有栈快照</div>';
      return;
    }

    const top = Number(values.top);
    const shell = document.createElement("div");
    shell.className = "stack-visual";
    shell.innerHTML = `
      <div class="linear-legend">
        <span><i class="legend-dot active"></i>栈内元素</span>
        <span><i class="legend-dot unused"></i>top 之外的物理槽位</span>
        <span><i class="legend-dot focus"></i>当前 top</span>
      </div>
    `;

    const body = document.createElement("div");
    body.className = "stack-body";
    const column = document.createElement("div");
    column.className = "stack-column";

    [...cells].reverse().forEach(cell => {
      const row = document.createElement("div");
      const stale = !cell.occupied && Number(cell.value) !== 0;
      row.className = `stack-row ${cell.occupied ? "is-occupied" : "is-unused"}${cell.index === top ? " is-top" : ""}`;
      row.innerHTML = `
        <span class="stack-index">[${cell.index}]</span>
        <span class="stack-value">${escapeHtml(cell.value)}</span>
        <span class="stack-address">${escapeHtml(shortAddress(cell.address))}</span>
        ${cell.index === top ? '<span class="stack-top-marker">top →</span>' : ""}
        ${stale ? '<span class="stack-stale">残留值 · 不在栈内</span>' : ""}
      `;
      column.appendChild(row);
    });

    body.appendChild(column);
    const meta = document.createElement("div");
    meta.className = "linear-meta";
    meta.innerHTML = `
      <div><strong>top</strong><span>${top}</span></div>
      <div><strong>size</strong><span>${Math.max(0, top + 1)}</span></div>
      <div><strong>push value</strong><span>${escapeHtml(values.value ?? "—")}</span></div>
      <div><strong>popped</strong><span>${Number(values.popped) < 0 ? "—" : escapeHtml(values.popped)}</span></div>
    `;
    body.appendChild(meta);
    shell.appendChild(body);
    structureGraphEl.replaceChildren(shell);
  }

  function renderCircularQueue(snap) {
    const cells = snap.queue || [];
    const values = snap.values || {};
    if (!cells.length) {
      structureGraphEl.innerHTML = '<div class="pointer-empty">没有循环队列快照</div>';
      return;
    }

    const front = Number(values.front);
    const rear = Number(values.rear);
    const size = Number(values.size);
    const capacity = Number(values.capacity || cells.length);
    const cx = 400, cy = 220, radius = 132, cellW = 104, cellH = 72;
    const points = new Map();
    const parts = [
      '<svg class="queue-ring" viewBox="0 0 800 440" role="img" aria-label="循环队列环形缓冲区">',
      '<defs><marker id="queue-front-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="queue-front-head"/></marker><marker id="queue-rear-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="queue-rear-head"/></marker></defs>',
      '<circle class="queue-orbit" cx="400" cy="220" r="132"/>',
    ];

    cells.forEach((cell, order) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * order) / cells.length;
      const x = cx + Math.cos(angle) * radius;
      const y = cy + Math.sin(angle) * radius;
      points.set(Number(cell.index), {x, y, angle});
      const classes = ["queue-cell", cell.occupied ? "is-occupied" : "is-unused"];
      if (Number(cell.index) === front) classes.push("is-front");
      if (Number(cell.index) === rear) classes.push("is-rear");
      const logical = Number(cell.logical_index) >= 0 ? `#${cell.logical_index}` : "空闲";
      parts.push(`
        <g class="${classes.join(" ")}">
          <rect x="${x - cellW / 2}" y="${y - cellH / 2}" width="${cellW}" height="${cellH}" rx="12"/>
          <text x="${x}" y="${y - 12}" text-anchor="middle" class="queue-index">[${cell.index}] · ${logical}</text>
          <text x="${x}" y="${y + 14}" text-anchor="middle" class="queue-value">${escapeHtml(cell.value)}</text>
          <text x="${x}" y="${y + 30}" text-anchor="middle" class="queue-address">${escapeHtml(shortAddress(cell.address))}</text>
        </g>
      `);
    });

    function addPointer(name, index, distance, marker, cssClass) {
      const point = points.get(index);
      if (!point) return;
      const labelX = cx + Math.cos(point.angle) * distance;
      const labelY = cy + Math.sin(point.angle) * distance;
      const endX = cx + Math.cos(point.angle) * (radius + 49);
      const endY = cy + Math.sin(point.angle) * (radius + 34);
      parts.push(`<text x="${labelX}" y="${labelY - 7}" text-anchor="middle" class="queue-pointer ${cssClass}">${name}=${index}</text>`);
      parts.push(`<line x1="${labelX}" y1="${labelY}" x2="${endX}" y2="${endY}" class="queue-pointer-line ${cssClass}" marker-end="url(#${marker})"/>`);
    }

    addPointer("front", front, 190, "queue-front-arrow", "front");
    addPointer("rear", rear, 205, "queue-rear-arrow", "rear");
    parts.push(`
      <text x="400" y="194" text-anchor="middle" class="queue-center-title">CIRCULAR QUEUE</text>
      <text x="400" y="221" text-anchor="middle" class="queue-center-value">size ${size} / ${capacity}</text>
      <text x="400" y="247" text-anchor="middle" class="queue-center-note">rear 指向下一次入队位置</text>
      ${rear === 0 ? '<text x="400" y="273" text-anchor="middle" class="queue-wrap-note">↻ rear 已回绕到下标 0</text>' : ""}
      <text x="28" y="420" class="queue-footer">enqueue=${escapeHtml(values.value ?? "—")} · dequeued=${Number(values.removed) < 0 ? "—" : escapeHtml(values.removed)}</text>
    </svg>`);
    structureGraphEl.innerHTML = parts.join("");
  }

  RendererRegistry.stack = renderStack;
  RendererRegistry["circular-queue"] = renderCircularQueue;
})();
