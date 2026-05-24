function insertSymbol(sym) {
  const textarea = document.getElementById("query");
  if (!textarea) return;
  
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const text = textarea.value;
  
  textarea.value = text.substring(0, start) + sym + text.substring(end);
  textarea.selectionStart = textarea.selectionEnd = start + sym.length;
  textarea.focus();
}

function switchPalette(id) {
  // Tabs
  document.querySelectorAll('.palette-tab').forEach(tab => {
    tab.classList.remove('active');
    if (tab.getAttribute('onclick').includes(id)) {
      tab.classList.add('active');
    }
  });
  
  // Contents
  document.querySelectorAll('.palette-content').forEach(content => {
    content.classList.remove('active');
  });
  document.getElementById('palette-' + id).classList.add('active');
}

function setTemplate(type) {
  const q = document.getElementById("query");
  if (type === 'modal') {


  } else if (type === 'prop') {
    q.value = `Domain: propositional_logic
Formula: "((p -> q) & p) -> q"

Question: Is this a tautology?`;
  } else if (type === 'la') {
    q.value = `Domain: linear_algebra
Problem: What is the dimension of the space of n x n symmetric matrices?
n = ? (symbolic)`;
  }
}

function normalizeModalFormula(s) {
  if (!s) return s;
  s = s.replace(/□/g, "[]").replace(/◇/g, "<>");
  s = s.replace(/\bbox\b/gi, "[]").replace(/\bdiamond\b/gi, "<>");
  s = s.replace(/\[\]\s+(?=[A-Za-z(~\[])/g, "[]");
  s = s.replace(/<>\s+(?=[A-Za-z(~\[])/g, "<>");
  s = s.replace(/\[\]\s+\[\]\s*/g, "[][]");
  s = s.replace(/<>\s+<>\s*/g, "<><>");
  return s;
}

function normalizeInputText(raw) {
  if (!raw) return raw;
  const lines = raw.split(/\r?\n/);
  let out = [];
  let inFormulaLine = false;
  for (const line of lines) {
    if (/^\s*Formula\s*:/i.test(line)) {
      inFormulaLine = true;
      const parts = line.split(/:(.+)/);
      const prefix = parts[0];
      const rest = parts[1] || "";
      out.push(prefix + ":" + " " + normalizeModalFormula(rest));
      continue;
    }
    out.push(inFormulaLine ? normalizeModalFormula(line) : line);
  }
  return out.join("\n");
}

let lastCandidates = [];
let LAST_SOLVE = null;
let LAST_MAPPING_SUGGEST = null;

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  return await res.json();
}

function getTextCrossHintThreshold() {
  const el = document.getElementById("tcHintThreshold");
  const v = el ? Number(el.value) : NaN;
  return Number.isFinite(v) ? v : 0.25;
}

function initTextCrossHintControl() {
  const el = document.getElementById("tcHintThreshold");
  const out = document.getElementById("tcHintThresholdValue");
  if (!el || !out) return;
  const stored = localStorage.getItem("tc_hint_min_score");
  if (stored !== null && !Number.isNaN(Number(stored))) {
    el.value = stored;
  }
  const update = () => {
    const v = Number(el.value);
    out.textContent = Number.isFinite(v) ? v.toFixed(2) : "0.25";
    localStorage.setItem("tc_hint_min_score", String(el.value));
  };
  el.addEventListener("input", update);
  update();
}

async function fetchUiRules() {
  try {
    const r = await fetch("/api/ui_rules");
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

function renderInputRules(rules) {
  // 決定打：HTMLに直書きした新しいルールを優先するため、サーバーからの上書きを停止する
  /*
  const el = document.getElementById("inputRules");
  if (!el) return;
  const en = rules?.rule_en || rules?.en || 'Input Rule: Formulas are auto-extracted (quoting optional).';
  el.textContent = en;
  */
  const q = document.getElementById("query");
  if (q && !q.placeholder) {
    q.placeholder = 'Ex: "((A -> B) & A) -> B" / "[]p -> [][]p"';
  }
}

// Tab Switching Logic
function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
  
  // Find the button that called this
  const targetBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
  if(targetBtn) targetBtn.classList.add('active');
  
  document.getElementById(tabId).classList.add('active');
  
  // If switching to graph tab, force resize to fix Cytoscape sizing
  if(tabId === 'tab-graph') {
    setTimeout(() => {
        // Trigger graph redraw if needed
    }, 100);
  }
}

function setTemplate(type) {
  const q = document.getElementById("query");
  if (type === 'modal') {
    q.value = "Domain: modal_logic\nAssumption: transitive\nFormula: box A -> box box A";
  } else if (type === 'prop') {
    q.value = "Domain: propositional_logic\nFormula: ((A -> B) & A) -> B";
  } else if (type === 'la') {
    q.value = "Domain: linear_algebra\nProblem: What is the dimension of the space of n x n symmetric matrices?";
  }
}

async function solve() {
  const q = document.getElementById("query").value;
  const validation = validateQuotedFormula(q);
  if (!validation.ok) {
    const answerCard = document.getElementById("answer-card");
    answerCard.style.display = "block";
    answerCard.className = "result-card disproved";
    document.getElementById("answer-status").innerText = "INPUT ERROR";
    document.getElementById("answer-text").innerText = validation.message;
    document.getElementById("answer-key").innerText = "";
    return;
  }
  
  // Validation: If Domain is given, Formula should be too (for logic)
  if (/Domain:\s*modal|propositional/i.test(q) && !/Formula:/i.test(q)) {
    if (!confirm("Warning: Domain specified without explicit 'Formula:' line. Extraction might be less accurate. Continue?")) return;
  }

  const answerCard = document.getElementById("answer-card");
  
  // Reset UI
  answerCard.style.display = "block";
  answerCard.className = "result-card"; 
  document.getElementById("answer-status").innerText = "SOLVING...";
  document.getElementById("answer-text").innerText = "";
  document.getElementById("answer-key").innerText = "";
  
  try {
    const normalizedQuery = normalizeInputText(q);
    const res = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: normalizedQuery,
        text_cross_hint_min_score: getTextCrossHintThreshold()
      })
    });

    const data = await res.json();
    LAST_SOLVE = data;

    const decomp = data?.payload?.decomp;
    const hasMapping = !!(decomp?.evidence?.text_cross_mapping);
    if (!hasMapping) {
      try {
        LAST_MAPPING_SUGGEST = await postJSON("/api/text_cross/mapping_suggest", { query: normalizedQuery });
      } catch (e) {
        LAST_MAPPING_SUGGEST = null;
      }
    } else {
      LAST_MAPPING_SUGGEST = null;
    }

    renderSolutionReport(data);

  } catch(e) {
    document.getElementById("answer-status").innerText = "ERROR";
    document.getElementById("answer-text").innerText = e.message;
  }
}

