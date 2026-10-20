(() => {
  const el = id => document.getElementById(id);
  let sessionEnded = false;
  let folder = null, busy = false, requestNumber = 0, processing = false, dragDepth = 0, pickerTarget = null, mkdirTarget = null;
  const queue = [];
  const bytes = size => {
    const units = ['B','KiB','MiB','GiB','TiB']; let i=0;
    while (size >= 1024 && i < units.length-1) { size/=1024; i++; }
    return `${size.toFixed(i ? 1 : 0)} ${units[i]}`;
  };
  function node(tag, cls, text) {
    const item=document.createElement(tag); if(cls) item.className=cls;
    if(text !== undefined) item.textContent=text; return item;
  }
  function notice(message, error=false) {
    el('files-notice').textContent=message; el('files-notice').hidden=!message;
    el('files-notice').classList.toggle('firewall-error',error);
  }
  const target = () => folder && !busy && folder.writable ? {path:folder.path, id:folder.folder_id, display:folder.actual_path, max:folder.max_upload_bytes} : null;
  async function api(url, options={}) {
    const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30000),...options});
    if(response.status===401) { location.assign('/login'); throw new Error('Sign in required.'); }
    const data=await response.json(); if(!response.ok) throw new Error(data.error || 'File operation failed.'); return data;
  }
  function renderRows() {
    if(!folder) return;
    const tbody=el('files-entries'); tbody.replaceChildren();
    const text=el('files-search').value.toLowerCase();
    const items=folder.entries.filter(entry => entry.name.toLowerCase().includes(text));
    for(const entry of items) {
      const row=node('tr');
      const name=node('td');
      const icon=node('span','files-entry-icon',entry.type==='folder'?'▰':entry.type==='link'?'↗':entry.type==='file'?'▱':'◇');
      name.append(icon);
      if(entry.type==='folder') { const button=node('button','files-folder-link',entry.name); button.type='button'; button.disabled=busy; button.addEventListener('click',()=>load(entry.path)); name.append(button); }
      else name.append(node('span','',entry.name));
      if(entry.type==='link'||entry.type==='special') name.append(node('span','ds-badge files-type',entry.type==='link'?'LINK':'SPECIAL'));
      const modified=new Date(entry.modified*1000).toLocaleString();
      row.append(name,node('td','files-size',entry.size===null?'—':bytes(entry.size)),node('td','files-modified',modified),node('td','files-permissions',entry.permissions));
      const action=node('td');
      if(entry.type==='file') { const download=node('a','ds-link','Download'); download.href=`/api/files/download?${new URLSearchParams({path:entry.path})}`; download.setAttribute('aria-label',`Download ${entry.name}`); action.append(download); }
      row.append(action); tbody.append(row);
    }
    el('files-empty').hidden=items.length>0;
    el('files-empty').textContent=folder.entries.length?'No filenames match this filter.':folder.writable?'No files in this folder. Drop files here to upload.':'No visible files in this folder.';
  }
  function render() {
    el('files-path').value=folder.path;
    el('files-location').textContent=folder.actual_path;
    const crumbs=el('files-breadcrumbs'); crumbs.replaceChildren();
    const root=node('button','ds-link','/'); root.type='button'; root.addEventListener('click',()=>load('/')); crumbs.append(root);
    let path='';
    for(const [index,name] of folder.path.split('/').filter(Boolean).entries()) {
      path+='/'+name; const destination=path;
      if(index>0)crumbs.append(node('span','','/')); const button=node('button','ds-link',name); button.type='button'; button.addEventListener('click',()=>load(destination)); crumbs.append(button);
    }
    el('files-up').disabled=!folder.parent;
    el('files-upload').disabled=!folder.writable;
    el('files-new-folder').disabled=!folder.writable;
    el('files-previous').disabled=folder.offset===0;
    el('files-next').disabled=folder.next_offset===null;
    el('files-summary').textContent=`${folder.total} visible items${folder.total ? ` · ${folder.offset+1}–${Math.min(folder.offset+folder.limit,folder.total)}` : ''}${folder.truncated?' · first 10,000 entries only':''}${folder.skipped?` · ${folder.skipped} unreadable entries skipped`:''}`;
    el('files-upload-note').textContent=folder.writable?`Drop desktop files into this folder to upload automatically · ${bytes(folder.max_upload_bytes)} per file · existing files are never overwritten.`:'This folder is not writable by your account. You can browse it and download readable files.';
    renderRows();
  }
  async function load(path,offset=0) {
    const id=++requestNumber; busy=true; el('files-upload').disabled=true; el('files-new-folder').disabled=true;
    try {
      const data=await api(`/api/files?${new URLSearchParams({path,hidden:el('files-hidden').checked?'1':'0',offset:String(offset)})}`);
      if(id!==requestNumber)return;
      folder=data; busy=false; render(); notice(data.truncated?'This folder is large. The list is limited to the first 10,000 scanned entries.':'');
    } catch(error) {
      if(id===requestNumber) { notice(error.message,true); /* Keep the last valid folder visible; drops stay disabled until refresh. */ }
    } finally { if(id===requestNumber) { el('files-refresh').disabled=false; } }
  }
  function renderQueue() {
    el('files-queue-panel').hidden=queue.length===0;
    const list=el('files-queue'); list.replaceChildren();
    for(const item of queue) {
      const row=node('li','files-queue-item'); row.dataset.state=item.state;
      const title=node('div','files-queue-title'); title.append(node('strong','',item.file.name),node('span','',item.state==='uploading'?`${item.percent}%`:item.state==='done'?'Uploaded':item.state==='failed'?'Failed':'Queued'));
      const progress=node('progress'); progress.max=100; progress.value=item.percent;
      progress.setAttribute('aria-label',`Upload ${item.file.name}`);
      row.append(title,node('span','files-queue-target',item.destination.display),progress);
      if(item.error)row.append(node('span','error',item.error));
      list.append(row);
    }
  }
  function upload(item) {
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest(); xhr.open('POST','/api/files/upload');
      xhr.setRequestHeader('Content-Type','application/octet-stream');
      xhr.setRequestHeader('X-CSRF-Token',el('files-csrf').value);
      xhr.setRequestHeader('X-Folder-Path',encodeURIComponent(item.destination.path));
      xhr.setRequestHeader('X-Folder-Id',item.destination.id);
      xhr.setRequestHeader('X-File-Name',encodeURIComponent(item.file.name));
      xhr.upload.onprogress=event=>{ if(event.lengthComputable) { item.percent=Math.min(99,Math.round(event.loaded/event.total*100)); renderQueue(); } };
      xhr.onload=()=>{
        let data; try { data=JSON.parse(xhr.responseText); } catch { data={error:'Unexpected upload response. Refresh the folder before retrying.'}; }
        if(xhr.status===401){sessionEnded=true;location.assign('/login');}
        if(xhr.status>=200&&xhr.status<300)resolve(data); else reject(new Error(data.error||'Upload failed. Refresh to check the destination.'));
      };
      xhr.onerror=()=>reject(new Error('Connection lost. Check the destination before retrying; the upload will not be retried automatically.'));
      xhr.onabort=()=>reject(new Error('Upload interrupted. Refresh the destination folder to check its state.'));
      xhr.send(item.file);
    });
  }
  async function drain() {
    if(processing)return; processing=true;
    try {
      let item;
      while(!sessionEnded && (item=queue.find(entry=>entry.state==='queued'))) {
        item.state='uploading';renderQueue();
        try { await upload(item); item.state='done';item.percent=100; }
        catch(error) {item.state='failed';item.error=error.message;}
        renderQueue();
        if(!busy&&folder?.path===item.destination.path)await load(folder.path,folder.offset);
      }
    } finally {processing=false;}
  }
  function enqueue(files,destination) {
    if(!destination) {notice('Open a writable folder and wait for it to finish loading before uploading.',true);return;}
    const batch=Array.from(files);
    if(!batch.length)return;
    if(queue.filter(item=>['queued','uploading'].includes(item.state)).length+batch.length>100) {notice('Upload up to 100 files at a time.',true);return;}
    for(const file of batch) {
      const item={file,destination:{...destination},state:'queued',percent:0};
      if(file.size>destination.max) {item.state='failed';item.error=`File exceeds ${bytes(destination.max)} limit.`;}
      queue.push(item);
    }
    renderQueue();drain();
  }
  const zone=el('files-dropzone');
  const isFileDrag=event=>Array.from(event.dataTransfer?.types||[]).includes('Files');
  zone.addEventListener('dragenter',event=>{if(!isFileDrag(event))return;event.preventDefault();dragDepth++;zone.classList.add('drag-over');});
  zone.addEventListener('dragover',event=>{if(!isFileDrag(event))return;event.preventDefault();event.dataTransfer.dropEffect=target()?'copy':'none';});
  zone.addEventListener('dragleave',event=>{event.preventDefault();if(--dragDepth<=0){dragDepth=0;zone.classList.remove('drag-over');}});
  zone.addEventListener('drop',event=>{
    event.preventDefault();dragDepth=0;zone.classList.remove('drag-over');
    const destination=target(); const items=Array.from(event.dataTransfer.items||[]);
    if(items.some(item=>item.webkitGetAsEntry?.()?.isDirectory)) {notice('Folder drops are not supported yet. Drop individual files or select multiple files.',true);return;}
    enqueue(event.dataTransfer.files,destination);
  });
  // Prevent accidental browser navigation when a file is dropped outside the explorer.
  window.addEventListener('dragover',event=>{if(isFileDrag(event))event.preventDefault();});
  window.addEventListener('drop',event=>{if(isFileDrag(event))event.preventDefault();});
  el('files-upload').addEventListener('click',()=>{pickerTarget=target();el('files-picker').click();});
  el('files-picker').addEventListener('change',event=>{enqueue(event.target.files,pickerTarget);event.target.value='';});
  el('files-refresh').addEventListener('click',()=>load(folder?.path||document.querySelector('.files-page').dataset.initialPath,folder?.offset||0));
  el('files-home').addEventListener('click',()=>load(folder?.home||document.querySelector('.files-page').dataset.initialPath));
  el('files-up').addEventListener('click',()=>{if(folder?.parent)load(folder.parent);});
  el('files-path-form').addEventListener('submit',event=>{event.preventDefault();load(el('files-path').value);});
  el('files-hidden').addEventListener('change',()=>{if(folder)load(folder.path);});
  el('files-search').addEventListener('input',renderRows);
  el('files-previous').addEventListener('click',()=>load(folder.path,Math.max(0,folder.offset-folder.limit)));
  el('files-next').addEventListener('click',()=>{if(folder?.next_offset!==null)load(folder.path,folder.next_offset);});
  el('files-clear-queue').addEventListener('click',()=>{for(let i=queue.length-1;i>=0;i--)if(['done','failed'].includes(queue[i].state))queue.splice(i,1);renderQueue();});
  const dialog=el('files-folder-dialog');
  el('files-new-folder').addEventListener('click',()=>{mkdirTarget=target();if(!mkdirTarget)return;el('files-folder-name').value='';el('files-folder-error').hidden=true;dialog.showModal();});
  el('files-folder-cancel').addEventListener('click',()=>dialog.close());
  el('files-folder-form').addEventListener('submit',async event=>{
    event.preventDefault();el('files-folder-submit').disabled=true;
    try {
      const body=new URLSearchParams({csrf:el('files-csrf').value,path:mkdirTarget.path,name:el('files-folder-name').value,folder_id:mkdirTarget.id});
      await api('/api/files/folders',{method:'POST',body});dialog.close();if(folder?.path===mkdirTarget.path)await load(folder.path);
    }catch(error){el('files-folder-error').textContent=error.message;el('files-folder-error').hidden=false;}
    finally{el('files-folder-submit').disabled=false;}
  });
  load(document.querySelector('.files-page').dataset.initialPath);
})();
