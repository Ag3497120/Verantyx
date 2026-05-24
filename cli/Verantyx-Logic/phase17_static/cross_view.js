function renderCrossSvg(svgEl, crossView) {
  if (!svgEl) return;
  const W = 900;
  const H = 260;
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svgEl.innerHTML = "";

  const nodes = crossView?.nodes || [];
  const edges = crossView?.edges || [];

  const core = nodes.find(n => n.axis === "core" || (n.id || "").endsWith("__core")) || nodes[0];
  const byAxis = {};
  for (const n of nodes) {
    const ax = n.axis || "other";
    byAxis[ax] = byAxis[ax] || [];
    byAxis[ax].push(n);
  }

  const pos = {};
  const cx = 450;
  const cy = 130;
  if (core) pos[core.id] = { x: cx, y: cy };

  const lanes = [
    ["syntax", 180],
    ["semantic", 720],
    ["assumption", 120],
    ["counterexample", 780],
    ["evidence", 300],
    ["result", 600],
    ["other", 450]
  ];

  for (const [ax, x] of lanes) {
    const arr = (byAxis[ax] || []).filter(n => !core || n.id !== core.id);
    if (!arr.length) continue;
    const step = H / (arr.length + 1);
    for (let i = 0; i < arr.length; i++) {
      pos[arr[i].id] = { x, y: (i + 1) * step };
    }
  }

  for (const n of nodes) {
    if (!pos[n.id]) pos[n.id] = { x: 450, y: 20 + (Math.random() * 220) };
  }

  for (const e of edges) {
    const s = pos[e.source];
    const t = pos[e.target];
    if (!s || !t) continue;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", s.x);
    line.setAttribute("y1", s.y);
    line.setAttribute("x2", t.x);
    line.setAttribute("y2", t.y);
    line.setAttribute("stroke", "#666");
    line.setAttribute("stroke-width", "2");
    svgEl.appendChild(line);
  }

  for (const n of nodes) {
    const p = pos[n.id];
    if (!p) continue;
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", p.x);
    circle.setAttribute("cy", p.y);
    circle.setAttribute("r", (n.axis === "core") ? "18" : "12");
    circle.setAttribute("fill", (n.axis === "core") ? "#00ff88" : "#2b7");
    circle.setAttribute("opacity", (n.axis === "core") ? "0.95" : "0.75");
    svgEl.appendChild(circle);

    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", p.x + 16);
    text.setAttribute("y", p.y + 4);
    text.setAttribute("fill", "#ddd");
    text.setAttribute("font-size", "12");
    text.textContent = (n.label || n.id || "").slice(0, 60);
    svgEl.appendChild(text);
  }
}

window.renderCrossSvg = renderCrossSvg;
