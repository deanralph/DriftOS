'use strict';
(() => {
  const el = id => document.getElementById(`shares-${id}`);
  const node = (tag,text,cls) => {const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  let report=null,busy=false,userAction='create';
  function status(message){el('notice').textContent=message;}
  function lock(value){
    busy=value;
    document.querySelectorAll('.shares-page button').forEach(button=>button.disabled=value);
    el('add').disabled=value || !report?.privileged;
    el('add-user').disabled=value || !report?.privileged || !report?.services.smb.installed;
    if(!value)document.querySelectorAll('[data-start-disabled]').forEach(button=>button.disabled=true);
    if(!report)document.querySelectorAll('.shares-page button:not(#shares-refresh)').forEach(button=>button.disabled=true);
  }
  async function api(operation='',body){
    const response=await fetch(`/api/shares${operation ? '/'+operation : ''}`,body?{method:'POST',body}:undefined);
    if(response.status===401){location.assign('/login');throw Error('Sign in required.');}
    const data=await response.json();if(!response.ok)throw Error(data.error || 'Share request failed.');return data;
  }
  function payload(values){
    const body=new URLSearchParams({csrf:el('csrf').value,revision:report.revision});
    Object.entries(values).forEach(([key,value])=>{if(Array.isArray(value))value.forEach(v=>body.append(key,v));else body.set(key,String(value));});
    return body;
  }
  async function load(message){
    if(busy)return;
    lock(true);
    try{report=await api();render();status(message || report.note || 'Share report updated.');}
    catch(error){report=null;status(error.message);}
    finally{lock(false);}
  }
  function button(text,handler){const b=node('button',text,'ds-button ds-button--secondary ds-button--compact');b.type='button';b.addEventListener('click',handler);return b;}
  function render(){
    el('services').replaceChildren();
    for(const protocol of ['smb','nfs']){
      const s=report.services[protocol];const card=node('section','','ds-panel shares-service');
      card.append(node('span',protocol.toUpperCase(),'ds-label'),node('h2',!s.installed?'Not installed':s.active?'Active':'Inactive'));
      card.append(node('p',s.service || 'No supported systemd service detected','ds-text-muted'));
      if(protocol==='smb' && report.privileged && s.installed && !s.linked)card.append(node('p','Managed include needs administrator configuration.','ds-text-muted'));
      const start=button(s.active?'Running':'Start service',()=>startService(protocol));
      if(!report.privileged || !s.installed || !s.service || s.active || (protocol==='smb' && s.linked===false))start.dataset.startDisabled='true';
      card.append(start);el('services').append(card);
    }
    el('setup').hidden=!report.setup_required && !(report.privileged && report.services.smb.installed && report.services.smb.linked===false);
    el('setup-command').hidden=!report.setup_command;
    el('setup-command').textContent=report.setup_command || '';
    el('list').replaceChildren();
    report.shares.forEach(share=>{
      const tr=document.createElement('tr');const first=document.createElement('td');first.append(node('strong',share.protocol==='smb'?`ds_${share.name}`:share.name),node('small',`${report.root}/${share.name}`,'ds-text-muted'));tr.append(first);
      tr.append(node('td',share.protocol.toUpperCase()),node('td',share.read_only?'Read only':'Read / write'),node('td',(share.protocol==='smb'?share.users.map(u=>'ds_u_'+u):share.clients).join(', ')),node('td',share.enabled?'Enabled':'Disabled'));
      const actions=node('td','');actions.append(button('Edit',()=>openShare(share)));tr.append(actions);el('list').append(tr);
    });el('empty').hidden=report.shares.length>0;
    el('users').replaceChildren();
    report.users.forEach(user=>{
      const tr=document.createElement('tr');const first=node('td','');first.append(node('strong',user.name),node('small',user.account,'ds-text-muted'));tr.append(first,node('td',user.pending?'Needs password':user.enabled?'Enabled':'Disabled'));
      tr.append(node('td',report.shares.filter(s=>s.protocol==='smb' && s.users.includes(user.name)).map(s=>'ds_'+s.name).join(', ') || '—'));
      const actions=node('td','','shares-user-actions');actions.append(button('Set password',()=>openUser(user)));
      if(!user.pending)actions.append(button(user.enabled?'Disable':'Enable',()=>toggleUser(user)));
      tr.append(actions);el('users').append(tr);
    });el('users-empty').hidden=report.users.length>0;
  }
  function protocolFields(){const smb=el('protocol').value==='smb';el('user-field').hidden=!smb;el('client-field').hidden=smb;el('clients').required=!smb;preview();}
  function preview(){const name=el('name').value || '…';el('path').textContent=`Folder: /srv/driftos-shares/${name}${el('protocol').value==='smb' ? ` · SMB share: ds_${name}` : ''}`;}
  function openShare(share){
    el('form').reset();el('form-error').hidden=true;el('editor-title').textContent=share?'Edit share':'Add share';
    el('name').value=share?.name || '';el('name').readOnly=Boolean(share);
    el('protocol').value=share?.protocol || (report.services.smb.installed?'smb':'nfs');el('protocol').disabled=Boolean(share);
    el('access').value=String(share?.read_only ?? true);el('enabled').checked=share?.enabled ?? true;el('clients').value=share?.clients.join(', ') || '';
    el('user-options').replaceChildren();
    report.users.filter(u=>!u.pending).forEach(user=>{const label=node('label','','shares-check');const check=document.createElement('input');check.type='checkbox';check.value=user.name;check.checked=share?.users.includes(user.name) || false;label.append(check,node('span',`ds_u_${user.name}${user.enabled?'':' (disabled)'}`));el('user-options').append(label);});
    if(!el('user-options').children.length)el('user-options').append(node('p','Add a share user first.'));
    protocolFields();el('editor').showModal();
  }
  function clearPasswords(){el('password').value='';el('password-confirm').value='';}
  function openUser(user){
    userAction=user?'password':'create';el('user-form').reset();el('user-error').hidden=true;
    el('user-title').textContent=user?'Set SMB password':'Add share user';el('user-name').value=user?.name || '';el('user-name').readOnly=Boolean(user);
    el('account-preview').textContent=`SMB login: ds_u_${user?.name || '…'} · No Linux password or shell access`;
    el('user-editor').showModal();
  }
  async function confirm(title,message){
    el('confirm-title').textContent=title;el('confirm-message').textContent=message;el('confirm').returnValue='cancel';el('confirm').showModal();
    return await new Promise(resolve=>el('confirm').addEventListener('close',()=>resolve(el('confirm').returnValue==='confirm'),{once:true}));
  }
  async function mutate(operation,values){
    if(busy)return;
    lock(true);let message;
    try{const data=await api(operation,payload(values));message=data.message;}
    catch(error){status(error.message);return;}
    finally{lock(false);}
    await load(message);
  }
  async function toggleUser(user){
    if(await confirm(`${user.enabled?'Disable':'Enable'} SMB user?`,`ds_u_${user.name}: this changes future SMB logins. Existing sessions may remain connected. Linux login and NFS access are unaffected.`))await mutate('user',{name:user.name,action:user.enabled?'disable':'enable'});
  }
  async function startService(protocol){
    if(await confirm(`Start ${protocol.toUpperCase()}?`,'Starting the server makes its configured shares available, including existing shares outside DriftOS. This does not open firewall ports or enable the service at boot.'))await mutate('start',{protocol});
  }
  el('form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    const values={name:el('name').value,protocol:el('protocol').value,read_only:el('access').value,enabled:el('enabled').checked,clients:el('clients').value,users:[...el('user-options').querySelectorAll('input:checked')].map(input=>input.value)};
    if(values.protocol==='smb' && !values.users.length){el('form-error').textContent='Select at least one SMB user.';el('form-error').hidden=false;return;}
    lock(true);let message;
    try{const data=await api('share',payload(values));message=data.message;el('editor').close();}
    catch(error){el('form-error').textContent=error.message;el('form-error').hidden=false;return;}
    finally{lock(false);}
    await load(message);
  });
  el('user-form').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;
    if(el('password').value!==el('password-confirm').value){el('user-error').textContent='Passwords do not match.';el('user-error').hidden=false;return;}
    const body=payload({name:el('user-name').value,action:userAction,password:el('password').value});clearPasswords();
    lock(true);let message;
    try{const data=await api('user',body);message=data.message;el('user-editor').close();}
    catch(error){el('user-error').textContent=error.message+' Re-enter the password before trying again.';el('user-error').hidden=false;return;}
    finally{body.delete('password');lock(false);}
    await load(message);
  });
  document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>document.getElementById(button.dataset.close).close()));
  document.querySelectorAll('.shares-dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();}));
  el('user-editor').addEventListener('close',clearPasswords);
  el('refresh').addEventListener('click',()=>load());el('add').addEventListener('click',()=>openShare());el('add-user').addEventListener('click',()=>openUser());
  el('protocol').addEventListener('change',protocolFields);el('name').addEventListener('input',preview);
  el('user-name').addEventListener('input',()=>el('account-preview').textContent=`SMB login: ds_u_${el('user-name').value || '…'} · No Linux password or shell access`);
  load();
})();