function renderSolutionReport(data) {
  const status = (data.status || "unknown").toLowerCase();
  document.getElementById("answer-status").innerText = status.toUpperCase();
  document.getElementById("answer-domain").innerText = data.domain_guess || "unknown";
  document.getElementById("answer-key").innerText = "KEY: " + (data.problem_key || "");

  const answerCard = document.getElementById("answer-card");
  answerCard.className = "result-card " + status;

  let html = `<div style="font-size:1.1em; font-weight:bold; margin-bottom:15px;">${escapeHtml(data.answer_text)}</div>`;


  // Proof Block
  if (data.proof) {
    html += `<div class="item" style="border-left:3px solid var(--accent-green)">
      <div style="color:var(--accent-green); font-weight:bold; margin-bottom:10px;">REASONING PROOF (Method: ${escapeHtml(data.proof.method)})</div>
      <div style="font-size:0.9em; line-height:1.6;">
        ${(data.proof.steps || []).map((s, i) => `<div>${i+1}. ${escapeHtml(s)}</div>`).join("")}
      </div>
    </div>`;
  }

  // Counterexample Block
  if (data.counterexample) {
    html += `<div class="item" style="border-left:3px solid var(--accent-red)">
      <div style="color:var(--accent-red); font-weight:bold; margin-bottom:10px;">COUNTEREXAMPLE FOUND (Method: ${escapeHtml(data.counterexample.method)})</div>
      <pre style="font-size:0.85em;">${escapeHtml(JSON.stringify(data.counterexample.structure, null, 2))}</pre>
      <div style="font-size:0.8em; color:#888; margin-top:5px;">Note: ${escapeHtml(data.counterexample.note)}</div>
    </div>`;
  }

  // Why / Limitation
  if (data.why) {
    html += `<div style="margin-top:10px; font-style:italic; color:var(--accent-blue); font-size:0.85em; background:#111; padding:5px; border-radius:3px;">
      <b>INTERNAL EVALUATION:</b> ${escapeHtml(data.why)}
    </div>`;
  }

  // Next Actions
  if (data.next_actions && data.next_actions.length > 0) {
    html += `<div style="margin-top:15px;">
      <div style="font-weight:bold; font-size:0.8em; color:#666; margin-bottom:5px;">SUGGESTED ACTIONS:</div>
      <div style="display:flex; gap:8px; flex-wrap:wrap;">
        ${data.next_actions.map(a => `<span class="tag" style="cursor:pointer; border:1px solid #444;" onclick="document.getElementById('query').value += '\\n${escapeHtml(a)}'">${escapeHtml(a)}</span>`).join("")}
      </div>
    </div>`;
  }

  // Trace (Optional foldable or summary)
  if (data.trace && data.trace.stages) {
      const lastStage = data.trace.stages[data.trace.stages.length - 1];
      html += `<div style="margin-top:10px; font-size:0.75em; color:#555; text-align:right;">
        Completed in ${lastStage ? lastStage.t_ms : '?'} ms | Worlds: ${data.trace.limits.max_worlds || '?'}
      </div>`;
  }

  document.getElementById("answer-text").innerHTML = html;

  const decomp = data?.payload?.decomp;
  if (decomp) renderDecomp(decomp);
  const assumptionCompletion = data?.payload?.assumption_completion;
  renderAssumptionCompletion(assumptionCompletion);
}

