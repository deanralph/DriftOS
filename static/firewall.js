(() => {
  const el = id => document.getElementById(id);
  const control = el('firewall-switch');
  const refresh = el('firewall-refresh');
  let report = null;
  let busy = false;
  let uncertain = false;
  const allowed = new Set(['allow', 'accept', 'limit']);
  const blocked = new Set(['deny', 'drop', 'reject', 'block']);
  const notice = (message, error = false) => {
    el('firewall-notice').textContent = message;
    el('firewall-notice').hidden = !message;
    el('firewall-notice').classList.toggle('firewall-error', error);
  };
  function render(data) {
    report = data;
    el('firewall-setup').hidden = !data.setup_required;
    el('firewall-setup-command').textContent = data.setup_command || 'See Deployment → Firewall permissions.';
    el('firewall-name').textContent = data.name;
    el('firewall-installed').textContent = data.installed.length ? `Installed tools: ${data.installed.join(', ')}` : 'No supported firewall tools detected';
    const known = typeof data.active === 'boolean';
    const state = known ? data.active ? 'ACTIVE' : 'INACTIVE' : 'UNKNOWN';
    el('firewall-status').textContent = state;
    el('firewall-status').dataset.state = state.toLowerCase();
    control.checked = data.active === true;
    control.disabled = !data.can_toggle || busy || uncertain;
    el('firewall-switch-text').textContent = known ? data.active ? 'On' : 'Off' : 'Unavailable';
    const counts = {allowed: 0, blocked: 0, other: 0};
    for (const rule of data.rules) counts[allowed.has(rule.action) ? 'allowed' : blocked.has(rule.action) ? 'blocked' : 'other']++;
    for (const key of Object.keys(counts)) el(`firewall-${key}`).textContent = known ? counts[key] : '—';
    el('firewall-policy-scope').textContent = data.active === false ? 'NOT CURRENTLY ENFORCED' : 'CURRENT REPORT';
    const policies = el('firewall-policies'); policies.replaceChildren();
    if (!data.policies.length) policies.textContent = data.active === false ? 'No live default policies are reported while this manager is inactive.' : 'Default policies could not be determined. Check the full report and access notice.';
    for (const policy of data.policies) {
      const item = document.createElement('span'); item.className = 'ds-badge firewall-policy';
      item.textContent = `${policy.direction}: ${policy.action}`; policies.append(item);
    }
    const rows = el('firewall-rules'); rows.replaceChildren();
    for (const rule of data.rules) {
      const row = document.createElement('tr');
      for (const [index, text] of [rule.action.toUpperCase(), rule.direction, rule.target, [rule.source, rule.details].filter(Boolean).join(' · '), rule.scope].entries()) {
        const cell = document.createElement('td'); cell.textContent = text;
        if (index === 0) cell.className = allowed.has(rule.action) ? 'rule-allow' : blocked.has(rule.action) ? 'rule-block' : '';
        if (index === 3) cell.classList.add('firewall-rule-detail');
        row.append(cell);
      }
      rows.append(row);
    }
    if (!data.rules.length) {
      const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 5;
      cell.textContent = !known ? 'Rules are unavailable until status can be verified.' : data.active ? 'No explicit rule entries in this report. Default policies and manager-specific configuration still apply.' : 'No saved rule entries reported. This manager is inactive.';
      row.append(cell); rows.append(row);
    }
    el('firewall-rule-count').textContent = `${data.rules.length} REPORTED ENTRIES`;
    el('firewall-scope').textContent = `${data.scope} Counts are explicit entries, not ports or packet statistics. LIMIT rules are conditional allowances. Named services and complex rules require the full report for details.`;
    el('firewall-raw').textContent = data.raw || 'Report unavailable.';
    el('firewall-updated').textContent = `Checked ${new Date(data.sampled_at * 1000).toLocaleTimeString()}`;
    const warnings = [data.error, data.access_note];
    if (data.backend && !['ufw', 'firewalld'].includes(data.backend)) warnings.push('This ruleset is read-only; switching is supported for UFW and firewalld.');
    notice(warnings.filter(Boolean).join(' '), Boolean(data.error));
  }
  async function fetchReport() {
    if (busy) return;
    busy = true; control.disabled = true; refresh.disabled = true;
    try {
      const response = await fetch('/api/firewall', {cache:'no-store', signal:AbortSignal.timeout(45000)});
      if (response.status === 401) { location.assign('/login'); return; }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not read firewall status.');
      uncertain = false; busy = false; render(data);
    } catch (error) {
      uncertain = true;
      notice(`${error.message} Displayed data may be stale. Refresh before switching.`, true);
    } finally { busy = false; refresh.disabled = false; }
  }
  control.addEventListener('change', async () => {
    if (!report?.can_toggle || busy || uncertain) return;
    const enabled = control.checked;
    busy = true; control.disabled = true; refresh.disabled = true;
    notice(enabled ? 'Enabling firewall…' : 'Disabling firewall…');
    try {
      const body = new URLSearchParams({csrf:el('firewall-csrf').value, backend:report.backend, enabled:String(enabled), revision:report.revision});
      const response = await fetch('/api/firewall', {method:'POST', body, signal:AbortSignal.timeout(45000)});
      if (response.status === 401) { location.assign('/login'); return; }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not confirm firewall change.');
      busy = false; render(data);
      notice('Firewall state updated and verified.');
    } catch (error) {
      control.checked = report.active === true;
      uncertain = true;
      notice(`${error.message} Refresh to verify the current state; the request will not be retried automatically.`, true);
    } finally { busy = false; refresh.disabled = false; }
  });
  refresh.addEventListener('click', fetchReport);
  fetchReport();
})();
