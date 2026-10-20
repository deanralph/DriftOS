const el = id => document.getElementById(id);
const bytes = n => { const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']; let i = 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return `${n.toFixed(i > 1 ? 1 : 0)} ${units[i]}`; };
const set = (id, value) => { el(id).textContent = value; };
let busy = false;
async function refresh() {
  if (busy) return;
  busy = true; el('refresh').disabled = true;
  try {
    const response = await fetch('/api/stats', {cache: 'no-store', signal: AbortSignal.timeout(10000)});
    if (response.status === 401) { location.assign('/login'); return; }
    if (!response.ok) throw new Error('Metrics unavailable');
    const data = await response.json();
    set('hostname', data.hostname); set('system', `${data.os} · ${data.kernel}`);
    const days = Math.floor(data.uptime / 86400), hours = Math.floor(data.uptime % 86400 / 3600), minutes = Math.floor(data.uptime % 3600 / 60);
    set('uptime', `${days}d ${hours}h ${minutes}m`);
    set('cpu', data.cpu.percent.toFixed(1)); el('cpu-bar').value = data.cpu.percent;
    set('cpu-detail', `${data.cpu.cores ?? '—'} cores / ${data.cpu.threads} threads${data.cpu.frequency ? ` · ${(data.cpu.frequency / 1000).toFixed(2)} GHz` : ''}`);
    set('load', data.cpu.load.map(n => n.toFixed(2)).join(' / '));
    set('ram', data.memory.percent.toFixed(1)); el('ram-bar').value = data.memory.percent;
    set('ram-detail', `${bytes(data.memory.used)} used of ${bytes(data.memory.total)}`); set('ram-free', bytes(data.memory.available));
    const root = data.drives.find(d => d.mount === '/');
    set('storage', root ? root.percent.toFixed(1) : '—'); el('storage-bar').value = root?.percent ?? 0;
    set('storage-detail', root ? `${bytes(root.used)} used of ${bytes(root.total)}` : 'Root filesystem unavailable'); set('storage-free', root ? bytes(root.free) : '—');
    el('drives').replaceChildren();
    for (const drive of data.drives) {
      const tr = document.createElement('tr');
      const cell = text => { const td = document.createElement('td'); td.textContent = text; tr.append(td); return td; };
      const device = cell('');
      for (const [cls, text] of [['drive-device', drive.device], ['drive-mount', drive.mount]]) { const span = document.createElement('span'); span.className = cls; span.textContent = text; device.append(span); }
      cell(drive.filesystem); cell(bytes(drive.total)); const usage = cell(''); usage.className = 'usage-cell';
      const label = document.createElement('span'); label.textContent = `${drive.percent.toFixed(1)}% · ${bytes(drive.used)} used`;
      const bar = document.createElement('progress'); bar.max = 100; bar.value = drive.percent; bar.setAttribute('aria-label', `${drive.mount} usage`); usage.append(label, bar);
      cell(bytes(drive.free)); el('drives').append(tr);
    }
    if (!data.drives.length) { const tr = document.createElement('tr'); const td = document.createElement('td'); td.colSpan = 5; td.textContent = 'No accessible mounted filesystems found.'; tr.append(td); el('drives').append(tr); }
    set('drive-count', `${data.drives.length} MOUNTED VOLUMES`); set('connection', '● CONNECTED');
    set('updated', `Updated ${new Date(data.sampled_at * 1000).toLocaleTimeString()}`); el('notice').hidden = true;
  } catch (error) {
    set('connection', '○ DISCONNECTED'); set('notice', 'Could not refresh server data. Displayed values may be stale. Retrying every 5 seconds.'); el('notice').hidden = false;
  } finally { busy = false; el('refresh').disabled = false; }
}
el('refresh').addEventListener('click', refresh);
refresh(); setInterval(refresh, 5000);