function renderAssumptionCompletion(data) {
  const box = document.getElementById("assumptionCompletion");
  if (!box) return;
  box.innerHTML = "";
  if (!data || !data.missing || data.missing.length === 0) {
    box.innerHTML = "<h4>Assumption Completion</h4><div>No missing assumptions detected.</div>";
    return;
  }
  const title = document.createElement("h4");
  title.textContent = "Missing Assumptions (Check to Apply)";
  box.appendChild(title);

  data.missing.forEach(a => {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = a;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + a));
    box.appendChild(label);
    box.appendChild(document.createElement("br"));
  });

  const btn = document.createElement("button");
  btn.className = "secondary";
  btn.textContent = "Re-evaluate";
  btn.onclick = () => rerunWithAssumptions();
  box.appendChild(btn);
}

async function rerunWithAssumptions() {
  const checked = [...document.querySelectorAll("#assumptionCompletion input:checked")]
    .map(cb => cb.value);
  if (checked.length === 0) {
    alert("Please select at least one assumption.");
    return;
  }
  const q = document.getElementById("query");
  if (!q) return;
  const base = q.value || "";
  const filtered = base.split(/\r?\n/).filter(line => !/^\s*Assumption(s)?\s*:/i.test(line));
  filtered.unshift(`Assumptions: ${checked.join(", ")}`);
  q.value = filtered.join("\n");
  const res = await postJSON("/api/cross/solve", {
    query: q.value,
    add_assumptions: checked,
    text_cross_hint_min_score: getTextCrossHintThreshold(),
  });
  const cross = res?.payload?.cross || res.cross;
  const crossView = res?.payload?.cross_view;
  if (res.ok && cross) {
    fillCrossMeta(cross);
    await updateCrossView(cross, crossView);
    fillResultPanel(cross, res);
    if (res?.payload?.decomp) renderDecomp(res.payload.decomp);
    if (res?.payload?.assumption_completion) renderAssumptionCompletion(res.payload.assumption_completion);
  } else {
    solve();
  }
}

