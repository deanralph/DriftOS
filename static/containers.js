'use strict';
(() => {
  const el = id => document.getElementById(`container-${id}`);
  let runtime = '', kind = 'containers', items = [], busy = false, generation = 0;
  const columns = {
    containers: [['name','Name'],['image','Image'],['state','State'],['status','Status'],['ports','Ports'],['networks','Networks']],
    images: [['name','Repository'],['tag','Tag'],['size','Size'],['created','Created']],
    volumes: [['name','Name'],['driver','Driver'],['scope','Scope']],
    networks: [['name','Name'],['driver','Driver'],['scope','Scope']]
  };
  const node = (tag, value, cls) => { const n = document.createElement(tag); n.textContent = value; if(cls) n.className = cls; return n; };
  async function api(path, options) {
    const response = await fetch(`/api/containers/${path}`, options);
    if (response.status === 401) { location.assign('/login'); throw Error('Sign in required.'); }
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Runtime request failed.');
    return data;
  }
  function lock(value) {
    busy = value;
    el('refresh').disabled = value;
    el('runtime').disabled = value || !el('runtime').options.length;
    document.querySelectorAll('#container-tabs button, #container-body button').forEach(b => b.disabled = value);
  }
  function render() {
    el('head').replaceChildren(); el('body').replaceChildren();
    const header = document.createElement('tr');
    columns[kind].forEach(([, label]) => header.append(node('th', label)));
    if(kind === 'containers') header.append(node('th','Actions'));
    el('head').append(header);
    const query = el('search').value.toLowerCase();
    const filtered = items.filter(item => Object.values(item).join(' ').toLowerCase().includes(query));
    filtered.forEach(item => {
      const row = document.createElement('tr');
      columns[kind].forEach(([key]) => row.append(node('td',item[key] || '—')));
      if(kind === 'containers') {
        const cell = document.createElement('td'); cell.className = 'container-actions';
        const state = item.state.toLowerCase();
        const verbs = state === 'running' ? ['stop','restart','logs'] : ['created','exited','stopped','configured','initialized'].includes(state) ? ['start','logs'] : ['logs'];
        verbs.forEach(verb => {
          const button = node('button', verb[0].toUpperCase()+verb.slice(1), 'ds-button ds-button--secondary ds-button--compact');
          button.disabled = busy; button.addEventListener('click', () => operate(item,verb)); cell.append(button);
        });
        row.append(cell);
      }
      el('body').append(row);
    });
    el('empty').hidden = filtered.length > 0;
    el('empty').textContent = items.length ? 'No matches.' : `No ${kind} found.`;
  }
  async function load() {
    if (!runtime || busy) return;
    const requestGeneration = ++generation;
    lock(true); items = []; if(kind === 'containers') el('summary').replaceChildren(); render(); el('empty').textContent = 'Loading inventory…';
    el('notice').textContent = 'Reading local runtime inventory…';
    try {
      const data = await api(`${runtime}/inventory/${kind}`);
      if(requestGeneration !== generation) return;
      items = data.items; render();
      if(kind === 'containers') {
        el('summary').replaceChildren();
        const running = items.filter(i => i.state.toLowerCase() === 'running').length;
        [['Total containers',items.length],['Running',running],['Other states',items.length-running]].forEach(([label,count]) => {
          const card = node('div','', 'ds-panel'); card.append(node('span',label,'ds-label'),node('strong',String(count))); el('summary').append(card);
        });
      }
      el('notice').textContent = `Updated ${new Date().toLocaleTimeString()} · ${runtime === 'docker' ? 'Docker' : 'Podman'}`;
    } catch(error) { el('notice').textContent = error.message; el('empty').textContent = 'Inventory unavailable.'; }
    finally { lock(false); }
  }
  async function detect() {
    if(busy) return;
    lock(true); el('logs').hidden = true; el('summary').replaceChildren(); items=[];render();
    try {
      const data = await api('runtimes');
      const previous = runtime;
      el('runtime').replaceChildren();
      data.runtimes.forEach(r => { const option = node('option',`${r.id === 'docker' ? 'Docker' : 'Podman'} · ${r.available ? 'Connected' : r.installed ? 'Unavailable' : 'Not installed'}`); option.value=r.id; option.disabled=!r.available; el('runtime').append(option); });
      const selected = data.runtimes.find(r => r.id===previous && r.available) || data.runtimes.find(r => r.available);
      runtime = selected?.id || ''; el('runtime').value = runtime;
      el('connection').textContent = selected ? `${selected.id === 'docker' ? 'Docker' : 'Podman'} ${selected.version}` : 'No runtime connected';
      el('notice').textContent = selected ? 'Connected' : data.runtimes.map(r => `${r.id}: ${r.message}`).join(' · ');
      if(!selected) el('empty').textContent='Start a local runtime and verify this Linux account can access it, then refresh.';
    } catch(error) { runtime='';el('notice').textContent=error.message;el('connection').textContent='Connection unavailable'; }
    finally {lock(false);}
    await load();
  }
  async function operate(item,verb) {
    if(busy) return;
    if(verb !== 'logs') {
      el('confirm-title').textContent = `${verb[0].toUpperCase()+verb.slice(1)} container?`;
      el('confirm-message').textContent = `${item.name} · ${runtime}. ${verb === 'start' ? 'This starts the container using its existing configuration.' : 'This can interrupt services using this container.'}`;
      el('confirm').returnValue='cancel'; el('confirm').showModal();
      const accepted = await new Promise(resolve => el('confirm').addEventListener('close',()=>resolve(el('confirm').returnValue==='confirm'),{once:true}));
      if(!accepted) return;
    }
    lock(true);
    let succeeded = false;
    try {
      const path = `${runtime}/${item.id}/${verb}`;
      const data = await api(path, verb === 'logs' ? undefined : {method:'POST',body:new URLSearchParams({csrf:el('csrf').value})});
      succeeded = true;
      if(verb === 'logs') {
        el('logs').hidden=false;el('log-title').textContent=`Logs · ${item.name}`;el('log-limit').textContent=data.limit;el('log-output').textContent=data.log || 'No log output.';el('logs').scrollIntoView({behavior:'smooth',block:'start'});
      } else {el('notice').textContent=data.message;}
    } catch(error) {el('notice').textContent=error.message;}
    finally {lock(false);}
    if(verb !== 'logs' && succeeded) await load();
  }
  el('refresh').addEventListener('click',detect);
  el('runtime').addEventListener('change',()=>{runtime=el('runtime').value;el('logs').hidden=true;el('summary').replaceChildren();el('connection').textContent=runtime === 'docker' ? 'Docker connected' : 'Podman connected';load();});
  el('search').addEventListener('input',render);
  document.querySelectorAll('#container-tabs button').forEach(button=>button.addEventListener('click',()=>{
    if(busy)return;kind=button.dataset.kind;
    document.querySelectorAll('#container-tabs button').forEach(b=>{b.setAttribute('aria-pressed',String(b===button));b.classList.toggle('ds-button--secondary',b!==button);});load();
  }));
  el('log-close').addEventListener('click',()=>el('logs').hidden=true);
  detect();
})();
