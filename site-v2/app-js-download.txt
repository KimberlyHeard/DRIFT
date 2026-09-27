/*
 * DRIFT workbench. One authoritative evidence adapter, bound to the real
 * report schema (schema_version 1.0): runs[] with assertions[assertion_id,
 * expected, actual, passed, fact_ids, trace_indices] and trace[sequence,
 * virtual_time_us, address_7bit, register, operation, sent_bytes,
 * received_bytes, outcome, fact_ids]. Provenance: reviewer, approved_utc.
 * Replay only: nothing here runs Python or calls Bob.
 */
(function () {
'use strict';

var EV = window.DRIFT_EVIDENCE;
var errEl = document.getElementById('evErr');
function fail(msg) { errEl.hidden = false; errEl.textContent = 'Evidence could not be loaded: ' + msg + ' Nothing below is shown in place of it.'; }

/* ---------------- sheet frames (decorative) ---------------- */
var SHEETS = document.querySelectorAll('.sheet');
Array.prototype.forEach.call(SHEETS, function (s) {
  function band(cls, labels) { var d = document.createElement('div'); d.className = cls; d.setAttribute('aria-hidden', 'true'); d.innerHTML = labels.map(function (l) { return '<span>' + l + '</span>'; }).join(''); s.appendChild(d); }
  var nums = ['8','7','6','5','4','3','2','1'], lets = ['D','C','B','A'];
  band('zones-top', nums); band('zones-bot', nums); band('zones-left', lets); band('zones-right', lets);
  var tag = document.createElement('div'); tag.className = 'sheet-tag'; tag.setAttribute('aria-hidden', 'true');
  tag.innerHTML = '<span>SHEET ' + s.dataset.n + ' / 0' + SHEETS.length + '</span><span>' + s.dataset.t + '</span>';
  s.querySelector('.frame').appendChild(tag);
});

/* ---------------- hero drawing geometry (decorative, values match run) ---------------- */
(function () {
  var cells = document.getElementById('bitcells'), dims = document.getElementById('heroDims');
  var X0 = 80, W = 30, Y = 150, H = 54, bits = '0000110010000000', h = '', i;
  for (i = 0; i < 16; i++) {
    var x = X0 + i * W;
    h += '<rect class="draw" style="--d:' + (0.35 + i * 0.035).toFixed(3) + 's" pathLength="1" x="' + x + '" y="' + Y + '" width="' + W + '" height="' + H + '" fill="none" stroke="#1F3FD1" stroke-width="' + (i === 8 ? 2.2 : 1) + '"/>';
    h += '<text class="fade" style="--d:' + (1.1 + i * 0.03).toFixed(2) + 's" x="' + (x + W / 2) + '" y="' + (Y + 34) + '" text-anchor="middle" font-family="IBM Plex Mono" font-size="17" fill="' + (i === 0 ? '#C9331C' : '#16181D') + '">' + bits[i] + '</text>';
    h += '<text class="fade" style="--d:1.0s" x="' + (x + W / 2) + '" y="' + (Y - 10) + '" text-anchor="middle" font-family="IBM Plex Mono" font-size="10" fill="#80848E">' + (15 - i) + '</text>';
  }
  h += '<rect class="draw" style="--d:.3s" pathLength="1" x="' + X0 + '" y="' + Y + '" width="' + (16 * W) + '" height="' + H + '" fill="none" stroke="#1F3FD1" stroke-width="2.2"/>';
  cells.innerHTML = h;
  var yT = 94, yB = 236, xa = X0, xm = X0 + 8 * W, xb = X0 + 16 * W, s = '';
  [xa, xb].forEach(function (x) { s += '<line class="draw" style="--d:.9s" pathLength="1" x1="' + x + '" y1="' + (Y - 4) + '" x2="' + x + '" y2="' + (yT - 8) + '" stroke="#1F3FD1" stroke-opacity=".4" stroke-width="1"/>'; });
  [xa, xm, xb].forEach(function (x) { s += '<line class="draw" style="--d:1.3s" pathLength="1" x1="' + x + '" y1="' + (Y + H + 4) + '" x2="' + x + '" y2="' + (yB + 8) + '" stroke="#1F3FD1" stroke-opacity=".4" stroke-width="1"/>'; });
  s += '<line class="draw" style="--d:1.0s" pathLength="1" x1="' + (xa + 2) + '" y1="' + yT + '" x2="' + (xb - 2) + '" y2="' + yT + '" stroke="#1F3FD1" stroke-width="1.1" marker-start="url(#ar)" marker-end="url(#ar)"/>';
  s += '<rect class="fade" style="--d:1.2s" x="186" y="' + (yT - 12) + '" width="268" height="24" fill="#FFFFFF"/>';
  s += '<text class="fade" style="--d:1.25s" x="320" y="' + (yT + 4) + '" text-anchor="middle" font-family="Instrument Sans" font-size="13.5" fill="#16181D">16 bits, signed, most significant byte first</text>';
  [[xa, xm, 'first byte · MSB'], [xm, xb, 'second byte · LSB']].forEach(function (p, k) {
    s += '<line class="draw" style="--d:' + (1.4 + k * .1) + 's" pathLength="1" x1="' + (p[0] + 2) + '" y1="' + yB + '" x2="' + (p[1] - 2) + '" y2="' + yB + '" stroke="#1F3FD1" stroke-width="1.1" marker-start="url(#ar)" marker-end="url(#ar)"/>';
    var cx = (p[0] + p[1]) / 2;
    s += '<rect class="fade" style="--d:1.5s" x="' + (cx - 66) + '" y="' + (yB - 11) + '" width="132" height="22" fill="#FFFFFF"/>';
    s += '<text class="fade" style="--d:1.55s" x="' + cx + '" y="' + (yB + 4) + '" text-anchor="middle" font-family="IBM Plex Mono" font-size="12" fill="#4A4E57">' + p[2] + '</text>';
  });
  s += '<path class="draw" style="--d:1.6s" pathLength="1" d="M' + (X0 + W / 2) + ' ' + (Y + H + 2) + ' L' + (X0 + W / 2) + ' ' + (Y + H + 20) + ' L40 ' + (Y + H + 20) + ' L40 ' + (Y + H + 38) + '" fill="none" stroke="#E4472E" stroke-width="1.2"/>';
  s += '<text class="fade" style="--d:1.8s" x="28" y="' + (Y + H + 54) + '" font-family="Instrument Serif" font-style="italic" font-size="16" fill="#C9331C">sign bit</text>';
  s += '<path class="draw" style="--d:1.1s" pathLength="1" d="M52 82 L76 ' + yT + '" fill="none" stroke="#1F3FD1" stroke-width="1.1"/>';
  dims.innerHTML = s;
})();

if (!EV || !EV.tmp117 || !EV.bme280) { fail('evidence.js is missing or incomplete.'); return; }

/* ---------------- adapter ---------------- */
var hasOwn = Object.prototype.hasOwnProperty;
function hexPairs(s) { s = String(s || ''); var out = []; for (var i = 0; i + 1 < s.length; i += 2) out.push(parseInt(s.substr(i, 2), 16)); return out; }
function spaced(s) { return String(s || '').toUpperCase().replace(/(..)(?=.)/g, '$1 '); }
function regNum(r) { return r ? parseInt(r, 16) : null; }

var DEVICES = {
  tmp117: { key: 'tmp117', name: 'TI TMP117', sub: 'I²C 0x48 · one-shot', report: EV.tmp117, contract: EV.tmp117_contract, file: EV.files.tmp117, cfile: EV.files.tmp117_contract,
    regs: { 0x00: 'Temperature result', 0x01: 'Configuration', 0x0F: 'Device ID' },
    datasheet: 'https://www.ti.com/lit/ds/symlink/tmp117.pdf' },
  bme280: { key: 'bme280', name: 'Bosch BME280', sub: 'I²C 0x76 · forced, temperature', report: EV.bme280, contract: EV.bme280_contract, file: EV.files.bme280, cfile: EV.files.bme280_contract,
    regs: { 0xD0: 'Chip ID', 0x88: 'Calibration dig_T1 to dig_T3', 0xF4: 'ctrl_meas', 0xF3: 'status', 0xFA: 'Raw temperature' },
    datasheet: 'https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf' }
};

function factsOf(contract) { var m = {}; ((contract && contract.contract && contract.contract.facts) || []).forEach(function (f) { m[f.id] = f; }); return m; }

var COPY = {
  baseline_25c: ['Normal reading at room temperature', 'A normal one-shot measurement with no fault injected.'],
  baseline_neg1c: ['Normal reading just below freezing', 'A normal one-shot measurement of a negative temperature.'],
  fault_nack_identity: ['The chip does not answer', 'The identity read is not acknowledged. The driver must stop with a clear error.'],
  fault_never_ready: ['The measurement never finishes', 'The ready flag never sets. The driver must give up at its 100,000 µs timeout policy.'],
  fault_wrong_id_bits: ['A different chip answers', 'The device ID has the wrong lower bits. The driver must refuse to continue.'],
  fault_short_temp: ['Only one byte comes back', 'The temperature read returns one byte instead of two. The driver must report a protocol error.'],
  bme280_25c: ['Normal reading, 25.08 °C', 'Calibration read, forced conversion, 20-bit raw value and integer compensation.'],
  bme280_neg8c: ['Normal reading below freezing', 'The same path with a different raw value, producing a negative temperature.'],
  bme280_short_temp: ['Raw temperature read comes back short', 'The driver asks for three bytes and receives two. It must report a protocol error.']
};

function normRun(r, dev) {
  var events = (r.trace || []).map(function (e) {
    return { seq: e.sequence, t: e.virtual_time_us, addr: e.address_7bit, reg: regNum(e.register), regStr: e.register, op: e.operation,
      sent: e.sent_bytes || '', recv: e.received_bytes || '', outcome: e.outcome, faulty: e.outcome !== 'ok', facts: e.fact_ids || [], raw: e };
  });
  var groups = [];
  events.forEach(function (ev) {
    var g = groups[groups.length - 1];
    if (g && g.first.op === ev.op && g.first.regStr === ev.regStr && g.first.sent === ev.sent && g.first.recv === ev.recv && g.first.outcome === ev.outcome) { g.members.push(ev); g.last = ev; }
    else groups.push({ first: ev, last: ev, members: [ev] });
  });
  var variant = r.driver_variant, c = COPY[r.scenario_id] || [r.scenario_id, ''];
  var title = c[0];
  if (variant === 'byte_swap') title = 'Byte-swap control, ' + (/neg1c/.test(r.scenario_id) ? '-1.0 °C case' : '25.0 °C case');
  if (variant === 'repair_candidate') title = 'Repaired driver, ' + (/neg1c/.test(r.scenario_id) ? '-1.0 °C case' : '25.0 °C case');
  var plain = variant === 'byte_swap' ? 'A deliberately broken driver receives the correct bytes and reads them in reverse order. It must keep failing.'
    : variant === 'repair_candidate' ? 'Bob\'s repaired copy runs against the same fixed expectations.' : c[1];
  return { raw: r, dev: dev, id: r.scenario_id, variant: variant, runId: r.run_id, title: title, plain: plain,
    status: r.verification_status, observed: r.expected_behavior_observed === true, exec: r.execution_status, outcome: r.device_outcome,
    isControl: variant === 'byte_swap', isRepair: variant === 'repair_candidate',
    assertions: r.assertions || [], events: events, groups: groups, prov: r.provenance || {}, limits: r.limitations, meta: r.run_metadata || {} };
}

var RUNS = {}, SEEN = {};
Object.keys(DEVICES).forEach(function (k) {
  var d = DEVICES[k];
  if (!d.report || !Array.isArray(d.report.runs)) { fail(k + ' report has no runs array.'); return; }
  d.facts = factsOf(d.contract);
  RUNS[k] = [];
  d.report.runs.forEach(function (r) {
    var key = r.profile_id + '|' + r.scenario_id + '|' + r.driver_variant;
    if (SEEN[key]) return; SEEN[key] = 1;
    RUNS[k].push(normRun(r, d));
  });
});
var ALL = RUNS.tmp117.concat(RUNS.bme280);

function esc(s) { return String(s === undefined || s === null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
function fmtC(v) { return typeof v === 'number' ? (Number.isInteger(v) ? v.toFixed(1) : String(v)) : String(v); }
function us(t) { return t === null || t === undefined ? '' : Number(t).toLocaleString('en-US') + ' µs'; }
function factRef(f) { if (!f) return ''; var p = f.page ? 'p. ' + f.page : (f.pages ? 'pp. ' + f.pages.join(', ') : ''); return [p, f.section ? '§' + f.section : ''].filter(Boolean).join(' '); }
function primary(run) { return run.assertions.find(function (a) { return a.assertion_id === 'celsius' || a.assertion_id === 'expected_exception'; }) || run.assertions[0]; }
function unitFor(a) { return a && a.assertion_id === 'celsius' ? ' °C' : ''; }

/* ---------------- hero legend and tally from evidence ---------------- */
(function () {
  var tf = DEVICES.tmp117.facts, run = RUNS.tmp117.find(function (r) { return r.id === 'baseline_25c' && r.variant === 'baseline'; });
  var step = run && run.events.find(function (e) { return e.regStr === '0x00' && e.op === 'read'; });
  var cel = run && run.assertions.find(function (a) { return a.assertion_id === 'celsius'; });
  var items = [
    ['', '<b>Datasheet fact F02.</b> ' + esc(tf.F02 && tf.F02.claim), 'TI ' + esc(DEVICES.tmp117.contract.contract.source.document) + ' ' + factRef(tf.F02)],
    ['sun', '<b>Approved by ' + esc(run.prov.reviewer) + '.</b> Bob drafted the cited facts; the approval binds them to the exact PDF by hash.', esc(String(run.prov.approved_utc).replace('T', ' ').slice(0, 19)) + ' UTC'],
    ['', '<b>Recorded bus step ' + (step ? step.seq : '?') + ':</b> the driver read register 0x00 and received ' + esc(spaced(step && step.recv)) + '.', 'cites ' + esc(step ? step.facts.join(', ') : '')],
    ['', '<b>Fact F04 and the check.</b> ' + esc(tf.F04 && tf.F04.claim.split(';')[0]) + '. Expected ' + fmtC(cel.expected) + ' °C, observed ' + fmtC(cel.actual) + ' °C.', factRef(tf.F04)]
  ];
  document.getElementById('heroLegend').innerHTML = items.map(function (it, i) {
    return '<li><span class="cn ' + it[0] + '">' + (i + 1) + '</span><span>' + it[1] + '<span class="ref">' + it[2] + '</span></span></li>';
  }).join('');
  var nFacts = Object.keys(DEVICES.tmp117.facts).length + Object.keys(DEVICES.bme280.facts).length;
  var obs = ALL.filter(function (r) { return r.observed; }).length;
  document.getElementById('tally').innerHTML =
    '<div><dt>real sensors, each approved by name</dt><dd>2</dd></div>' +
    '<div><dt>page-cited datasheet facts</dt><dd>' + nFacts + '</dd></div>' +
    '<div><dt>recorded cases, ' + obs + ' as expected</dt><dd>' + ALL.length + '</dd></div>';
})();

/* ---------------- workbench ---------------- */
var S = { dev: 'tmp117', sel: 0, step: 0, timer: null };

function renderTabs() {
  var el = document.getElementById('devTabs');
  el.innerHTML = Object.keys(DEVICES).map(function (k) {
    var d = DEVICES[k], n = RUNS[k].length;
    return '<button class="devtab" role="tab" id="tab-' + k + '" aria-selected="' + (S.dev === k) + '" data-k="' + k + '"><b>' + d.name + '</b><span>' + d.sub + ' · ' + n + ' recorded runs</span></button>';
  }).join('');
  Array.prototype.forEach.call(el.querySelectorAll('.devtab'), function (b) {
    b.addEventListener('click', function () { S.dev = b.dataset.k; renderTabs(); renderSchedule(); select(0); });
    b.addEventListener('keydown', function (e) { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { var ks = Object.keys(DEVICES); var i = (ks.indexOf(S.dev) + (e.key === 'ArrowRight' ? 1 : ks.length - 1)) % ks.length; S.dev = ks[i]; renderTabs(); renderSchedule(); select(0); document.getElementById('tab-' + ks[i]).focus(); } });
  });
}

function renderSchedule() {
  var el = document.getElementById('schedule'), runs = RUNS[S.dev];
  var groups = [['Normal and fault cases', function (r) { return !r.isControl && !r.isRepair; }], ['Intentional negative controls', function (r) { return r.isControl; }], ['After repair', function (r) { return r.isRepair; }]];
  var h = '';
  groups.forEach(function (g) {
    var items = runs.map(function (r, i) { return [r, i]; }).filter(function (x) { return g[1](x[0]); });
    if (!items.length) return;
    h += '<h4>' + g[0] + '</h4>';
    items.forEach(function (x) {
      var r = x[0], i = x[1], ok = r.status === 'pass';
      h += '<button class="scn" data-i="' + i + '" aria-pressed="false"><span class="mk' + (ok ? '' : ' fail') + (r.isControl ? ' ctrl' : '') + '" aria-hidden="true">' + (ok ? '✓' : '✕') + '</span><span><span class="scn-t">' + esc(r.title) + '</span><span class="scn-id">' + esc(r.id) + ' · ' + esc(r.variant) + '</span></span></button>';
    });
  });
  var pass = runs.filter(function (r) { return r.observed; }).length, ctrl = runs.filter(function (r) { return r.isControl && !r.observed; }).length;
  h += '<p class="suite">' + runs.length + ' recorded runs. ' + pass + ' observed their expected behavior' + (ctrl ? '; ' + ctrl + ' intentional byte-swap control' + (ctrl > 1 ? 's were' : ' was') + ' rejected, as designed' : '') + '.</p>';
  el.innerHTML = h;
  Array.prototype.forEach.call(el.querySelectorAll('.scn'), function (b) { b.addEventListener('click', function () { select(+b.dataset.i); }); });
}

function select(i) {
  stop(); S.sel = i; S.step = 0;
  Array.prototype.forEach.call(document.querySelectorAll('.scn'), function (b) { b.setAttribute('aria-pressed', String(+b.dataset.i === i)); });
  renderStage();
}

function renderStage() {
  var r = RUNS[S.dev][S.sel], ok = r.status === 'pass', a = primary(r), h = '';
  h += '<div class="verdict' + (ok ? '' : ' bad') + '"><div class="bigmk" aria-hidden="true">' + (ok ? '✓' : '✕') + '</div><div><div class="vh">' + (ok ? 'Expected behavior observed' : 'Rejected: expected behavior not observed') + '</div><div class="vp">' + esc(r.plain) + '</div>';
  if (r.isControl) h += '<span class="vc">This rejection is the point. The byte-swap variant is a negative control: if it ever passed, the checks would be broken.</span>';
  h += '</div></div>';
  if (a) {
    h += '<div class="xo"><div><div class="xl">Expected, from independent literal answers</div><div class="xv">' + esc(fmtC(a.expected)) + unitFor(a) + '</div><div class="xs">' + esc(a.assertion_id) + ' · cites ' + esc((a.fact_ids || []).join(', ')) + '</div></div>';
    h += '<div><div class="xl">Observed, from the driver</div><div class="xv' + (a.passed ? '' : ' bad') + '">' + esc(fmtC(a.actual)) + unitFor(a) + '</div><div class="xs">' + esc(r.exec) + ' · ' + esc(r.outcome) + ' · virtual end ' + us(r.meta.virtual_end_us) + '</div></div></div>';
  }
  h += '<div class="fh"><h3>Bus transactions</h3><span class="rec">Recorded · run ' + esc(String(r.runId).slice(0, 8)) + '</span></div>';
  h += '<div class="scope gridbg" id="scope"></div><div class="detail" id="detail"></div>';
  h += '<div class="ctl"><button class="btn" id="bPrev">Previous</button><button class="btn" id="bNext">Next</button><button class="btn solid" id="bPlay">Replay recorded trace</button><button class="btn" id="bAll">Show all</button><span class="stepread" id="stepRead"></span></div>';
  h += '<div class="sec" id="bb"></div>';
  h += '<details open><summary>Assertions (' + r.assertions.length + ')</summary>' + assertTable(r) + '</details>';
  h += '<details><summary>Full trace (' + r.events.length + ' events)</summary>' + traceTable(r) + '</details>';
  h += '<details><summary>Raw report JSON and limitations</summary><p style="margin-top:10px">' + esc(r.limits) + '</p><p><button class="btn" id="bDl">Download this run as JSON</button> <a class="btn" href="' + esc(r.dev.file) + '" download>Download full report file</a></p><pre class="json">' + esc(JSON.stringify(r.raw, null, 2)) + '</pre></details>';
  document.getElementById('stage').innerHTML = h;
  document.getElementById('bPrev').onclick = function () { stop(); go(S.step - 1); };
  document.getElementById('bNext').onclick = function () { stop(); go(S.step + 1); };
  document.getElementById('bAll').onclick = function () { stop(); go(r.groups.length - 1); };
  document.getElementById('bPlay').onclick = play;
  document.getElementById('bDl').onclick = function () { download(r); };
  Array.prototype.forEach.call(document.querySelectorAll('[data-seq]'), function (b) { b.addEventListener('click', function () { stop(); jumpToSeq(+b.dataset.seq); document.getElementById('scope').scrollIntoView({ block: 'nearest' }); }); });
  drawScope(r); go(0); renderBB(r);
}

function assertTable(r) {
  return '<div style="overflow-x:auto"><table class="tr"><thead><tr><th>assertion</th><th>expected</th><th>actual</th><th>passed</th><th>facts</th><th>trace steps</th></tr></thead><tbody>' + r.assertions.map(function (a) {
    var idx = a.trace_indices || [], shown = idx.length > 4 ? [idx[0], idx[idx.length - 1]] : idx;
    return '<tr class="' + (a.passed ? '' : 'f') + '"><td>' + esc(a.assertion_id) + '</td><td>' + esc(a.assertion_id === 'celsius' ? fmtC(a.expected) : a.expected) + '</td><td>' + esc(a.assertion_id === 'celsius' ? fmtC(a.actual) : a.actual) + '</td><td>' + a.passed + '</td><td>' + esc((a.fact_ids || []).join(', ')) + '</td><td>' + shown.map(function (s) { return '<button data-seq="' + s + '">' + s + '</button>'; }).join(idx.length > 4 ? ' to ' : ', ') + '</td></tr>';
  }).join('') + '</tbody></table></div>';
}
function traceTable(r) {
  return '<div style="overflow-x:auto"><table class="tr"><thead><tr><th>#</th><th>µs</th><th>addr</th><th>op</th><th>reg</th><th>sent</th><th>received</th><th>outcome</th><th>facts</th></tr></thead><tbody>' + r.events.map(function (e) {
    return '<tr class="' + (e.faulty ? 'f' : '') + '"><td>' + e.seq + '</td><td>' + Number(e.t).toLocaleString('en-US') + '</td><td>' + esc(e.addr) + '</td><td>' + esc(e.op) + '</td><td>' + esc(e.regStr) + '</td><td>' + esc(spaced(e.sent)) + '</td><td>' + esc(spaced(e.recv)) + '</td><td>' + esc(e.outcome) + '</td><td>' + esc(e.facts.join(' ')) + '</td></tr>';
  }).join('') + '</tbody></table></div>';
}

function cloud(x, y, w, h, r) {
  var nx = Math.max(3, Math.round(w / (2 * r))), ny = Math.max(2, Math.round(h / (2 * r))), sx = w / nx, sy = h / ny, d = 'M' + x + ' ' + y, i;
  for (i = 0; i < nx; i++) d += ' a' + sx / 2 + ' ' + sx / 2 + ' 0 0 1 ' + sx + ' 0';
  for (i = 0; i < ny; i++) d += ' a' + sy / 2 + ' ' + sy / 2 + ' 0 0 1 0 ' + sy;
  for (i = 0; i < nx; i++) d += ' a' + sx / 2 + ' ' + sx / 2 + ' 0 0 1 ' + (-sx) + ' 0';
  for (i = 0; i < ny; i++) d += ' a' + sy / 2 + ' ' + sy / 2 + ' 0 0 1 0 ' + (-sy);
  return d + 'Z';
}
var LN = { drv: 58, bus: 132, dev: 206 }, H = 268, X0 = 104, GAP = 30, POS = [];
function capLabel(e) {
  var l1 = (e.op === 'read' ? 'R ' : e.op === 'write' ? 'W ' : '') + e.regStr;
  var data = e.op === 'write' ? e.sent : e.recv;
  var l2 = spaced(data) || (e.faulty ? '' : 'no data');
  if (e.faulty) l2 = (l2 ? l2 + ' · ' : '') + String(e.outcome).replace(/_injected$/, '').replace(/^fault_/, '').replace(/_/g, ' ').toUpperCase();
  return [l1, l2];
}
function drawScope(r) {
  var g = r.groups, x = X0, fn = 0; POS = [];
  var widths = g.map(function (grp) { var L = capLabel(grp.first); return Math.max(110, Math.max(L[0].length, L[1].length) * 7.6 + 24); });
  widths.forEach(function (w) { POS.push(x + w / 2); x += w + GAP; });
  var W = x + 10;
  var s = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Recorded bus transactions for ' + esc(r.id) + '">';
  s += '<text class="lane-l" x="12" y="' + (LN.drv + 4) + '">Driver</text><text class="lane-l" x="12" y="' + (LN.bus + 4) + '">I²C bus</text><text class="lane-l" x="12" y="' + (LN.dev + 4) + '">Virtual ' + (r.dev.key === 'tmp117' ? 'TMP117' : 'BME280') + '</text>';
  ['drv', 'bus', 'dev'].forEach(function (k) { s += '<line class="lane" x1="' + (X0 - 14) + '" x2="' + W + '" y1="' + LN[k] + '" y2="' + LN[k] + '"/>'; });
  s += '<line class="cursor" id="cursor" x1="0" x2="0" y1="26" y2="' + (H - 8) + '"/>';
  g.forEach(function (grp, i) {
    var e = grp.first, cx = POS[i], w = widths[i], L = capLabel(e), n = grp.members.length;
    s += '<g class="col' + (e.faulty ? ' fault' : '') + '" data-g="' + i + '">';
    s += '<text class="tm" x="' + cx + '" y="18" text-anchor="middle">' + (n > 1 ? us(grp.first.t) + ' to ' + us(grp.last.t) : us(e.t)) + '</text>';
    s += '<line class="stem" x1="' + cx + '" x2="' + cx + '" y1="' + LN.drv + '" y2="' + LN.dev + '"/>';
    s += '<circle class="dot" cx="' + cx + '" cy="' + LN.drv + '" r="3.2"/><circle class="dot" cx="' + cx + '" cy="' + LN.dev + '" r="3.2"/>';
    if (e.faulty) { fn++; s += '<path class="cloud" d="' + cloud(cx - w / 2 - 12, LN.bus - 31, w + 24, 62, 7) + '"/>'; }
    s += '<rect class="cap" x="' + (cx - w / 2) + '" y="' + (LN.bus - 21) + '" width="' + w + '" height="42" rx="3"/>';
    s += '<text class="c1" x="' + cx + '" y="' + (LN.bus - 3) + '" text-anchor="middle">' + esc(L[0]) + '</text>';
    s += '<text class="c2" x="' + cx + '" y="' + (LN.bus + 13) + '" text-anchor="middle">' + esc(L[1]) + '</text>';
    if (n > 1) s += '<text class="ct" x="' + cx + '" y="' + (LN.drv - 12) + '" text-anchor="middle">×' + n + '</text>';
    if (e.faulty) {
      var tx = cx + w / 2 + 4, ty = LN.bus - 46;
      s += '<path class="delta" d="M' + tx + ' ' + (ty - 9) + ' L' + (tx + 10) + ' ' + (ty + 8) + ' L' + (tx - 10) + ' ' + (ty + 8) + 'Z"/><text class="dn" x="' + tx + '" y="' + (ty + 5) + '" text-anchor="middle">' + fn + '</text>';
      s += '<text class="fl" x="' + cx + '" y="' + (LN.dev + 32) + '" text-anchor="middle">fault injected here</text>';
    } else { var rn = r.dev.regs[e.reg]; if (rn) s += '<text class="tm" x="' + cx + '" y="' + (LN.dev + 30) + '" text-anchor="middle">' + esc(rn) + '</text>'; }
    s += '</g>';
  });
  s += '</svg>';
  var sc = document.getElementById('scope'); sc.innerHTML = s;
  Array.prototype.forEach.call(sc.querySelectorAll('.col'), function (c) { c.addEventListener('click', function () { stop(); go(+c.dataset.g); }); });
}
function jumpToSeq(seq) { var r = RUNS[S.dev][S.sel]; var gi = r.groups.findIndex(function (g) { return g.members.some(function (m) { return m.seq === seq; }); }); if (gi >= 0) go(gi); }
function go(n) {
  var r = RUNS[S.dev][S.sel], max = r.groups.length - 1; if (max < 0) return;
  S.step = Math.max(0, Math.min(max, n));
  Array.prototype.forEach.call(document.querySelectorAll('#scope .col'), function (c) { var i = +c.dataset.g; c.classList.toggle('future', i > S.step); c.classList.toggle('current', i === S.step); });
  var x = POS[S.step], cur = document.getElementById('cursor'); if (cur) { cur.setAttribute('x1', x); cur.setAttribute('x2', x); }
  var sc = document.getElementById('scope'); if (sc) sc.scrollTo({ left: Math.max(0, x - sc.clientWidth / 2), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  document.getElementById('stepRead').textContent = 'Step ' + (S.step + 1) + ' of ' + (max + 1);
  renderDetail(r, r.groups[S.step]);
}
function renderDetail(r, grp) {
  var e = grp.first, n = grp.members.length, rn = r.dev.regs[e.reg];
  var h = '<div><div class="dt">RECORDED STEP ' + (n > 1 ? grp.first.seq + ' TO ' + grp.last.seq : e.seq) + '</div><dl class="kv">';
  h += '<dt>Virtual time</dt><dd>' + (n > 1 ? us(grp.first.t) + ' to ' + us(grp.last.t) + ' (' + n + ' identical)' : us(e.t)) + '</dd>';
  h += '<dt>Address</dt><dd>' + esc(e.addr) + '</dd><dt>Operation</dt><dd>' + esc(e.op) + '</dd>';
  h += '<dt>Register</dt><dd>' + esc(e.regStr) + (rn ? ' · ' + esc(rn) : '') + '</dd>';
  h += '<dt>Sent</dt><dd>' + (e.sent ? esc(spaced(e.sent)) : 'none') + '</dd><dt>Received</dt><dd>' + (e.recv ? esc(spaced(e.recv)) : 'none') + '</dd>';
  h += '<dt>Outcome</dt><dd class="' + (e.faulty ? 'f' : '') + '">' + esc(e.outcome) + '</dd></dl></div>';
  h += '<div><div class="dt">RECORDED SOURCE FACTS FOR THIS STEP</div>';
  if (e.facts.length) {
    var doc = r.dev.contract.contract.source.document;
    h += '<ul class="facts">' + e.facts.map(function (id) { var f = r.dev.facts[id]; return '<li><span class="fid"><a href="' + esc(r.dev.cfile) + '">' + esc(id) + '</a> · ' + esc(doc) + ' ' + esc(factRef(f)) + '</span>' + esc(f ? f.claim : 'Fact not found in contract.') + '</li>'; }).join('') + '</ul>';
  } else h += '<p class="muted" style="margin:0">This step records no fact reference.</p>';
  h += '<p class="muted" style="margin:12px 0 0;font:12px var(--mono)">approved by ' + esc(r.prov.reviewer) + ' · ' + esc(String(r.prov.approved_utc).slice(0, 10)) + ' · contract ' + esc(String(r.prov.contract_sha256).slice(0, 12)) + '…</p></div>';
  document.getElementById('detail').innerHTML = h;
}
function play() {
  stop(); var r = RUNS[S.dev][S.sel]; if (S.step >= r.groups.length - 1) go(0);
  S.timer = setInterval(function () { if (S.step >= r.groups.length - 1) { stop(); return; } go(S.step + 1); }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 1400 : 950);
  document.getElementById('bPlay').textContent = 'Replaying recorded trace…';
}
function stop() { if (S.timer) { clearInterval(S.timer); S.timer = null; } var b = document.getElementById('bPlay'); if (b) b.textContent = 'Replay recorded trace'; }
function download(r) {
  var blob = new Blob([JSON.stringify(r.raw, null, 2)], { type: 'application/json' }), a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'drift_' + r.id + '_' + r.variant + '.json';
  document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

/* ---------------- section B-B: interpretation computed from recorded bytes ---------------- */
function tmpDecode(msb, lsb) { var u = (msb << 8) | lsb, s = u >= 0x8000 ? u - 0x10000 : u; return { word: u, signed: s, c: s / 128 }; }
function bmeTemp(cal, raw) {
  var T1 = cal[0] | (cal[1] << 8), T2 = cal[2] | (cal[3] << 8), T3 = cal[4] | (cal[5] << 8);
  if (T2 >= 0x8000) T2 -= 0x10000; if (T3 >= 0x8000) T3 -= 0x10000;
  var adc = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4);
  var v1 = Math.floor(((Math.floor(adc / 8) - T1 * 2) * T2) / 2048), d = Math.floor(adc / 16) - T1;
  var v2 = Math.floor((Math.floor((d * d) / 4096) * T3) / 16384), tf = v1 + v2, T = Math.floor((tf * 5 + 128) / 256);
  return { T1: T1, T2: T2, T3: T3, adc: adc, v1: v1, v2: v2, tf: tf, centi: T, c: T / 100 };
}
function bits8(b) { return ('0000000' + b.toString(2)).slice(-8).replace(/(\d{4})(\d{4})/, '$1 $2'); }
function tiles(bytes, need) {
  var h = '<div class="parts">';
  for (var i = 0; i < need; i++) h += i < bytes.length ? '<div class="part"><div class="h">' + ('0' + bytes[i].toString(16).toUpperCase()).slice(-2) + '</div><div class="b">' + bits8(bytes[i]) + '</div><div class="n">byte ' + (i + 1) + '</div></div>' : '<div class="part miss"><div class="h">??</div><div class="b">missing</div><div class="n">byte ' + (i + 1) + '</div></div>';
  return h + '</div>';
}
function renderBB(r) {
  var el = document.getElementById('bb'), a = r.assertions.find(function (x) { return x.assertion_id === 'celsius'; }), obs = a ? a.actual : null, h = '';
  if (r.dev.key === 'tmp117') {
    var e = r.events.filter(function (x) { return x.regStr === '0x00' && x.op === 'read'; }).pop(); if (!e) { el.innerHTML = ''; return; }
    var b = hexPairs(e.recv);
    h = '<div class="fh"><h3>Section B-B · the recorded bytes, two readings</h3><span class="rec">computed in your browser from step ' + e.seq + '</span></div><div class="bb gridbg">' + tiles(b, 2) + '<div class="reads">';
    if (b.length === 2) {
      var m = tmpDecode(b[0], b[1]), s = tmpDecode(b[1], b[0]);
      [['Datasheet order', 'first byte most significant (F02)', m, false], ['Reversed order', 'second byte treated as most significant', s, true]].forEach(function (row) {
        var d = row[2], match = obs !== null && Math.abs(d.c - obs) < 1e-9, cls = row[3] ? (match ? ' redl' : ' muted') : (match ? '' : ' muted');
        var note = match ? (row[3] ? 'what the byte-swap control reported' : 'what the driver reported') : row[1];
        h += '<div class="rd' + cls + '"><span class="lbl">' + row[0] + '<small>' + note + '</small></span><span class="f">0x' + ('000' + d.word.toString(16).toUpperCase()).slice(-4) + ' → ' + d.signed + ' × 1/128</span><span class="res">' + fmtC(d.c) + ' °C</span></div>';
      });
    } else h += '<div class="rd redl"><span class="lbl">Short response<small>one byte cannot form a 16-bit result</small></span><span class="f">driver raised ProtocolReadError</span><span class="res">error</span></div>';
    el.innerHTML = h + '</div></div>';
  } else {
    var ce = r.events.find(function (x) { return x.regStr === '0x88'; }), re = r.events.filter(function (x) { return x.regStr === '0xFA'; }).pop();
    if (!ce || !re) { el.innerHTML = ''; return; }
    var cal = hexPairs(ce.recv), raw = hexPairs(re.recv);
    h = '<div class="fh"><h3>Section B-B · compensation from the recorded bytes</h3><span class="rec">computed in your browser from steps ' + ce.seq + ' and ' + re.seq + '</span></div><div class="bb gridbg">' + tiles(raw, 3) + '<div class="reads">';
    if (raw.length === 3) {
      var t = bmeTemp(cal, raw);
      h += '<div class="rd"><span class="lbl">Calibration<small>little-endian, T2 and T3 signed (F03)</small></span><span class="f">' + spaced(ce.recv) + ' → ' + t.T1 + ', ' + t.T2 + ', ' + t.T3 + '</span><span class="res"></span></div>';
      h += '<div class="rd"><span class="lbl">Raw reading<small>20-bit, msb first (F04)</small></span><span class="f">adc_T = ' + t.adc + ' → t_fine ' + t.tf + '</span><span class="res"></span></div>';
      h += '<div class="rd' + (obs !== null && Math.abs(t.c - obs) < 1e-9 ? '' : ' redl') + '"><span class="lbl">Integer compensation<small>' + (obs !== null && Math.abs(t.c - obs) < 1e-9 ? 'matches what the driver reported' : 'differs from the driver') + ' (F05)</small></span><span class="f">' + t.centi + ' centidegrees</span><span class="res">' + t.c + ' °C</span></div>';
    } else h += '<div class="rd redl"><span class="lbl">Short response<small>' + raw.length + ' of 3 bytes received</small></span><span class="f">a 20-bit reading needs three bytes; driver raised ProtocolReadError</span><span class="res">error</span></div>';
    el.innerHTML = h + '</div></div>';
  }
}

/* ---------------- repair triad and diff ---------------- */
(function () {
  function find(id, v) { return RUNS.tmp117.find(function (r) { return r.id === id && r.variant === v; }); }
  function col(v, title, note, bad) {
    var rows = ['baseline_25c', 'baseline_neg1c'].map(function (id) {
      var r = find(id, v); if (!r) return '';
      var c = r.assertions.find(function (a) { return a.assertion_id === 'celsius'; }), rb = r.assertions.find(function (a) { return a.assertion_id === 'raw_bytes'; });
      return '<div class="row"><span class="by">' + spaced(rb.actual) + ' →</span><span class="val">' + fmtC(c.actual) + ' °C</span><span class="exp">expected ' + fmtC(c.expected) + ' °C · ' + (c.passed ? 'passes' : 'fails') + '</span></div>';
    }).join('');
    return '<div class="' + (bad ? 'bad' : '') + '"><div class="k"><span>' + esc(v) + '</span><span>' + note + '</span></div><h3>' + title + '</h3><div class="rows">' + rows + '</div></div>';
  }
  document.getElementById('triad').innerHTML =
    col('baseline', 'Reference driver', 'reads MSB first') +
    col('byte_swap', 'Intentional byte swap', 'kept as control', true) +
    col('repair_candidate', 'Bob\'s repair', 'same expectations');
  var lines = String(EV.repair_diff || '').replace(/\n$/, '').split('\n');
  document.getElementById('diff').innerHTML = lines.map(function (l) {
    var k = /^(---|\+\+\+)/.test(l) ? 'meta' : l[0] === '@' ? 'hunk' : l[0] === '-' ? 'del' : l[0] === '+' ? 'add' : '';
    return '<div class="' + k + '"><span>' + esc(k === 'del' || k === 'add' ? l.slice(1) : l) + '</span></div>';
  }).join('');
  var dl = document.getElementById('diffLink'); dl.href = EV.files.repair_diff; dl.setAttribute('download', '');
})();

/* ---------------- BME280 calculation sheet from recorded runs ---------------- */
(function () {
  var cols = ['bme280_25c', 'bme280_neg8c'].map(function (id) {
    var r = RUNS.bme280.find(function (x) { return x.id === id; }); if (!r) return '';
    var ce = r.events.find(function (x) { return x.regStr === '0x88'; }), re = r.events.filter(function (x) { return x.regStr === '0xFA'; }).pop();
    var t = bmeTemp(hexPairs(ce.recv), hexPairs(re.recv)), a = r.assertions.find(function (x) { return x.assertion_id === 'celsius'; });
    var vt = r.assertions.find(function (x) { return x.assertion_id === 'virtual_time_us'; });
    return '<table><tbody>' +
      '<tr><td>Run</td><td>' + esc(id) + '</td></tr>' +
      '<tr><td>Calibration bytes, step ' + ce.seq + '</td><td>' + spaced(ce.recv) + '</td></tr>' +
      '<tr><td>dig_T1; dig_T2, dig_T3 signed</td><td>' + t.T1 + '; ' + t.T2 + ', ' + t.T3 + '</td></tr>' +
      '<tr><td>Raw bytes, step ' + re.seq + '</td><td>' + spaced(re.recv) + ' → adc_T ' + t.adc + '</td></tr>' +
      '<tr><td>var1, var2, t_fine</td><td>' + t.v1 + ', ' + t.v2 + ', ' + t.tf + '</td></tr>' +
      '<tr><td>Conversion finished at</td><td>' + us(vt && vt.actual) + ' virtual</td></tr>' +
      '<tr class="res"><td>Recomputed here / driver reported</td><td>' + t.c + ' °C / ' + fmtC(a.actual) + ' °C</td></tr></tbody></table>';
  });
  var sr = RUNS.bme280.find(function (x) { return x.id === 'bme280_short_temp'; }), sre = sr && sr.events.filter(function (x) { return x.regStr === '0xFA'; }).pop();
  document.getElementById('bmeCalc').innerHTML = '<h3>Calculation sheet · recomputed from the recorded bytes</h3><p class="muted">Your browser reruns Bosch\'s 32-bit integer compensation on the bytes each run recorded, and compares the result with what the driver reported.</p><div class="cols">' + cols.join('') + '</div>' +
    (sre ? '<p style="margin:18px 0 0;font-size:15px"><b>Fault case:</b> in bme280_short_temp the driver requests three bytes from 0xFA and receives <code>' + spaced(sre.recv) + '</code>. It raises ' + esc(primary(sr).actual) + ', the expected behavior.</p>' : '');
})();

/* ---------------- register, title block, files ---------------- */
(function () {
  var nF = Object.keys(DEVICES.tmp117.facts).length, nB = Object.keys(DEVICES.bme280.facts).length;
  var obs = ALL.filter(function (r) { return r.observed; }).length, ctrl = ALL.filter(function (r) { return r.isControl && !r.observed; }).length;
  var REG = [
    ['312', 'Automated tests passed, plus 2 subtests, on the final build.', 'Kimberly\'s final Windows pytest run', 'blue', 'Measured'],
    [String(ALL.length), 'Recorded verification cases: ' + RUNS.tmp117.length + ' TMP117 and ' + RUNS.bme280.length + ' BME280.', 'from reports on this page', 'ink', 'Counted'],
    [String(obs), 'Cases where the expected behavior was observed, including every injected fault handled correctly.', 'from reports on this page', 'ink', 'Counted'],
    [String(ctrl), 'Intentional byte-swap controls rejected, as designed.', 'from reports on this page', 'ink', 'Counted'],
    [String(nF + nB), 'Page-cited datasheet facts in the approved contracts: ' + nF + ' TMP117, ' + nB + ' BME280.', 'from contracts on this page', 'ink', 'Counted'],
    ['2', 'Reviewed sensor profiles, each approved by name and bound to its PDF by SHA-256.', 'from contracts on this page', 'ink', 'Counted'],
    ['15', 'Recorded IBM Bob task sessions, screenshots in the repository.', 'bob_sessions/', 'ink', 'Counted'],
    ['65,536', 'Every TMP117 16-bit raw encoding decoded with zero arithmetic mismatches against a standard-library reference.', 'independent review snapshot · software only', 'sun', 'Supplementary'],
    ['1,300', '100 deterministic replays of all 13 scenarios with zero normalized report differences.', 'independent review snapshot · software only', 'sun', 'Supplementary'],
    ['n/a', 'Physical hardware accuracy, electrical timing, and engineering time saved.', 'outside this prototype', 'dash', 'Not measured']
  ];
  document.getElementById('regBody').innerHTML = REG.map(function (r) {
    return '<tr><td class="n">' + esc(r[0]) + '</td><td>' + esc(r[1]) + '<span class="src">' + esc(r[2]) + '</span></td><td><span class="stamp ' + r[3] + '">' + esc(r[4]) + '</span></td></tr>';
  }).join('');
  var t = DEVICES.tmp117.report.provenance, b = DEVICES.bme280.report.provenance;
  function hsh(s) { return esc(s); }
  document.getElementById('titleBlock').innerHTML =
    '<div class="r2"><span class="k">PROJECT</span><span class="big">DRIFT</span><span class="v" style="display:block;margin-top:6px;font-size:13px;color:var(--ink-2)">Datasheet-to-Driver Virtual Verification Lab</span></div>' +
    '<div class="apv"><span class="k">TMP117 PROFILE</span><span class="v m">' + esc(t.approved_profile_id) + '<br>' + esc(t.source_document) + '</span></div>' +
    '<div class="apv s2"><span class="k">TMP117 APPROVAL</span><span class="v">' + esc(t.reviewer) + ' · <span class="m">' + esc(t.approved_utc) + '</span></span><span class="v m" style="display:block">source ' + hsh(t.source_sha256) + '<br>contract ' + hsh(t.contract_sha256) + '</span></div>' +
    '<div class="apv"><span class="k">BME280 PROFILE</span><span class="v m">' + esc(b.approved_profile_id) + '<br>' + esc(b.source_document) + '</span></div>' +
    '<div class="apv s2"><span class="k">BME280 APPROVAL</span><span class="v">' + esc(b.reviewer) + ' · <span class="m">' + esc(b.approved_utc) + '</span></span><span class="v m" style="display:block">source ' + hsh(b.source_sha256) + '<br>contract ' + hsh(b.contract_sha256) + '</span></div>' +
    '<div><span class="k">SCOPE, SOURCE REVIEW, APPROVAL</span><span class="v">Kimberly Heard</span></div>' +
    '<div class="s2"><span class="k">ENGINEERING · IBM BOB</span><span class="v">Contract validation, interfaces, decoders, drivers, virtual sensors, faults, runners, reports, deterministic generators, integration fix, repair candidate</span></div>' +
    '<div><span class="k">EXECUTION AND VERDICTS</span><span class="v">Plain Python, no model at runtime</span></div>' +
    '<div class="s2"><span class="k">CHATGPT · CODEX</span><span class="v">Planning, final verification, five final checks, one BME280 short-read trace correction, documentation, presentation</span></div>' +
    '<div><span class="k">CLAUDE</span><span class="v">Workbench design, copy and review</span></div>' +
    '<div><span class="k">SHEET</span><span class="v m">07 of 07</span></div>';
  var files = [[EV.files.tmp117, 'TMP117 recorded runs'], [EV.files.bme280, 'BME280 recorded runs'], [EV.files.tmp117_contract, 'TMP117 approved contract'], [EV.files.bme280_contract, 'BME280 approved contract'], [EV.files.repair_diff, 'Repair patch']];
  document.getElementById('fileList').innerHTML = files.map(function (f) { return '<li><a href="' + esc(f[0]) + '" download><code>' + esc(f[0]) + '</code></a> · ' + f[1] + '</li>'; }).join('') +
    '<li><a href="https://github.com/KimberlyHeard/DRIFT/tree/main/generated">Generated drivers, models and manifests</a></li><li><a href="https://github.com/KimberlyHeard/DRIFT/tree/main/bob_sessions">IBM Bob task session screenshots</a></li>' +
    '<li>Datasheets: <a href="' + DEVICES.tmp117.datasheet + '">TI TMP117</a>, <a href="' + DEVICES.bme280.datasheet + '">Bosch BME280</a></li>';
})();

renderTabs(); renderSchedule(); select(0);
})();