function deriveCoreSource(audit) {
  if (!Array.isArray(audit)) return "";
  if (audit.some(a => String(a).includes("core_source=kb_dedup"))) return "kb_dedup";
  if (audit.some(a => String(a).includes("core_source=quoted_or_inline"))) return "quoted_or_inline";
  if (audit.some(a => String(a).includes("core_source=text_cross_hint"))) return "text_cross_hint";
  if (audit.some(a => String(a).includes("core_source=ranked_candidates"))) return "ranked_candidates";
  return "";
}

function renderDecomp(decomp) {
  const el = document.getElementById("decompPanel");
  if (!el) return;
  const safe = (x) => (x === null || x === undefined) ? "" : String(x);
  const joinCodes = (arr) => Array.isArray(arr) ? arr.map(v => `<code>${escapeHtml(safe(v))}</code>`).join(" , ") : "";
  const evidence = decomp?.evidence || {};
  const mapping = evidence?.text_cross_mapping || (LAST_MAPPING_SUGGEST?.mapping || {});
  const mappingDomain = mapping?.domain_hint || "";
  const mappingAssumptions = Array.isArray(mapping?.assumptions) ? mapping.assumptions : [];
  const mappingCount = mapping?.count ?? "";
  const signature = Array.isArray(evidence?.text_cross_signature)
    ? evidence.text_cross_signature
    : (Array.isArray(LAST_MAPPING_SUGGEST?.signature) ? LAST_MAPPING_SUGGEST.signature : []);
  const similars = Array.isArray(evidence?.text_cross_similar_ids) ? evidence.text_cross_similar_ids : [];
  const maxScore = evidence?.text_cross_similarity_max;
  const coreSource = deriveCoreSource(decomp?.audit);
  el.innerHTML = `
    <h4>INPUT NORMALIZATION (Decomposer)</h4>
    <div><b>domain</b>: ${escapeHtml(safe(decomp.domain))}</div>
    <div><b>core_formula</b>: <code>${escapeHtml(safe(decomp.core_formula))}</code></div>
    <div><b>core_source</b>: ${escapeHtml(safe(coreSource))}</div>
    <div><b>candidates</b>: ${joinCodes(decomp.candidates)}</div>
    <div><b>assumptions</b>: ${joinCodes(decomp.assumptions)}</div>
    <div><b>atoms</b>: ${joinCodes(decomp.atoms)}</div>
    <div style="margin-top:8px;"><b>text_cross.mapping</b>: ${escapeHtml(safe(mappingDomain))} ${joinCodes(mappingAssumptions)} ${escapeHtml(safe(mappingCount))}</div>
    <div><b>text_cross.signature</b>: ${joinCodes(signature)}</div>
    <div><b>text_cross.similar_ids</b>: ${joinCodes(similars)}</div>
    <div><b>text_cross.similarity_max</b>: ${escapeHtml(safe(maxScore))}</div>
    <details style="margin-top:8px;">
      <summary>audit</summary>
      <pre>${escapeHtml(Array.isArray(decomp.audit) ? decomp.audit.join("\n") : "")}</pre>
    </details>
  `;
}

function setText(id, s) {
  const el = document.getElementById(id);
  if (el) el.textContent = (s ?? "");
}

function setCode(id, s) {
  const el = document.getElementById(id);
  if (el) el.textContent = (s ?? "");
}

function setPre(id, obj) {
  const el = document.getElementById(id);
  if (el) el.textContent = obj ? JSON.stringify(obj, null, 2) : "";
}

function renderResultList(listEl, resultNodes) {
  if (!listEl) return;
  listEl.innerHTML = "";
  const arr = resultNodes || [];
  for (const r of arr) {
    const div = document.createElement("div");
    div.style.borderBottom = "1px solid #333";
    div.style.padding = "6px 2px";
    const formula = r?.content?.formula || r?.formula || "";
    const status = r?.content?.status || r?.status || "?";
    const audit = (r?.content?.audit || r?.audit || []).slice(0, 3);
    div.innerHTML = `
      <div><b>${escapeHtml(status)}</b> : <code>${escapeHtml(String(formula).slice(0, 70))}</code></div>
      <div style="opacity:0.8; font-size:12px;">${escapeHtml(audit.join(", "))}</div>
    `;
    listEl.appendChild(div);
  }
}

