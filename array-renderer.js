(() => {
  if (typeof RendererRegistry === "undefined") return;

  function renderArrayVisual(snap) {
    const cells = snap.array || [];
    const values = snap.values || {};
    if (!cells.length) {
      structureGraphEl.innerHTML = '<div class="pointer-empty">没有数组快照</div>';
      return;
    }

    const length = Number(values.length ?? 0);
    const capacity = Number(values.capacity ?? cells.length);
    const pos = Number(values.pos);
    const i = Number(values.i);

    const shell = document.createElement("div");
    shell.className = "array-visual";

    const legend = document.createElement("div");
    legend.className = "array-legend";
    legend.innerHTML = `
      <span><i class="legend-dot active"></i>有效元素</span>
      <span><i class="legend-dot unused"></i>空闲容量</span>
      <span><i class="legend-dot focus"></i>当前操作位置</span>
    `;
    shell.appendChild(legend);

    const track = document.createElement("div");
    track.className = "array-track";

    cells.forEach(cell => {
      const card = document.createElement("div");
      const isFocus = cell.index === i || cell.index === pos;
      card.className = `array-dom-cell ${cell.active ? "is-active" : "is-unused"}${isFocus ? " is-focus" : ""}`;

      const index = document.createElement("div");
      index.className = "array-dom-index";
      index.textContent = `[${cell.index}]`;

      const value = document.createElement("div");
      value.className = "array-dom-value";
      value.textContent = cell.value;

      const address = document.createElement("div");
      address.className = "array-dom-address";
      address.textContent = shortAddress(cell.address);

      card.append(index, value, address);

      if (cell.index === pos) {
        const badge = document.createElement("div");
        badge.className = "array-dom-badge pos";
        badge.textContent = `pos=${pos}`;
        card.appendChild(badge);
      }
      if (cell.index === i) {
        const badge = document.createElement("div");
        badge.className = "array-dom-badge cursor";
        badge.textContent = `i=${i}`;
        card.appendChild(badge);
      }

      track.appendChild(card);
    });

    shell.appendChild(track);

    const meta = document.createElement("div");
    meta.className = "array-visual-meta";
    meta.innerHTML = `
      <div><strong>length</strong><span>${length}</span></div>
      <div><strong>capacity</strong><span>${capacity}</span></div>
      <div><strong>插入值</strong><span>${values.value ?? "—"}</span></div>
      <div><strong>当前 i</strong><span>${Number.isFinite(i) ? i : "—"}</span></div>
    `;
    shell.appendChild(meta);

    structureGraphEl.replaceChildren(shell);
  }

  RendererRegistry.array = renderArrayVisual;
})();
