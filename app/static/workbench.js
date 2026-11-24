(function () {
  var state = { payload: null, kind: 'bars', run: null, approved: false };
  var $ = function (id) { return document.getElementById(id); };
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }
  function setNotice(text) { $('notice').textContent = text || ''; }
  function renderIssues(data) {
    $('issue-count').textContent = data.issues.length + ' 条';
    $('issue-list').innerHTML = data.issues.length ? data.issues.map(function (item) {
      return '<li><span>' + esc(item.line || '-') + '</span><span>' + esc(item.key || '无主键') + '</span><code>' + esc(item.code) + '</code></li>';
    }).join('') : '<li class="empty">暂无异常</li>';
  }
  function renderRows(data) {
    var labels = Object.assign({label: '记录'}, state.resultColumns);
    var source = data.row_kind === 'source';
    var keys = source ? state.inputColumns : Object.keys(labels).filter(function (key) {
      return data.rows.some(function (row) { return Object.hasOwn(row, key); });
    });
    $('row-count').textContent = source ? data.rows.length + ' 行预览' :
      data.summary.PASS + ' 通过 / ' + data.summary.REVIEW + ' 复核 / ' + data.summary.REJECT + ' 阻断';
    var tail = source ? '' : '<th>结论</th>';
    $('row-head').innerHTML = '<tr>' + keys.map(function (key) { return '<th>' + esc(labels[key] || key) + '</th>'; }).join('') + tail + '</tr>';
    $('row-body').innerHTML = data.rows.length ? data.rows.map(function (row) {
      var values = keys.map(function (key) { return '<td class="' + (typeof row[key] === 'number' ? 'num' : '') + '">' + esc(row[key]) + '</td>'; }).join('');
      var verdict = source ? '' : '<td><span class="verdict" data-v="' + esc(row.verdict) + '">' + esc(row.verdict || '') + '</span><br><small>' + esc(row.reason || '') + '</small></td>';
      return '<tr>' + values + verdict + '</tr>';
    }).join('') : '<tr><td class="empty" colspan="' + (keys.length + (source ? 0 : 1)) + '">没有可展示条目</td></tr>';
  }
  function renderSigning(data) {
    var signing = data.signing;
    if (!signing) { $('signing-body').innerHTML = '<tr><td class="empty" colspan="6">运行对账后显示</td></tr>'; $('signing-count').textContent = '--'; return; }
    var totals = signing.totals;
    $('signing-count').textContent = totals.signed_tickets + ' 已签 / ' + totals.pending_tickets + ' 待签 / ' + totals.blocked_tickets + ' 阻断';
    $('signing-body').innerHTML = signing.tickets.map(function (item) {
      return '<tr><td>' + esc(item.ticket_id) + '</td>' +
        '<td><span class="verdict" data-v="' + esc(item.verdict) + '">' + esc(item.verdict) + '</span></td>' +
        '<td>' + esc(item.basis) + (item.hold_reason ? '<br><small>' + esc(item.hold_reason) + '</small>' : '') + '</td>' +
        '<td class="num">' + esc(item.due_cents) + '</td>' +
        '<td class="num">' + esc(item.signed_cents) + '</td>' +
        '<td><span class="verdict" data-v="' + (item.sign_state === 'SIGNED' ? 'PASS' : (item.sign_state === 'BLOCKED' ? 'REJECT' : 'REVIEW')) + '">' + esc(item.sign_state) + '</span></td></tr>';
    }).join('');
  }
  function renderLedger(data) {
    if (!data.ledger) { $('ledger-list').innerHTML = '<p class="empty">运行对账后显示</p>'; return; }
    var values = data.ledger;
    $('ledger-list').innerHTML = [
      ['来源行', values.counts.input], ['采信行', values.counts.accepted], ['隔离行', values.counts.isolated],
      ['精确重复', values.counts.duplicates], ['忽略行', values.counts.ignored], ['计算条目', values.counts.computed],
      ['团单净额(分)', values.net_total_cents]
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + esc(row[1]) + '</strong></div>'; }).join('') +
      '<div class="ledger-row"><span>' + esc(values.metric_field) + '</span><strong>' + esc(values.metric_total) + '</strong></div>' +
      values.checks.map(function (check) { return '<div class="ledger-row"><span>' + esc(check.label) + '</span><strong class="' + (check.ok ? 'check-ok' : 'check-bad') + '">' + (check.ok ? '通过' : '异常') + '</strong></div>'; }).join('');
  }
  function render(data) {
    state.payload = data;
    $('chart-label').textContent = Object.values(state.resultColumns)[0];
    $('m-input').textContent = data.counts.input;
    $('m-accepted').textContent = data.counts.accepted;
    $('m-isolated').textContent = data.counts.isolated + data.counts.duplicates;
    $('m-rejected').textContent = data.summary.REJECT;
    renderRows(data);
    renderIssues(data);
    renderLedger(data);
    renderSigning(data);
    window.renderChart($('chart'), data.chart && data.chart.length ? (state.kind || 'bars') : 'bars', data.chart || []);
  }
  function stageButtons(stages) {
    $('stage-nav').innerHTML = stages.map(function (stage, index) {
      return '<button type="button" data-stage="' + stage.id + '" aria-pressed="' + (index === 0 ? 'true' : 'false') + '">' + esc(stage.name) + '</button>';
    }).join('');
    Array.from(document.querySelectorAll('[data-stage]')).forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-stage]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
        loadStage(button.getAttribute('data-stage'));
      });
    });
  }
  async function loadStage(stage) {
    try {
      setNotice('');
      document.body.setAttribute('aria-busy', 'true');
      var payload = await request('/api/stages/' + stage, {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      render(payload);
    } catch (error) { setNotice(error.message); }
    finally { document.body.removeAttribute('aria-busy'); }
  }
  function syncRun(run) {
    state.run = run;
    state.approved = run.status === 'APPROVED';
    render(run);
    $('run-status').textContent = run.status + ' · rev ' + run.revision;
    $('revision').textContent = 'rev ' + run.revision;
    $('sign').disabled = run.summary.REJECT > 0 || state.approved;
    $('hold').disabled = state.approved;
    $('add-evidence').disabled = !state.run;
    $('download').hidden = !state.approved;
    if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
  }
  async function runBatch() {
    try {
      setNotice('');
      $('run').disabled = true;
      var run = await request('/api/runs', {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      syncRun(run);
    } catch (error) { setNotice(error.message); }
    finally { $('run').disabled = false; }
  }
  async function review(decision) {
    if (!state.run) return;
    try {
      var run = await request('/api/runs/' + state.run.run_id + '/review', {
        method: 'POST',
        body: JSON.stringify({decision: decision, comment: $('comment').value, expected_revision: state.run.revision})
      });
      syncRun(run);
    } catch (error) { setNotice(error.message); }
  }
  async function addEvidence() {
    if (!state.run) return;
    var text = $('supplement').value.trim();
    if (!text) { setNotice('请填写后补凭据 JSON'); return; }
    var evidence;
    try { evidence = JSON.parse(text); } catch (error) { setNotice('凭据 JSON 格式不正确'); return; }
    try {
      var data = await request('/api/runs/' + state.run.run_id + '/supplements', {
        method: 'POST',
        body: JSON.stringify({evidence: evidence, expected_revision: state.run.revision})
      });
      state.run = data.run;
      syncRun(state.run);
      var conflictIds = Object.keys(data.conflicts || {});
      setNotice(conflictIds.length ? '余款暂缓：' + conflictIds.join(', ') : '后补凭据已并入');
    } catch (error) { setNotice(error.message); }
  }
  async function boot() {
    try {
      var catalog = await request('/api/catalog');
      state.kind = catalog.chart;
      state.resultColumns = catalog.result_columns;
      state.inputColumns = catalog.columns;
      stageButtons(catalog.stages.slice(0, 5));
      document.querySelector('.rail-note').textContent = catalog.code + ' · ' + catalog.stages[6].name;
      await loadStage('intake');
    } catch (error) { setNotice(error.message); }
    $('run').addEventListener('click', runBatch);
    $('sign').addEventListener('click', function () { review('APPROVED'); });
    $('hold').addEventListener('click', function () { review('HELD'); });
    $('add-evidence').addEventListener('click', addEvidence);
    $('profile').addEventListener('change', function () {
      state.run = null; state.approved = false;
      $('sign').disabled = true; $('hold').disabled = true; $('add-evidence').disabled = true; $('download').hidden = true;
      $('run-status').textContent = '未执行批次'; $('revision').textContent = 'rev 0';
      loadStage('intake');
    });
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