async function updateCrossView(crossObj, crossViewOverride) {
  const svg = document.getElementById("crossGraphSvg");
  if (!svg || !window.renderCrossSvg) return;
  if (crossViewOverride) {
    window.renderCrossSvg(svg, crossViewOverride);
    return;
  }
  const view = await postJSON("/api/cross/view", { cross: crossObj });
  window.renderCrossSvg(svg, view);
}

function fillCrossMeta(cross) {
  setText("crossId", cross?.cross_id || "");
  setText("crossDomain", cross?.domain || (cross?.meta?.domain ?? ""));
  setCode("crossCoreFormula", cross?.core_formula || "");
  setText("crossAtoms", JSON.stringify(cross?.meta?.atoms || []));
  const assumes = (cross?.assumption_nodes || [])
    .map(n => n?.content?.tag || n?.content?.assumption)
    .filter(Boolean);
  setText("crossAssumptions", JSON.stringify(assumes));
}

function fillResultPanel(cross, apiResult) {
  const meta = cross?.meta || {};
  const verdict = apiResult?.verdict || meta.verdict || "";
  const best = apiResult?.best || meta.best || {};
  const counterexample = apiResult?.counterexample || best.counterexample || null;
  const proof = apiResult?.proof || best.proof_sketch || null;

  setText("verdictText", verdict);
  setPre("bestJson", best);
  setPre("cexJson", counterexample);
  setPre("proofJson", proof);
  const listEl = document.getElementById("resultList");
  renderResultList(listEl, cross?.solver_nodes || []);
}

async function explain() {
  const q = document.getElementById("query").value;
  const exDiv = document.getElementById("explain-output");
  exDiv.innerHTML = "⏳ ANALYZING BOUNDARIES...";

  const res = await fetch("/api/explain", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: q, lang: "ja", max_evidence: 8 })
  });

  const ex = await res.json();

  let html = `<div class="item">
    <div><span class="tag">Estimated Domain</span><b>${escapeHtml(ex.domain_guess)}</b></div>
    <div style="margin-top:10px; line-height:1.6;">${escapeHtml(ex.summary)}</div>
  </div>`;

  if (ex.why_steps && ex.why_steps.length) {
    html += `<h3>Boundary Steps</h3><ul style="padding-left:20px; color:#ccc;">`;
    for (const s of ex.why_steps) html += `<li style="margin-bottom:5px;">${escapeHtml(s)}</li>`;
    html += `</ul>`;
  }

  if (ex.evidence && ex.evidence.length) {
    html += `<h3>Evidence (KB)</h3>`;
    for (const ev of ex.evidence) {
      html += `<div class="item">
        <div style="color:var(--accent-blue)"><b>${escapeHtml(ev.id)}</b> <span class="tag">${escapeHtml(ev.kind)}</span></div>
        <div style="font-size:0.8em; margin-bottom:5px;">${escapeHtml(ev.title || "")}</div>
        <pre>${escapeHtml(JSON.stringify(ev, null, 2))}</pre>
      </div>`;
    }
  }

  exDiv.innerHTML = html;
}

const crossBtn = document.getElementById("btnCrossBuild");
const crossSolveBtn = document.getElementById("btnCrossSolve");

