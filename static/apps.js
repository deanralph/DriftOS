(() => {
  const el = id => document.getElementById(id);
  let report = null, job = null, busy = false, uncertain = false, pollTimer = null;
  const running = state => ['queued', 'running', 'unknown'].includes(state);
  const notice = (text, error = false) => {
    el('apps-notice').textContent = text; el('apps-notice').hidden = !text;
    el('apps-notice').classList.toggle('firewall-error', error);
  };
  function node(tag, cls, text) {
    const item = document.createElement(tag); if (cls) item.className = cls;
    if (text !== undefined) item.textContent = text; return item;
  }
  function renderCards() {
    if (!report) return;
    const search = el('apps-search').value.trim().toLowerCase(), filter = el('apps-filter').value;
    const grid = el('apps-grid'); grid.replaceChildren();
    const items = report.apps.filter(app => `${app.name} ${app.category} ${app.description}`.toLowerCase().includes(search) &&
      (filter === 'all' || filter === 'installed' && app.installed === true || filter === 'available' && app.installed === false));
    for (const app of items) {
      const card = node('article', 'ds-panel app-card');
      const header = node('div', 'app-card-header');
      header.append(node('span', 'app-icon', app.icon), node('span', 'ds-badge', app.installed === true ? 'INSTALLED' : app.installed === false ? 'NOT INSTALLED' : 'UNKNOWN'));
      card.append(header, node('span', 'ds-label', app.category), node('h2', '', app.name), node('p', 'app-description', app.description));
      if (app.note) card.append(node('p', 'app-package-note', app.note));
      const metadata = node('div', 'app-metadata');
      metadata.append(node('code', '', app.package || 'Unsupported OS'), node('span', '', app.version || ''));
      card.append(metadata);
      const footer = node('div', 'app-card-footer');
      if (app.installed === true) {
        if (app.command) { const command = node('code', 'app-command', app.command); footer.append(command); }
        else footer.append(node('span', 'ds-text-muted', 'Installed · service configuration is separate'));
        if (app.command) { const link = node('a', 'ds-link', 'Open terminal ↗'); link.href = '/terminal'; footer.append(link); }
      } else {
        const button = node('button', 'ds-button ds-button--compact', ['queued', 'running'].includes(job?.state) && job?.app === app.id ? 'Installing…' : `Install ${app.name}`);
        button.type = 'button'; button.disabled = app.installed !== false || !report.can_install || busy || uncertain || running(job?.state);
        button.addEventListener('click', () => install(app)); footer.append(button);
      }
      card.append(footer); grid.append(card);
    }
    if (!items.length) grid.append(node('p', 'ds-text-muted', 'No tools match this filter.'));
  }
  function renderJob(data) {
    job = data; el('apps-job').hidden = false;
    const appName = report?.apps.find(app => app.id === data.app)?.name || data.app;
    el('apps-job-title').textContent = `Installation · ${appName}`;
    el('apps-job-state').textContent = data.state.toUpperCase();
    el('apps-job-state').dataset.state = data.state;
    el('apps-job-message').textContent = data.message;
    el('apps-job-log').textContent = data.log || 'Waiting for installer output…';
    renderCards();
  }
  async function request(url, options = {}) {
    const response = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(45000), ...options});
    if (response.status === 401) { location.assign('/login'); throw new Error('Sign in required.'); }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'App operation failed.');
    return data;
  }
  async function pollJob(id) {
    clearTimeout(pollTimer);
    try {
      const data = await request(`/api/apps/jobs/${id}`); renderJob(data);
      if (['queued', 'running'].includes(data.state)) pollTimer = setTimeout(() => pollJob(id), 2000);
      else {
        uncertain = data.state === 'unknown';
        await refresh();
      }
    } catch (error) {
      uncertain = true; notice(`${error.message} The installation may still be running. Refresh to recover its status.`, true); renderCards();
    }
  }
  async function refresh() {
    if (busy) return;
    el('apps-refresh').disabled = true;
    try {
      const data = await request('/api/apps'); report = data; uncertain = false;
      el('apps-os').textContent = data.os; el('apps-manager').textContent = data.manager || 'Unsupported';
      el('apps-installed').textContent = `${data.apps.filter(app => app.installed === true).length} / ${data.apps.length}`;
      el('apps-setup').hidden = !data.setup_required;
      el('apps-setup-command').textContent = data.setup_command || '';
      el('apps-updated').textContent = `Checked ${new Date(data.sampled_at * 1000).toLocaleTimeString()}`;
      job = data.jobs?.find(item => running(item.state)) || data.jobs?.[0] || null;
      if (job) {
        renderJob(job);
        if (['queued','running'].includes(job.state)) {
          clearTimeout(pollTimer); pollTimer = setTimeout(() => pollJob(job.id), 2000);
        }
      }
      notice(data.error || (job?.state === 'unknown' ? 'An installation needs administrator review. Check its job report before retrying.' : ''), Boolean(data.error));
      renderCards();
    } catch (error) { uncertain = true; notice(`${error.message} Refresh before installing.`, true); renderCards(); }
    finally { el('apps-refresh').disabled = false; }
  }
  async function install(app) {
    if (busy || uncertain || running(job?.state)) return;
    busy = true; renderCards(); notice(`Starting installation of ${app.name}…`);
    try {
      const body = new URLSearchParams({csrf:el('apps-csrf').value, app:app.id, manager:report.manager});
      const data = await request('/api/apps/install', {method:'POST', body});
      renderJob(data); el('apps-job').scrollIntoView({block:'nearest'}); notice('Installation submitted. Leaving this page does not cancel it.');
      busy = false; await pollJob(data.id);
    } catch (error) {
      busy = false; uncertain = true;
      notice(`${error.message} Refresh before trying again; the request will not be retried automatically.`, true);
    } finally { busy = false; renderCards(); }
  }
  el('apps-search').addEventListener('input', renderCards);
  el('apps-filter').addEventListener('change', renderCards);
  el('apps-refresh').addEventListener('click', refresh);
  refresh();
})();
