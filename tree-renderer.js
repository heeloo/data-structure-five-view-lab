(() => {
  if (typeof RendererRegistry === "undefined") return;

  function renderBinaryTree(snap) {
    const nodes = snap.tree || [];
    const values = snap.values || {};
    const isRedBlack = runMeta.renderer === "red-black-tree" || nodes.some(node => node.color);
    if (!nodes.length) {
      structureGraphEl.innerHTML = '<div class="pointer-empty">没有树快照</div>';
      return;
    }

    const byAddress = new Map(nodes.map(node => [String(node.address), node]));
    const rootAddress = String(values.root);
    const currentAddress = String(values.current);
    const newAddress = String(values.new_node);
    const positions = new Map();
    const reachable = new Set();
    const width = 920;

    function place(address, depth, minX, maxX) {
      if (isNullPointer(address) || !byAddress.has(String(address)) || reachable.has(String(address))) return;
      const key = String(address);
      const node = byAddress.get(key);
      const x = (minX + maxX) / 2;
      const y = 88 + depth * 116;
      reachable.add(key);
      positions.set(key, {x, y, depth});
      place(node.left, depth + 1, minX, x);
      place(node.right, depth + 1, x, maxX);
    }

    place(rootAddress, 0, 70, 850);
    const detached = nodes.filter(node => !reachable.has(String(node.address)) || node.detached);
    detached.forEach((node, index) => positions.set(String(node.address), {x: 790 - index * 125, y: 352, depth: 3, detached: true}));

    const svg = [`<svg class="tree-canvas" viewBox="0 0 ${width} 430" role="img" aria-label="${isRedBlack ? "红黑树" : "二叉搜索树"}结构图">`,
      '<defs><marker id="tree-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="tree-arrow-head"/></marker></defs>'];

    for (const node of nodes) {
      const from = positions.get(String(node.address));
      if (!from || from.detached) continue;
      for (const field of ["left", "right"]) {
        const to = positions.get(String(node[field]));
        if (!to || to.detached) continue;
        svg.push(`<line class="tree-edge" x1="${from.x}" y1="${from.y + 34}" x2="${to.x}" y2="${to.y - 34}" marker-end="url(#tree-arrow)"/>`);
        svg.push(`<text class="tree-edge-label" x="${(from.x + to.x) / 2 + (field === "left" ? -13 : 13)}" y="${(from.y + to.y) / 2 - 5}" text-anchor="middle">${field}</text>`);
      }
    }

    for (const node of nodes) {
      const address = String(node.address);
      const pos = positions.get(address);
      if (!pos) continue;
      const classes = ["tree-node"];
      if (address === rootAddress) classes.push("is-root");
      if (address === currentAddress) classes.push("is-current");
      if (address === newAddress) classes.push("is-new");
      if (pos.detached || node.detached) classes.push("is-detached");
      if (node.color === "red") classes.push("is-red");
      if (node.color === "black") classes.push("is-black");
      const badges = [];
      if (address === currentAddress) badges.push("current");
      if (address === newAddress) badges.push("new_node");
      if (address === rootAddress) badges.push("root");
      svg.push(`<g class="${classes.join(" ")}">`);
      if (pos.detached || node.detached) svg.push(`<rect class="tree-detached-zone" x="${pos.x - 72}" y="${pos.y - 55}" width="144" height="112" rx="16"/>`);
      svg.push(`<rect class="tree-node-box" x="${pos.x - 52}" y="${pos.y - 34}" width="104" height="68" rx="15"/>`);
      svg.push(`<text class="tree-node-value" x="${pos.x}" y="${pos.y + 7}" text-anchor="middle">${escapeHtml(node.data)}</text>`);
      svg.push(`<text class="tree-node-address" x="${pos.x}" y="${pos.y + 26}" text-anchor="middle">${escapeHtml(shortAddress(address))}</text>`);
      const metadata = [node.color ? node.color.toUpperCase() : "", Number.isFinite(Number(node.height)) ? `h=${node.height}` : "", Number.isFinite(Number(node.balance)) ? `bf=${node.balance}` : "", Number.isFinite(Number(node.priority)) ? `p=${node.priority}` : ""].filter(Boolean).join(" · ");
      if (metadata) svg.push(`<text class="tree-node-meta" x="${pos.x}" y="${pos.y + 49}" text-anchor="middle">${escapeHtml(metadata)}</text>`);
      if (badges.length) svg.push(`<text class="tree-node-badge" x="${pos.x}" y="${pos.y - 46}" text-anchor="middle">${badges.join(" · ")}</text>`);
      if (pos.detached || node.detached) svg.push(`<text class="tree-detached-label" x="${pos.x}" y="${pos.y + 51}" text-anchor="middle">尚未连接到树</text>`);
      svg.push("</g>");
    }

    if (isNullPointer(values.current)) svg.push('<text class="tree-null-current" x="460" y="404" text-anchor="middle">current = NULL · 已到达插入位置</text>');
    svg.push("</svg>");

    const direction = Number(values.direction);
    let comparison = "准备开始递归插入";
    if (isRedBlack) {
      const cases = {0:"按 BST 次序插入红色新结点",1:"红父红叔：父叔染黑、祖父染红",2:"红父黑叔 + LL 外侧：右旋祖父",3:"旋转与重染色已完成",4:"检查并恢复全部红黑性质",10:"LL 外侧冲突",11:"LL 重染色，准备右旋祖父",12:"LL 单旋修复完成",20:"RR 外侧冲突",21:"RR 重染色，准备左旋祖父",22:"RR 单旋修复完成",30:"LR 内侧冲突",31:"LR 第一次左旋父结点",32:"LR 第二次右旋祖父完成",40:"RL 内侧冲突",41:"RL 第一次右旋父结点",42:"RL 第二次左旋祖父完成"};
      comparison = cases[Number(values.case_code)] || "执行红黑树插入修复";
    } else if (isNullPointer(values.current)) comparison = `current = NULL，创建 ${values.target}`;
    else if (direction < 0) comparison = `${values.target} < 当前节点，进入 left`;
    else if (direction > 0) comparison = `${values.target} > 当前节点，进入 right`;
    else if (!isNullPointer(values.new_node)) comparison = `插入 ${values.target} 完成`;

    const callStack = snap.debugger?.call_stack || [];
    const shell = document.createElement("div");
    shell.className = "tree-visual";
    shell.innerHTML = `
      <div class="tree-legend">
        <span><i class="tree-swatch root"></i>root</span>
        <span><i class="tree-swatch current"></i>current</span>
        <span><i class="tree-swatch fresh"></i>new_node</span>
        <span><i class="tree-swatch detached"></i>未连接结点</span>
        ${isRedBlack ? '<span><i class="tree-swatch red"></i>红结点</span><span><i class="tree-swatch black"></i>黑结点</span>' : ''}
      </div>
      ${svg.join("")}
      <div class="tree-runtime">
        <div class="tree-comparison"><strong>当前决策</strong><span>${escapeHtml(comparison)}</span></div>
        <div class="tree-addresses">
          <span>root <b>${escapeHtml(shortAddress(values.root))}</b></span>
          <span>current <b>${escapeHtml(shortAddress(values.current))}</b></span>
          <span>new_node <b>${escapeHtml(shortAddress(values.new_node))}</b></span>
          <span>${isRedBlack ? "repair case" : "depth"} <b>${escapeHtml(isRedBlack ? values.case_code : values.depth)}</b></span>
        </div>
        <div class="tree-call-stack">
          <strong>LLDB CALL STACK</strong>
          <div>${callStack.map(frame => `<span class="tree-frame ${["bst_insert","rb_insert","rb_fixup","rotate_left","rotate_right"].includes(frame.function) ? "recursive" : ""}">#${frame.index} ${escapeHtml(frame.function)}</span>`).join('<i>←</i>') || '<span class="tree-frame">等待调试器帧</span>'}</div>
        </div>
      </div>
    `;
    structureGraphEl.replaceChildren(shell);
  }

  RendererRegistry["binary-tree"] = renderBinaryTree;
  RendererRegistry["red-black-tree"] = renderBinaryTree;
})();