if (crossBtn) {
  crossBtn.onclick = async () => {
    const q = document.getElementById("query").value;
    const res = await postJSON("/api/cross/build", {
      query: q,
      save: true,
      text_cross_hint_min_score: getTextCrossHintThreshold(),
    });
    if (res.ok && res.cross) {
      const cross = res.cross;
      fillCrossMeta(cross);
      await updateCrossView(cross);
      fillResultPanel(cross);
    } else {
      alert("cross build failed");
    }
  };
}

  if (crossSolveBtn) {
    crossSolveBtn.onclick = async () => {
      const q = document.getElementById("query").value;
      const res = await postJSON("/api/cross/solve", {
        query: q,
        text_cross_hint_min_score: getTextCrossHintThreshold(),
      });
      const cross = res?.payload?.cross || res.cross;
      const crossView = res?.payload?.cross_view;
      if (res.ok && cross) {
        fillCrossMeta(cross);
        await updateCrossView(cross, crossView);
        fillResultPanel(cross, res);
        if (res?.payload?.decomp) renderDecomp(res.payload.decomp);
        if (res?.payload?.assumption_completion) renderAssumptionCompletion(res.payload.assumption_completion);
      } else {
        alert("cross solve failed");
      }
    };
  }

const initRules = async () => {
  const rules = await fetchUiRules();
  renderInputRules(rules);
  initTextCrossHintControl();
};
initRules();

function extractQuotedFormulasStrict(text) {
  const out = [];
  const re = /"([^"]+)"/g;
  let m;
  while ((m = re.exec(text || "")) !== null) {
    const f = (m[1] || "").trim();
    if (f) out.push(f);
  }
  return out;
}

function normalizeForCheck(s) {
  if (!s) return s;
  return s.replace(/\s+/g, " ").replace(/→/g, "->").trim();
}

function isBrokenArrow(formula) {
  const f = normalizeForCheck(formula);
  if (!f) return true;
  if (f.startsWith("->") || f.endsWith("->")) return true;
  if (f.includes("->")) {
    const parts = f.split("->");
    if (parts.length === 2) {
      const left = parts[0].trim();
      const right = parts[1].trim();
      if (!left || !right) return true;
      if (right.endsWith("[]") || right.endsWith("<>")) return true;
    }
  }
  return false;
}

function validateQuotedFormula(text) {
  const quoted = extractQuotedFormulasStrict(text);
  if (quoted.length) {
    for (const f of quoted) {
      if (isBrokenArrow(f)) {
        return { ok: false, message: `式が不完全です: "${f}"` };
      }
    }
    return { ok: true };
  }

  const raw = text || "";
  // Allow structured headers or math-ish keywords to pass UI guard.
  if (/^\s*Domain\s*:/im.test(raw) || /^\s*Formula\s*:/im.test(raw)) {
    return { ok: true };
  }
  const formulaLike =
    /(\[\]|\<\>|->|→|~|&|\||¬|∧|∨|\(|\)|∫|dx|dy|dz|sin|cos|tan|log|ln|sqrt|∞|φ|ψ|CNF|Tseytin|dim|sym|matrix|rank|det|trace)/i.test(raw);
  if (formulaLike) {
    return { ok: true };
  }

  return { ok: false, message: "式らしい部分が見つかりません。記号や括弧を確認してください。" };
}

async function why() {
  const q = document.getElementById("query").value;
  document.getElementById("nav_summary").innerHTML = "Loading...";
  renderGraph([], []);

  const res = await fetch("/api/boundary_nav", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: q, max_candidates: 120 })
  });

  const nav = await res.json();
  lastCandidates = nav.candidate_ids || [];

  document.getElementById("nav_summary").innerHTML = 
    `<span class="tag">Candidates: ${lastCandidates.length}</span>`;

  await loadSubgraph(lastCandidates.slice(0, 120));
  
  const hsDiv = document.getElementById("hotspots");
  if(nav.hotspots) {
      hsDiv.innerHTML = nav.hotspots.map(h => `<span class="tag" style="border:1px solid var(--accent-red)">${escapeHtml(h.name||h.assumption)}</span>`).join(" ");
  }
}

async function loadSubgraph(ids) {
  const res = await fetch("/api/graph/subgraph", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, max_nodes: 200, max_edges: 400 })
  });
  const g = await res.json();
  renderGraph(g.nodes || [], g.edges || []);
}

