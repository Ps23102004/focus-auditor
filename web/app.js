/* Focus Auditor dashboard: renders data/report.json, drives selection, witness playback, before/after, TV mode. */
(() => {
  'use strict';
  const M = window.Motion;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const NS = 'http://www.w3.org/2000/svg';
  const SEV = { critical: 0, warning: 1, info: 2 };
  const GLYPH = { UP: '↑', DOWN: '↓', LEFT: '←', RIGHT: '→' };
  const NAME = { UP: 'Up', DOWN: 'Down', LEFT: 'Left', RIGHT: 'Right' };
  const KIND_ICON = { TRAP: 'icon-trap', MISSING_LABEL: 'icon-label', DUPLICATE_LABEL: 'icon-info' };
  const RED = [177, 39, 4], GREEN = [6, 125, 98], GRAY = [101, 113, 131];
  const DATA_Q = new URLSearchParams(location.search).get('data') || '';
  const DATA = /^[a-z0-9-]{1,32}$/.test(DATA_Q) ? `data-${DATA_Q}/` : 'data/';  // ?data=v2 -> web/data-v2/
  const asset = (p) => (!p ? '' : /^(https?:|\/|data(-[a-z0-9-]+)?\/)/.test(p) ? p : DATA + p);
  // Model/exporter strings are untrusted: text only, control chars stripped, length capped.
  const clean = (v, max = 40) => (typeof v === 'string' ? v.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, max) : '');
  const state = { before: null, after: null, view: 'before', sel: null, sample: false, first: true };

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + 's'}`;
  const announce = (msg) => { const s = $('#status'); s.textContent = ''; setTimeout(() => { s.textContent = msg; }, 30); };
  const mix = (a, b, p) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * p)).join(',')})`;
  const center = (b) => ({ x: (b[0] + b[2]) / 2, y: (b[1] + b[3]) / 2 });
  const svg = (name, attrs = {}) => { const e = document.createElementNS(NS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  const icon = (id) => `<svg class="icon" aria-hidden="true" focusable="false"><use href="#${id}"></use></svg>`;

  // ---------- load + normalise ----------
  async function load() {
    for (const [url, sample] of [[DATA + 'report.json', false], ['data/report.sample.json', true]]) {
      try {
        const res = await fetch(url, { cache: 'no-store' });
        if (res.ok) { state.sample = sample; return normalise(await res.json()); }
      } catch (e) { /* try the next source */ }
    }
    return null;
  }

  function normalise(r, before) {
    r = r || {};
    r.meta = r.meta || {};
    r.coverage = Object.assign({ pressed: 0, budget: 0, nodes: 0, inconclusive: [] }, r.coverage);
    r.coverage.inconclusive = r.coverage.inconclusive || [];
    r.graph = Object.assign({ nodes: [], edges: [] }, r.graph);
    r.findings = (r.findings || []).map((f) => Object.assign({ severity: 'info', kind: '', title: 'Finding', evidence: '', bounds: [0, 0, 0, 0], node_ids: [], witness: [], fix_hint: '', test: '', status: 'inconclusive' }, f));
    r.findings.sort((a, b) => (SEV[a.severity] ?? 3) - (SEV[b.severity] ?? 3));
    const c = (k) => r.findings.filter((f) => f.kind === k).length;
    r.summary = Object.assign({ trap: c('TRAP'), missing_label: c('MISSING_LABEL'), duplicate_label: c('DUPLICATE_LABEL'), total: r.findings.length }, r.summary);
    r.verdict = ['pass', 'fail', 'inconclusive'].includes(r.verdict) ? r.verdict : 'inconclusive';
    r.items = r.findings;
    if (before && Array.isArray(r.resolved) && r.resolved.length) { // After view: one row per resolved Before finding
      const old = new Map(before.findings.map((f) => [f.id, f]));
      r.isAfter = true;
      r.items = r.resolved.map((x) => Object.assign({}, old.get(x.id) || {}, x, { fixed: true, status: x.status || 'inconclusive' }));
    }
    if (r.after) r.after = normalise(r.after, r);
    return r;
  }

  // ---------- graph helpers ----------
  const nodeIndex = (r) => new Map(r.graph.nodes.map((n) => [n.id, n]));
  const unionBounds = (bs) => bs.reduce((u, b) => [Math.min(u[0], b[0]), Math.min(u[1], b[1]), Math.max(u[2], b[2]), Math.max(u[3], b[3])], [1e9, 1e9, -1e9, -1e9]);

  function boxFor(r, f) {
    const nodes = nodeIndex(r);
    if (f.fixed) return f.bounds;
    const bs = f.kind === 'TRAP' ? f.node_ids.map((id) => nodes.get(id)).filter(Boolean).map((n) => n.bounds) : [];
    return bs.length ? unionBounds(bs) : f.bounds;
  }

  // Witness keys: the first key enters the app (cold start -> entry node); the rest follow recorded edges.
  function buildPath(r, f) {
    const nodes = nodeIndex(r), out = new Map();
    r.graph.edges.forEach(([a, k, b]) => { if (!out.has(a + '|' + k)) out.set(a + '|' + k, b); });
    const entry = r.graph.nodes[0];
    const pts = [], walls = [], trail = [];
    let cur = entry && entry.id, arrow = null;
    if (cur) {
      pts.push(center(entry.bounds));
      trail.push(cur);
      for (const k of f.witness.slice(1)) {
        const nx = out.get(cur + '|' + k);
        if (!nx || !nodes.has(nx)) break;
        if (nx !== cur) { pts.push(center(nodes.get(nx).bounds)); trail.push(nx); }
        cur = nx;
      }
      if (f.kind === 'TRAP' && f.node_ids.includes(cur)) {
        // short arrowed lead-in (80px, direction of the last witness key) instead of the long approach
        const vec0 = { UP: [0, -1], DOWN: [0, 1], LEFT: [-1, 0], RIGHT: [1, 0] }[f.witness[f.witness.length - 1]] || [1, 0];
        const c0 = center(nodes.get(cur).bounds);
        pts.length = 0;
        pts.push({ x: c0.x - vec0[0] * 80, y: c0.y - vec0[1] * 80 }, c0);
        arrow = { at: c0, dir: vec0 };
        // tour the region along its recorded in-region edges, then push into the wall
        const seen = new Set([cur]);
        for (let moved = true; moved;) {
          moved = false;
          for (const k of ['LEFT', 'RIGHT', 'UP', 'DOWN']) {
            const nx = out.get(cur + '|' + k);
            if (nx && nx !== cur && f.node_ids.includes(nx) && !seen.has(nx)) { seen.add(nx); cur = nx; trail.push(nx); pts.push(center(nodes.get(nx).bounds)); moved = true; break; }
          }
        }
        const vec = { UP: [0, -1], DOWN: [0, 1], LEFT: [-1, 0], RIGHT: [1, 0] };
        let blocked = ['UP', 'DOWN'].filter((k) => out.get(cur + '|' + k) === cur);
        if (!blocked.length) blocked = Object.keys(vec).filter((k) => out.get(cur + '|' + k) === cur);
        blocked.forEach((k) => walls.push({ dir: vec[k], count: 2 }));
      }
    }
    if (f.kind !== 'TRAP') { // no path across the screen: highlighted box + a 60px arrow into it from the last key's direction
      const b = boxFor(r, f), d = { UP: [0, -1], DOWN: [0, 1], LEFT: [-1, 0], RIGHT: [1, 0] }[f.witness[f.witness.length - 1]] || [0, 1];
      const c = center(b), tip = { x: c.x - d[0] * ((b[2] - b[0]) / 2), y: c.y - d[1] * ((b[3] - b[1]) / 2) };
      return { points: [{ x: tip.x - d[0] * 60, y: tip.y - d[1] * 60 }, tip], walls: [], trail, arrow: { at: tip, dir: d }, still: true };
    }
    if (pts.length < 2) { // fallback: centre line of the finding box
      const b = f.bounds, y = (b[1] + b[3]) / 2;
      return { points: [{ x: b[0], y }, { x: b[2], y }], walls, trail: [], arrow: null };
    }
    return { points: pts, walls, trail, arrow };
  }

  // ---------- render ----------
  function render(r, { animate = true } = {}) {
    const rep = $('#report');
    rep.dataset.verdict = r.verdict;
    rep.dataset.ready = '1';
    const mk = r.meta;
    $('#app-name').textContent = mk.app || mk.package || 'Unknown app';
    $('#device-name').textContent = mk.device || 'Android TV';
    $('#run-id').textContent = mk.run_id || 'run';
    $('#fa-version').textContent = mk.fa_version ? 'v' + mk.fa_version : '';
    $('#package-name').textContent = mk.package || '';
    const ts = $('#run-timestamp');
    ts.textContent = mk.timestamp ? new Date(mk.timestamp).toLocaleString() : '';
    if (mk.timestamp) ts.dateTime = mk.timestamp;
    $('#fixture-label').textContent = state.sample || mk.fixture ? 'Sample fixture' : '';
    renderHero(r);
    renderTiles(r, animate);
    renderMap(r);
    renderLegend(r);
    renderFindings(r);
    renderSteps(r);
    const notes = r.coverage.inconclusive;
    $('#inconclusive-reasons').textContent = notes.length ? (r.verdict === 'inconclusive' ? 'Inconclusive, never shown as passing. ' : '') + 'Coverage notes: ' + notes.map((n) => humanNote(n, r.coverage)).join('; ') : '';
    $$('[data-spatial-focus]').forEach((e) => { if (e.dataset.spatialFocus !== 'true') e.dataset.spatialFocus = 'false'; });
    select(r.items.length ? r.items[0].id : null, { silent: true }); // never leave the map and detail empty
  }

  function renderLegend(r) {
    const lg = $('.legend');
    if (!lg.dataset.before) lg.dataset.before = lg.innerHTML;
    lg.innerHTML = r.isAfter ? '<span class="legend-item"><span class="legend-swatch fixed" aria-hidden="true"></span>Fixed</span>' : lg.dataset.before;
  }

  function humanNote(n, c) {
    let m;
    if (/^budget_exhausted/.test(n)) return `Press budget used (${c.pressed} of ${c.budget})`;
    if ((m = /^node_cap:\s*(\d+) discovered nodes not expanded \(max_nodes=(\d+)\)/.exec(n))) return `${plural(+m[1], 'control')} found but not explored (limit ${m[2]})`;
    return n;
  }

  const fmtElapsed = (s) => (s >= 120 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`);

  const allFixed = (r) => r.isAfter && r.items.length > 0 && r.items.every((x) => x.status === 'passing');

  function verdictText(r) {
    if (r.isAfter) { const p = r.items.filter((x) => x.status === 'passing').length; return p === r.items.length ? `${p} fixed` : `${p} of ${r.items.length} fixed`; }
    if (r.verdict === 'pass') return 'All clear';
    if (r.verdict === 'inconclusive') return 'Inconclusive';
    return plural(r.summary.total, 'finding');
  }

  function markColor(r) { return allFixed(r) ? GREEN : r.verdict === 'pass' ? GREEN : r.verdict === 'inconclusive' ? GRAY : RED; }

  function renderHero(r) {
    const v = $('#verdict');
    v.textContent = verdictText(r) + ' ';
    const mark = document.createElement('span');
    mark.className = 'verdict-mark';
    mark.setAttribute('aria-hidden', 'true');
    mark.style.background = mix(markColor(r), markColor(r), 0);
    v.appendChild(mark);
    const s = r.summary, parts = [];
    if (s.trap) parts.push(plural(s.trap, 'focus trap'));
    if (s.missing_label) parts.push(plural(s.missing_label, 'unnamed control'));
    if (s.duplicate_label) parts.push(plural(s.duplicate_label, 'duplicate-name group'));
    const list = parts.length > 1 ? parts.slice(0, -1).join(', ') + ' and ' + parts[parts.length - 1] : parts[0];
    let d = list ? `${list} found${r.coverage.nodes ? ' across ' + r.coverage.nodes + ' mapped controls' : ''}.` : 'No focus or naming problems found.';
    if (r.isAfter) {
      const n = r.items.length, p = r.items.filter((x) => x.status === 'passing').length;
      d = p === n ? `All ${n} frozen tests now pass on the fixed build.` : `${p} of ${n} frozen tests pass on the fixed build.`;
      if (r.verdict === 'inconclusive') d += ` The re-audit found no new problems, but coverage was incomplete (${r.coverage.pressed} of ${r.coverage.budget} presses), so this is not a clean certificate.`;
      else if (r.verdict === 'fail') d += ` The re-audit still reports ${plural(r.summary.total, 'finding')}.`;
    } else if (r.verdict === 'inconclusive') d = 'The audit could not observe everything, so no result is shown as passing. ' + (list ? d : '');
    $('#verdict-description').textContent = d.trim();
    const pill = $('#run-pill');
    const pc = { fail: ['status-critical', 'icon-fail', 'Failing'], pass: ['status-passing', 'icon-check', 'Passing'], inconclusive: ['status-neutral', 'icon-info', 'Inconclusive'] }[r.verdict];
    pill.className = 'status-pill ' + pc[0];
    pill.innerHTML = icon(pc[1]) + pc[2];
    const c = r.coverage;
    $('#run-note').textContent = [c.budget ? `${c.pressed} of ${c.budget} presses` : '', c.elapsed_s ? fmtElapsed(c.elapsed_s) : ''].filter(Boolean).join(' · ');
  }

  function tile(label, ic, value, note) {
    const el = document.createElement('div');
    el.className = 'summary-tile';
    el.innerHTML = `<div class="tile-label">${icon(ic)}${esc(label)}</div><div class="tile-value">${value}</div><div class="tile-note">${esc(note)}</div>`;
    return el;
  }

  function renderTiles(r, animate) {
    const t = $('#tiles'), s = r.summary, c = r.coverage;
    t.textContent = '';
    const dup = r.findings.filter((f) => f.kind === 'DUPLICATE_LABEL');
    const dupN = dup.reduce((n, f) => n + f.node_ids.length, 0);
    const trapN = r.findings.filter((f) => f.kind === 'TRAP').reduce((n, f) => n + f.node_ids.length, 0);
    const tiles = [
      tile('Traps', 'icon-trap', '<span data-n></span>', s.trap ? `${plural(trapN, 'control')} with no way out` : 'No closed focus regions'),
      tile('Unnamed controls', 'icon-label', '<span data-n></span>', 'No exposed accessible name'),
      tile('Duplicate names', 'icon-info', '<span data-n></span>', dupN ? `${dupN} controls share a name` : 'None'),
      tile('Coverage', 'icon-coverage', `<span data-n></span><small> / ${c.budget || 0} presses</small>`, c.nodes ? `${c.nodes} controls mapped` : 'Not recorded'),
    ];
    const targets = [s.trap, s.missing_label, s.duplicate_label, c.pressed];
    tiles.forEach((el, i) => { t.appendChild(el); M.countUp($('[data-n]', el), targets[i], { from: animate ? 0 : targets[i] }); });
    const cov = tiles[3], pct = c.budget ? Math.min(100, Math.round((c.pressed / c.budget) * 100)) : 0;
    cov.insertAdjacentHTML('beforeend', `<div class="coverage-track" role="progressbar" aria-label="Press budget used" aria-valuemin="0" aria-valuemax="${c.budget || 0}" aria-valuenow="${c.pressed}" aria-valuetext="${c.pressed} of ${c.budget || 0} presses"><div class="coverage-fill" style="width:100%;transform-origin:0 50%;transform:scaleX(${pct / 100})"></div></div>`);
    if (animate && state.first) { M.stagger(tiles); state.first = false; }
  }

  function renderMap(r) {
    const img = $('#map-img');
    if (r.screenshot) img.src = asset(r.screenshot);
    $('#map-device').textContent = `${r.meta.device || 'Android TV'} · 1920 × 1080`;
    const g = $('#finding-boxes');
    g.textContent = '';
    r.items.forEach((f) => {
      const b = boxFor(r, f);
      const rect = svg('rect', { class: 'finding-box', x: b[0], y: b[1], width: b[2] - b[0], height: b[3] - b[1], rx: 10, 'data-finding-id': f.id, 'data-severity': f.severity });
      rect.style.cursor = 'pointer';
      if (f.fixed) { // Before box drawn in success green on the After screenshot, only while selected
        rect.removeAttribute('data-severity');
        rect.dataset.fixedBox = '1';
        rect.style.cssText += ';stroke:#067D62;stroke-width:2px;stroke-dasharray:none;fill:rgba(6,125,98,.08);display:none';
      }
      rect.addEventListener('click', () => select(f.id));
      g.appendChild(rect);
    });
    $('#focus-path').setAttribute('points', '');
    $('#node-labels').textContent = '';
    $('#map-meta').textContent = `${r.isAfter ? plural(r.items.length, 'fixed item') : plural(r.findings.length, 'finding')} · ${r.coverage.nodes || r.graph.nodes.length} mapped controls`;
  }

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };

  function suggestNode(f) {
    const name = clean(f.suggested_name);
    if (f.kind !== 'MISSING_LABEL' || !name) return null;
    const applied = !!f.fixed && f.status === 'passing'; // green only once the fix is verified by its frozen test
    const model = clean(f.suggestion_model, 24);
    const tag = applied ? 'Applied by the fix, test passing' : `${/^gemma4/i.test(model) || !model ? 'Gemma 4' : model} · local · unverified suggestion`;
    const p = el('p', 'suggest-line');
    p.append(el('span', 'suggest-label', 'Model-suggested name'), el('q', 'suggest-name', name), el('span', 'tag' + (applied ? ' tag-applied' : ''), tag));
    return p;
  }

  function renderFindings(r) {
    const ol = $('#findings');
    ol.textContent = '';
    $('#findings-count').textContent = r.items.length ? `(${r.items.length})` : '';
    if (!r.items.length) {
      ol.innerHTML = `<li class="finding-row"><p class="finding-evidence" style="margin-left:0">${r.verdict === 'pass' ? 'Nothing to fix.' : 'No findings, but coverage was incomplete.'}</p></li>`;
      return;
    }
    r.items.forEach((f) => {
      const li = document.createElement('li');
      li.className = 'finding-row';
      li.dataset.findingId = f.id;
      li.dataset.severity = f.severity;
      if (f.fixed) {
        const ok = f.status === 'passing';
        li.dataset.fixed = '1';
        li.innerHTML = `<div class="finding-heading"><svg class="icon severity-icon" aria-hidden="true" focusable="false"><use href="#icon-check"></use></svg>
          <button class="finding-select" type="button" data-action="select" data-spatial-focus aria-expanded="false" aria-controls="detail">${esc(f.title)}</button></div>
          <p class="finding-evidence">${ok ? 'Fixed' : 'Not yet confirmed fixed'}. Frozen test ${esc(f.test)} ${ok ? 'now passes' : 'is ' + esc(f.status)} on the fixed build.</p>
          <code class="finding-bounds" aria-label="Bounds left ${f.bounds[0]}, top ${f.bounds[1]}, right ${f.bounds[2]}, bottom ${f.bounds[3]}">[${f.bounds.join(', ')}]</code>
          <div class="finding-footer"><span class="status-pill ${ok ? 'status-passing' : f.status === 'failing' ? 'status-failing' : 'status-neutral'}">${icon(ok ? 'icon-check' : 'icon-info')}${ok ? 'Test passing' : 'Test ' + esc(f.status)}</span></div>`;
        const sg0 = suggestNode(f);
        if (sg0) $('.finding-evidence', li).after(sg0);
        ol.appendChild(li);
        return;
      }
      const st = { failing: ['status-failing', 'icon-fail', 'Test failing'], passing: ['status-passing', 'icon-check', 'Test passing'] }[f.status] || ['status-neutral', 'icon-info', 'Test inconclusive'];
      li.innerHTML = `<div class="finding-heading"><svg class="icon severity-icon" aria-hidden="true" focusable="false"><use href="#${KIND_ICON[f.kind] || 'icon-warning'}"></use></svg>
        <button class="finding-select" type="button" data-action="select" data-spatial-focus aria-expanded="false" aria-controls="detail">${esc(f.title)}</button></div>
        <p class="finding-evidence">${esc(f.evidence)}</p>
        <code class="finding-bounds" aria-label="Bounds left ${f.bounds[0]}, top ${f.bounds[1]}, right ${f.bounds[2]}, bottom ${f.bounds[3]}">[${f.bounds.join(', ')}]</code>
        <div class="finding-footer"><span class="status-pill ${st[0]}">${icon(st[1])}${st[2]}</span>
        <button class="copy-button" type="button" data-action="copy-fix" data-spatial-focus aria-label="Copy fix prompt for ${esc(f.title)}">${icon('icon-copy')}<span>Copy fix prompt</span></button></div>`;
      const sg = suggestNode(f);
      if (sg) $('.finding-evidence', li).after(sg);
      ol.appendChild(li);
    });
  }

  function renderSteps(r) {
    const c = r.coverage, f = r.findings, failing = f.filter((x) => x.status === 'failing').length;
    const notes = c.inconclusive.length;
    const steps = [
      ['Audit', true, notes ? `Complete with ${plural(notes, 'coverage note')}` : 'Complete', `Crawled ${c.nodes || r.graph.nodes.length} controls with ${c.pressed || 0} D-pad presses over adb.`],
      ['Test', f.length > 0, f.length ? 'Generated' : 'Nothing to test', f.length ? `${plural(f.length, 'frozen live test')}, ${failing} failing on this build.` : 'No findings to freeze into tests.'],
      ['Fix', !!r.after, r.after ? (allFixed(r.after) ? 'Verified' : 'Re-audited') : 'Waiting', r.after ? `Re-audit after the patch: ${plural(r.after.summary.total, 'finding')}${r.after.isAfter ? `, ${r.after.items.filter((x) => x.status === 'passing').length} of ${r.after.items.length} frozen tests passing` : ''}.` : 'A coding agent patches the app; the same tests must then pass.'],
    ];
    if (r.isAfter) { // After view: the same three steps, told from the fixed build's side
      const p = r.items.filter((x) => x.status === 'passing').length, n = r.items.length;
      steps[1] = ['Test', true, 'Re-run', `${plural(n, 'frozen live test')} re-run on the fixed build, ${p} passing.`];
      steps[2] = ['Fix', allFixed(r), allFixed(r) ? 'Verified' : 'Partly fixed', `${p} of ${n} findings fixed. Re-audit: ${plural(r.summary.total, 'finding')}.`];
    }
    $('#run-steps').innerHTML = steps.map((s, i) => `<li class="run-step"><span class="step-number" aria-hidden="true">${i + 1}</span><div><div class="step-title">${s[0]} <span class="step-state${s[1] ? ' complete' : ''}">${esc(s[2])}</span></div><p>${esc(s[3])}</p></div></li>`).join('');
  }

  // ---------- selection ----------
  function current() { return state.view === 'after' && state.after ? state.after : state.before; }
  const findingById = (id) => current().items.find((f) => f.id === id);

  function select(id, { silent = false, replay = false } = {}) {
    const r = current(), f = id && findingById(id);
    state.sel = f ? f.id : null;
    $$('.finding-row[data-finding-id]').forEach((li) => {
      const on = li.dataset.findingId === state.sel;
      li.classList.toggle('is-selected', on);
      if (on) li.setAttribute('aria-current', 'true'); else li.removeAttribute('aria-current');
      $('[data-action=select]', li).setAttribute('aria-expanded', String(on));
    });
    $$('.finding-box').forEach((b) => {
      const on = b.dataset.findingId === state.sel;
      b.classList.toggle('is-selected', on);
      if (b.dataset.fixedBox) b.style.display = on ? '' : 'none';
      b.setAttribute('aria-selected', String(on));
    });
    $('#map-overlay').dataset.hasSelection = String(!!f);
    const ball = $('#focus-ball'), poly = $('#focus-path');
    if (!f) {
      $('#detail-title').textContent = 'Select a finding';
      drawArrow(null);
      fillExtras(null);
      $('#detail-body').textContent = r.items.length ? 'Pick a finding to see its fix, the evidence path and the generated test.' : '';
      $('#detail-test').textContent = 'none';
      $('#map-selected').innerHTML = '<strong>Selected:</strong> none';
      $('#witness-keys').textContent = '';
      $('#node-labels').textContent = '';
      poly.setAttribute('points', '');
      return;
    }
    $('#detail-title').textContent = f.title;
    if (f.fixed) {
      $('#detail-body').textContent = `Fixed: the frozen test now ${f.status === 'passing' ? 'passes' : 'reports ' + f.status} on the fixed build.`;
      $('#detail-test').textContent = f.test_file || `tests_generated/${f.test}.py`;
      $('#map-selected').innerHTML = `<strong>Selected:</strong> ${esc(f.title)}`;
      $('#witness-keys').textContent = '';
      drawArrow(null);
      fillExtras(f);
      poly.setAttribute('points', '');
      ball.style.opacity = '0';
      renderLabels(r, f);
      if (!silent) announce(`Selected fixed item: ${f.title}. Frozen test ${f.status}.`);
      return;
    }
    $('#detail-test').textContent = f.test_file || f.test || 'none';
    $('#map-selected').innerHTML = `<strong>Selected:</strong> ${esc(f.title)}`;
    const keys = $('#witness-keys');
    const name = f.witness.map((k) => NAME[k] || k).join(', ');
    keys.setAttribute('role', 'group');
    keys.setAttribute('aria-label', name ? `Key sequence from a cold start: ${name}` : 'No key sequence recorded');
    keys.innerHTML = f.witness.map((k) => `<kbd aria-label="${NAME[k] || esc(k)}">${GLYPH[k] || esc(k)}</kbd>`).join('') +
      (f.witness.length ? `<span class="witness-result">${f.kind === 'TRAP' ? 'then no way out' : 'reaches the control'}</span>` : '');
    renderLabels(r, f);
    const path = buildPath(r, f), nodes = nodeIndex(r);
    const trail = path.trail.map((id) => (nodes.get(id) || {}).label || id.slice(0, 6)).join(' → ');
    $('#detail-body').textContent = (f.fix_hint || 'No fix hint recorded.') + (trail ? ` Recorded path: ${trail}.` : '');
    drawArrow(path.arrow);
    fillExtras(f);
    poly.setAttribute('points', path.points.map((p) => `${p.x},${p.y}`).join(' '));
    if (M.reduced() || path.still) { ball.style.opacity = '0'; if (M.reduced()) M.fade(poly); }
    else M.travel(ball, path.points, { speed: 1100, walls: path.walls, from: replay || path.arrow ? 'start' : 'current' });
    if (!silent) announce(`Selected ${f.severity} finding: ${f.title}. Key sequence: ${name || 'none'}.`);
  }

  // Suggestion line + "what a screen reader hears" in the detail panel.
  function fillExtras(f) {
    const box = $('#detail-suggest'), sg = f && suggestNode(f);
    box.replaceChildren(...(sg ? [sg] : []));
    box.hidden = !sg;
    const audio = $('#hears-audio');
    audio.pause();
    $$('[data-action=play-audio]').forEach((b) => { b.textContent = 'Play'; });
    const before = f && f.kind === 'MISSING_LABEL' ? clean(f.announce_before, 80) : '', after = f && f.kind === 'MISSING_LABEL' ? clean(f.announce_after, 80) : '';
    $('#hears').hidden = !(before || after);
    ['before', 'after'].forEach((w) => {
      const text = w === 'before' ? before : after, src = f && clean(f['audio_' + w], 200);
      $('#hears-' + w).textContent = text || 'not recorded';
      const b = $('#play-' + w);
      b.hidden = !src;
      b.dataset.src = src ? asset(src) : '';
      b.setAttribute('aria-label', `Play what a screen reader hears ${w} the fix`);
    });
  }

  function playAudio(btn) {
    const audio = $('#hears-audio'), src = btn.dataset.src;
    const same = audio.getAttribute('src') === src && !audio.paused;
    audio.pause();
    $$('[data-action=play-audio]').forEach((b) => { b.textContent = 'Play'; });
    if (same) return;
    audio.setAttribute('src', src);
    audio.onended = () => { btn.textContent = 'Play'; };
    btn.textContent = 'Stop';
    audio.play().catch(() => { btn.textContent = 'Play'; announce('Audio could not be played.'); });
  }

  function drawArrow(a) {
    let el = $('#lead-arrow');
    if (!el) { el = svg('polygon', { id: 'lead-arrow', fill: '#146EB4', 'aria-hidden': 'true' }); $('#focus-path-layer').insertBefore(el, $('#focus-ball')); }
    if (!a) { el.setAttribute('points', ''); return; }
    const [dx, dy] = a.dir, px = -dy, py = dx, tip = a.at, back = { x: tip.x - dx * 22, y: tip.y - dy * 22 };
    el.setAttribute('points', `${tip.x},${tip.y} ${back.x + px * 11},${back.y + py * 11} ${back.x - px * 11},${back.y - py * 11}`);
  }

  function renderLabels(r, f) {
    const g = $('#node-labels'), nodes = nodeIndex(r);
    g.textContent = '';
    const own = (id) => (nodes.get(id) || {}).label || '';
    const main = { TRAP: 'Trap', MISSING_LABEL: 'No name', DUPLICATE_LABEL: `Same name ×${f.on_screen || f.node_ids.length}` }[f.kind] || 'Finding';
    const name = f.kind === 'TRAP' ? '' : own((f.node_ids || [])[0]);
    const items = [[f.fixed ? 'Fixed' : name ? `${main} · ${name}` : main, boxFor(r, f)]];
    if (f.kind === 'TRAP' && !f.fixed) f.node_ids.forEach((id) => { const n = nodes.get(id); if (n && n.label) items.push([n.label, n.bounds]); });
    items.forEach(([text, b], i) => {
      const w = text.length * 14 + 20, y = i === 0 && b[1] > 40 && (f.kind === 'TRAP' || f.fixed) ? b[1] - 34 : b[3] + 38 <= 1080 ? b[3] + 8 : b[1] + 8; // above for traps; below otherwise so the arrow stays clear
      const grp = svg('g', { transform: `translate(${b[0]} ${y})` });
      grp.appendChild(svg('rect', { class: 'node-label-bg', width: w, height: 30, rx: 6 }));
      const t = svg('text', { class: 'node-label', x: 10, y: 22 });
      t.textContent = text;
      grp.appendChild(t);
      g.appendChild(grp);
    });
  }

  // ---------- copy fix prompt ----------
  function promptFor(r, f) {
    return [
      'Fix this accessibility defect found by Focus Auditor in an Android TV / Fire OS app.',
      `App: ${r.meta.package || r.meta.app || 'unknown'}`,
      `Finding: ${f.title} (${f.kind}, ${f.severity})`,
      `Evidence: ${f.evidence}`,
      `Affected controls: ${f.node_ids.slice(0, 8).join(', ')}${f.node_ids.length > 8 ? ', ...' : ''}`,
      `Bounds on the 1920x1080 screen: [${f.bounds.join(', ')}]`,
      `Reproduce from a cold start with D-pad keys: ${f.witness.join(', ') || 'n/a'}`,
      `Suggested fix: ${f.fix_hint}`,
      `Verify: the frozen live test ${f.test_file || f.test} must go from failing to passing:`,
      `  python3 -m pytest ${f.test_file || f.test} -m device -q`,
      'Do not edit the generated test. After patching, rebuild and reinstall the app, then re-run `python3 -m fa audit`.',
    ].join('\n');
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall through */ }
    const ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }

  async function copyFix(btn) {
    const f = findingById(btn.closest('[data-finding-id]').dataset.findingId);
    const ok = await copyText(promptFor(current(), f));
    const label = $('span', btn), old = 'Copy fix prompt';
    label.textContent = ok ? 'Copied' : 'Copy failed';
    announce(ok ? `Fix prompt copied for ${f.title}.` : 'Could not copy the fix prompt. Select the text in the detail panel instead.');
    setTimeout(() => { label.textContent = old; }, 1600);
  }

  // ---------- before / after ----------
  function morphMark(from, to) {
    const mark = $('#verdict .verdict-mark');
    if (!mark) return;
    if (M.reduced()) { mark.style.background = mix(to, to, 0); return; }
    M.spring({ from: 0, to: 1, response: 0.6 }, (p) => { mark.style.background = mix(from, to, p); });
  }

  function setView(which) {
    if (which === state.view || (which === 'after' && !state.after)) return;
    const prev = current();
    state.view = which;
    $$('.segmented-control [data-role]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.role === which)));
    const rep = $('#report'), next = current();
    const swap = () => {
      render(next, { animate: false });
      morphMark(markColor(prev), markColor(next));
      const d = $('#verdict-delta');
      if (which === 'after') {
        d.hidden = false;
        d.innerHTML = '<span class="verdict-mark" aria-hidden="true"></span><span><span id="delta-from"></span> → <span id="delta-to"></span> findings</span>';
        const mk = $('.verdict-mark', d);
        mk.style.background = mix(RED, RED, 0);
        M.countUp($('#delta-from', d), prev.summary.total, { from: prev.summary.total });
        M.countUp($('#delta-to', d), next.summary.total, { from: prev.summary.total });
        if (M.reduced()) mk.style.background = mix(GREEN, GREEN, 0);
        else M.spring({ from: 0, to: 1, response: 0.7 }, (p) => { mk.style.background = mix(markColor(prev), markColor(next), p); });
        announce(`After the fix: ${prev.summary.total} findings became ${next.summary.total}.`);
      } else { d.hidden = true; d.textContent = ''; announce('Showing the before report.'); }
    };
    if (M.reduced()) { rep.style.transition = 'opacity 120ms linear'; rep.style.opacity = '0'; setTimeout(() => { swap(); rep.style.opacity = '1'; setTimeout(() => { rep.style.transition = ''; rep.style.opacity = ''; }, 150); }, 120); return; }
    const sp = M.spring({ from: 1, to: 0, response: 0.2 }, (o) => { rep.style.opacity = String(o); }, () => {
      swap();
      M.spring({ from: 0, to: 1, response: 0.35 }, (o) => { rep.style.opacity = String(o); }, () => { rep.style.opacity = ''; });
    });
    return sp;
  }

  // ---------- TV mode + spatial navigation ----------
  let ring = null, ringSprings = null;
  function ensureRing() {
    if (ring) return;
    ring = document.createElement('div');
    ring.setAttribute('aria-hidden', 'true');
    ring.style.cssText = 'position:fixed;left:0;top:0;width:100px;height:100px;border-radius:18px;pointer-events:none;z-index:40;background:rgba(20,110,180,.24);opacity:0;will-change:transform;transform-origin:0 0';
    document.body.appendChild(ring);
    ringSprings = {};
  }

  function moveRing(el, instant) {
    if (!document.body.classList.contains('tv')) { if (ring) ring.style.opacity = '0'; return; }
    if (M.reduced()) { document.body.classList.remove('ring-on'); if (ring) ring.style.opacity = '0'; return; } // no halo: native outline stays
    ensureRing();
    document.body.classList.add('ring-on');
    const r = el.getBoundingClientRect(), pad = 8;
    const t = { x: r.left - pad, y: r.top - pad, sx: (r.width + pad * 2) / 100, sy: (r.height + pad * 2) / 100 };
    const apply = () => { const q = ringSprings; if (q.x && q.y && q.sx && q.sy) { ring.style.transform = `translate(${q.x.cur}px,${q.y.cur}px) scale(${q.sx.cur},${q.sy.cur})`; ring.style.borderRadius = `${18 / q.sx.cur}px / ${18 / q.sy.cur}px`; } }; // radius compensates the scale
    ring.style.opacity = '1';
    for (const k in t) {
      let o = ringSprings[k];
      if (!o || instant || M.reduced()) { // first placement, scroll or reduced motion: jump
        if (o && o.s) o.s.stop();
        o = ringSprings[k] = { cur: t[k], s: null };
        o.s = M.spring({ from: t[k], to: t[k], response: 0.3, damping: 0.85 }, (v) => { o.cur = v; apply(); });
      } else o.s.retarget(t[k]); // keeps velocity: the ring never jumps mid-flight
    }
    apply();
  }

  function candidates() {
    return $$('[data-spatial-focus]').filter((e) => !e.disabled && e.offsetParent !== null);
  }

  function spatial(dir) {
    const all = candidates(), cur = all.includes(document.activeElement) ? document.activeElement : null;
    if (!cur) { const first = $('.finding-select') || all[0]; if (first) first.focus(); return; }
    const a = cur.getBoundingClientRect(), ac = { x: a.left + a.width / 2, y: a.top + a.height / 2 };
    let best = null, bestScore = Infinity;
    all.forEach((el) => {
      if (el === cur) return;
      const b = el.getBoundingClientRect(), dx = b.left + b.width / 2 - ac.x, dy = b.top + b.height / 2 - ac.y;
      const along = { ArrowRight: dx, ArrowLeft: -dx, ArrowDown: dy, ArrowUp: -dy }[dir];
      if (along <= 1) return;
      const across = dir === 'ArrowLeft' || dir === 'ArrowRight' ? Math.abs(dy) : Math.abs(dx);
      const score = along + 2.5 * across;
      if (score < bestScore) { bestScore = score; best = el; }
    });
    if (best) best.focus();
  }

  function setTv(on) {
    document.body.classList.toggle('tv', on);
    const t = $('#tv-toggle');
    t.setAttribute('aria-pressed', String(on));
    $('span', t).textContent = on ? 'Exit TV mode' : 'TV mode';
    if (on) { const el = document.activeElement; if (el && el.dataset && 'spatialFocus' in el.dataset) moveRing(el, true); }
    else { document.body.classList.remove('ring-on'); if (ring) ring.style.opacity = '0'; }
    announce(on ? 'TV mode on. Arrow keys move, Enter inspects, Escape returns to the findings.' : 'TV mode off.');
  }

  function wire() {
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      if (btn.dataset.action === 'play-audio') { playAudio(btn); return; }
      const row = btn.closest('[data-finding-id]');
      if (btn.dataset.action === 'select' && row) select(row.dataset.findingId, { replay: state.sel === row.dataset.findingId });
      else if (btn.dataset.action === 'copy-fix' && row) copyFix(btn);
      else if (btn.dataset.action === 'replay') { if (state.sel) select(state.sel, { replay: true, silent: true }); else announce('Select a finding to replay its path.'); }
    });
    $$('.segmented-control [data-role]').forEach((b) => b.addEventListener('click', () => setView(b.dataset.role)));
    $('#tv-toggle').addEventListener('click', () => setTv(!document.body.classList.contains('tv')));
    document.addEventListener('focusin', (e) => {
      const el = e.target.closest && e.target.closest('[data-spatial-focus]');
      $$('[data-spatial-focus="true"]').forEach((x) => { x.dataset.spatialFocus = 'false'; });
      if (el) { el.dataset.spatialFocus = 'true'; moveRing(el, false); }
    });
    window.addEventListener('scroll', () => { const el = document.activeElement; if (el && el.dataset && 'spatialFocus' in el.dataset) moveRing(el, true); }, { passive: true });
    document.addEventListener('keydown', (e) => {
      if (!document.body.classList.contains('tv') || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key.startsWith('Arrow')) { e.preventDefault(); spatial(e.key); }
      else if (e.key === 'Escape') {
        e.preventDefault();
        const row = $('.finding-row.is-selected [data-action=select]') || $('.finding-select');
        if (row) row.focus();
      } else if (e.key === 'Enter') {
        const el = document.activeElement;
        if (el && 'spatialFocus' in el.dataset && el.tagName !== 'BUTTON' && el.tagName !== 'A') { e.preventDefault(); el.click(); }
      }
    });
    const mq = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)');
    if (mq && mq.addEventListener) mq.addEventListener('change', () => { if (mq.matches && state.sel) select(state.sel, { silent: true }); });
  }

  // ---------- evidence (data*/ml.json, optional) ----------
  const num = (v, d = 2) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : null);

  function evidenceRows(ml) {
    const rows = [], sm = ml.screen_match, ns = ml.name_suggestions;
    const join = (parts) => parts.filter(Boolean).join(' · ');
    if (sm && typeof sm === 'object') {
      rows.push(['Screen matching', [join([
        sm.best_method && num(sm.best_f1) ? `Best method: ${clean(sm.best_method, 30)}, F1 ${num(sm.best_f1)}` : '',
        num(sm.network_f1) ? `Network F1 ${num(sm.network_f1)}` : '',
        typeof sm.n_pairs === 'number' ? `${sm.n_pairs} pairs` : ''])].concat(clean(sm.verdict, 240)).filter(Boolean).join('. ') || 'Not reported.']);
    } else rows.push(['Screen matching', 'Not reported.']);
    if (ns && typeof ns.n === 'number' && ns.n < 20) rows.push(['Name suggestions', 'Not reported: fewer than 20 labelled icons.']);
    else if (ns && typeof ns.n === 'number') {
      const base = clean(ns.baseline, 40);
      rows.push(['Name suggestions', join([
        num(ns.exact_match) ? `Exact match ${num(ns.exact_match)}${num(ns.baseline_exact_match) ? ` vs ${num(ns.baseline_exact_match)}` : ''}` : '',
        num(ns.token_f1) ? `Token F1 ${num(ns.token_f1)}${num(ns.baseline_token_f1) ? ` vs ${num(ns.baseline_token_f1)}` : ''}` : '',
        base ? `best baseline: ${base}` : '', `${ns.n} icons`])]);
    } else rows.push(['Name suggestions', 'Not reported.']);
    rows.push(['Announcements', 'Rules: TalkBack-style naming rules, not a model and not a device recording.' + (ml.announcements && clean(ml.announcements.note, 200) ? ' ' + clean(ml.announcements.note, 200) : '')]);
    return rows;
  }

  async function loadEvidence() {
    try {
      const res = await fetch(DATA + 'ml.json', { cache: 'no-store' });
      if (!res.ok) return;
      const ml = await res.json();
      if (!ml || typeof ml !== 'object') return;
      const ol = $('#evidence-rows');
      ol.textContent = '';
      evidenceRows(ml).forEach(([title, text]) => {
        const li = el('li');
        li.append(el('h3', '', title), el('p', '', text));
        ol.appendChild(li);
      });
      $('#evidence').hidden = false;
      $('#how-link').hidden = false;
    } catch (e) { /* evidence is optional */ }
  }

  // ---------- boot ----------
  async function boot() {
    wire();
    $$('.segmented-control button, #tv-toggle, #replay-witness').forEach((e) => { e.dataset.spatialFocus = 'false'; });
    loadEvidence();
    const r = await load();
    if (!r) {
      $('#report').dataset.ready = '1';
      $('#verdict').textContent = 'No report';
      $('#verdict-description').textContent = 'Could not load data/report.json or the sample fixture.';
      announce('No report could be loaded.');
      return;
    }
    state.before = r;
    state.after = r.after || null;
    const afterBtn = $('[data-role=after]');
    if (state.after) { afterBtn.disabled = false; afterBtn.removeAttribute('aria-describedby'); }
    render(r);
    const q = new URLSearchParams(location.search);
    if (q.get('app') === '1') { $('#tv-toggle').hidden = true; setTv(true); } // TV app shell: always 10-foot mode, no toggle
    else if (q.get('tv') === '1') setTv(true);
  }

  boot();
})();