function renderGraph(nodes, edges) {
  const el = document.getElementById("graph");
  cytoscape({
    container: el,
    elements: [
      ...nodes.map(n => ({ data: { id: n.id, label: n.label || n.id } })),
      ...edges.map(e => ({ data: { id: `${e.source}->${e.target}`, source: e.source, target: e.target, label: e.label || "" } }))
    ],
    style: [
      { 
        selector: 'node', 
        style: { 
            'label': 'data(label)', 
            'background-color': '#555',
            'color': '#fff',
            'font-size': 10, 
            'text-wrap': 'wrap', 
            'text-max-width': 120 
        } 
      },
      { 
        selector: 'edge', 
        style: { 
            'width': 1,
            'line-color': '#444',
            'curve-style': 'bezier', 
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#444'
        } 
      }
    ],
    layout: { name: 'cose', animate: false }
  });
}

// Proof Functions
async function addProof() {
  if (!LAST_SOLVE) {
    alert("Please Solve first to generate a Problem Key.");
    return;
  }
  
  const payload = {
    problem_key: LAST_SOLVE.problem_key,
    query: LAST_SOLVE.query || "",
    title: document.getElementById("proof_title").value,
    domain: document.getElementById("proof_domain").value,
    kind: document.getElementById("proof_kind").value,
    text: document.getElementById("proof_text").value,
    kb_links: document.getElementById("proof_links").value.split(",").map(s=>s.trim()).filter(Boolean),
    lang: "ja"
  };

  const res = await fetch("/api/proof/add", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const out = await res.json();
  if (out.ok) {
      alert("Proof Saved!");
      loadProofsForThisProblem();
  } else {
      alert("Error saving proof");
  }
}

async function loadProofsForThisProblem() {
  if (!LAST_SOLVE) return;
  searchProofsAPI({ problem_key: LAST_SOLVE.problem_key });
}

async function searchProofs() {
  const q = document.getElementById("proof_search_q").value;
  searchProofsAPI({ query: q });
}

async function searchProofsAPI(body) {
  const res = await fetch("/api/proof/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, limit: 50 })
  });
  const out = await res.json();
  renderProofs(out.items || []);
}

function renderProofs(items) {
  const div = document.getElementById("proofs-list");
  if (!items.length) {
    div.innerHTML = `<div class="item" style="color:#666">No proofs found.</div>`;
    return;
  }
  let html = "";
  for (const p of items) {
    const isVerified = p.status === 'verified';
    const statusColor = isVerified ? 'var(--accent-green)' : 'var(--text-muted)';
    
    html += `
      <div class="item" id="proof-${p.id}">
        <div style="display:flex; justify-content:space-between;">
            <b style="color:var(--accent-green)">${escapeHtml(p.title || p.id)}</b>
            <span class="tag" style="color:${statusColor}">${escapeHtml(p.status.toUpperCase())}</span>
        </div>
        <div style="font-size:0.8em; color:var(--text-muted); margin-bottom:5px;">
            ${escapeHtml(p.domain)} | ${escapeHtml(p.created_at)}
        </div>
        <pre>${escapeHtml(p.text || "")}</pre>
        <div style="margin-top:5px; font-size:0.8em; color:#555; display:flex; justify-content:space-between; align-items:center;">
            <span>Links: ${(p.kb_links||[]).join(", ")}</span>
            ${!isVerified ? `<button class="secondary" style="padding:2px 8px; font-size:0.8em;" onclick="verifyProof('${p.id}')">VERIFY</button>` : ''}
        </div>
        <div id="verify-res-${p.id}" style="margin-top:10px; font-size:0.85em; display:none;"></div>
      </div>
    `;
  }
  div.innerHTML = html;
}

async function verifyProof(proofId) {
  const resDiv = document.getElementById(`verify-res-${proofId}`);
  resDiv.style.display = "block";
  resDiv.innerHTML = "⏳ Verifying...";

  try {
    const res = await fetch("/api/proof/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proof_id: proofId })
    });
    const data = await res.json();
    
    if (data.ok) {
      const r = data.result;
      if (r.status === "verified") {
        resDiv.innerHTML = `<span style="color:var(--accent-green)">✔ ${escapeHtml(r.reason)}</span>`;
        // UIのステータス表示を更新
        const item = document.getElementById(`proof-${proofId}`);
        const tag = item.querySelector(".tag");
        tag.textContent = "VERIFIED";
        tag.style.color = "var(--accent-green)";
        item.querySelector("button").style.display = "none";
      } else {
        resDiv.innerHTML = `<span style="color:var(--accent-red)">✖ ${escapeHtml(r.reason)}</span>`;
      }
    }
  } catch (e) {
    resDiv.innerHTML = `<span style="color:var(--accent-red)">Error: ${e.message}</span>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Paste Handling
document.getElementById("query").addEventListener("paste", async (e) => {
  // Let default paste happen, then analyze
  setTimeout(async () => {
    const text = document.getElementById("query").value;
    // Only trigger if text length is significant or has symbols
    if(text.length > 5) await analyzePaste(text);
  }, 100);
});

async function analyzePaste(text) {
  const options = [];
  
  if (/\[\]|<>|box|diamond|□|◇/i.test(text)) {
    options.push({ label: "Modal Logic (□, ◇)", action: "modal" });
  }
  if (/forall|exists|∀|∃/i.test(text)) {
    options.push({ label: "First-Order Logic (∀, ∃)", action: "fol" });
  }
  if (/&|\||->|↔|∧|∨|¬|→/i.test(text)) {
    options.push({ label: "Propositional Logic (∧, ∨, →)", action: "prop" });
  }
  if (/契約|売主|買主|民法|条文|責任|違反/i.test(text)) {
    options.push({ label: "Legal Document (law)", action: "law" });
  }
  if (/matrix|rank|det|trace|行列|固有値/i.test(text)) {
    options.push({ label: "Linear Algebra", action: "la" });
  }
  
  // Default general option if text is long
  if (text.length > 30 && options.length === 0) {
    options.push({ label: "Natural Language Problem", action: "general" });
  }
  
  // Ask server for hint (lightweight)
  if (options.length === 0) {
      try {
        const res = await postJSON("/api/text_cross/mapping_suggest", { query: text });
        if (res.mapping && res.mapping.domain_hint && res.mapping.domain_hint !== "unknown") {
           const d = res.mapping.domain_hint;
           options.push({ label: `Treat as ${d}`, action: d });
        }
      } catch(e) {}
  }

  if (options.length > 0) {
    console.log("[Paste] Options found:", options);
    showPasteMenu(options);
  } else {
    console.log("[Paste] No options found for text:", text.slice(0, 20));
  }
}

function showPasteMenu(options) {
  const menu = document.getElementById("paste-menu");
  const list = document.getElementById("paste-options");
  list.innerHTML = "";
  
  options.forEach(opt => {
    const btn = document.createElement("button");
    btn.className = "secondary";
    btn.style.textAlign = "left";
    btn.style.padding = "8px";
    btn.textContent = opt.label;
    btn.onclick = () => applyPasteOption(opt.action);
    list.appendChild(btn);
  });
  
  // Center on screen
  menu.style.position = "fixed";
  menu.style.top = "40%";
  menu.style.left = "50%";
  menu.style.transform = "translate(-50%, -50%)";
  menu.style.display = "block";
}

function closePasteMenu() {
  document.getElementById("paste-menu").style.display = "none";
}

function applyPasteOption(action) {
  const ta = document.getElementById("query");
  let text = ta.value;
  
  let header = "";
  if (action === "modal") {
      header = "Domain: modal_logic\n";
  } else if (action === "prop") {
      header = "Domain: propositional_logic\n";
  } else if (action === "law") {
      header = "Domain: law\n";
  } else if (action === "fol") {
      header = "Domain: first_order_logic\n";
  } else if (action === "la") {
      header = "Domain: linear_algebra\n";
  } else if (action === "general") {
      header = "Problem: ";
  } else if (action) {
      header = `Domain: ${action}\n`;
  }
  
  if (header && !text.includes("Domain:") && !text.includes("Problem:")) {
      ta.value = header + text;
  }
  
  closePasteMenu();
  // Optional: flash effect
  ta.style.outline = "2px solid var(--accent-blue)";
  setTimeout(() => ta.style.outline = "", 500);
}
