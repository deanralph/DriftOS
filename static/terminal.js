(() => {
  const el = id => document.getElementById(id);
  const connect = el('terminal-connect');
  const disconnect = el('terminal-disconnect');
  const reconnect = el('terminal-reconnect');
  const screen = el('terminal-screen');
  const overlay = el('terminal-start');
  let socket = null;
  let terminal = null;
  let fit = null;
  let ready = false;
  let finalMessage = '';
  let closingByUser = false;
  let inputQueue = '';
  const encoder = new TextEncoder();
  const send = message => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
  };
  const status = (state, message) => {
    el('terminal-status').textContent = `${state === 'CONNECTED' ? '●' : '○'} ${state}`;
    el('terminal-status').dataset.state = state.toLowerCase();
    el('terminal-message').textContent = message;
  };
  function fitTerminal() {
    if (!terminal || screen.hidden) return;
    fit.fit();
    if (terminal.cols > 500 || terminal.rows > 200) terminal.resize(Math.min(terminal.cols, 500), Math.min(terminal.rows, 200));
    el('terminal-size').textContent = `${terminal.cols} × ${terminal.rows}`;
  }
  // Keep large pastes inside protocol limits and pace them to the PTY.
  function drainInput() {
    if (!ready || !inputQueue) return;
    if (socket.bufferedAmount > 32768) return;
    let chunk = '', count = 0;
    for (const character of inputQueue) {
      const size = encoder.encode(character).length;
      if (count + size > 2048) break;
      chunk += character; count += size;
    }
    inputQueue = inputQueue.slice(chunk.length);
    send({type: 'input', data: chunk});
  }
  setInterval(drainInput, 40);
  function setupTerminal() {
    terminal?.dispose();
    terminal = new Terminal({
      cursorBlink: true, fontFamily: "'DejaVu Sans Mono', ui-monospace, monospace",
      fontSize: 13, lineHeight: 1.35, scrollback: 2000, screenReaderMode: true,
      theme: {background: '#030906', foreground: '#e0ecdb', cursor: '#9ccc77', selectionBackground: '#385b45',
        black: '#08120f', red: '#f0a49a', green: '#9ccc77', yellow: '#e8c47e', blue: '#94bccc', magenta: '#baa4ca', cyan: '#92c7b4', white: '#e0ecdb',
        brightBlack: '#668552', brightRed: '#ffc0b5', brightGreen: '#c8e7aa', brightYellow: '#f6dba5', brightBlue: '#b0d8e8', brightMagenta: '#dac4ea', brightCyan: '#b0e4d1', brightWhite: '#f4fff0'}
    });
    fit = new FitAddon.FitAddon(); terminal.loadAddon(fit); terminal.open(screen);
    terminal.onData(data => {
      if (!ready) return;
      if (inputQueue.length + data.length > 65536) {
        el('terminal-message').textContent = 'Paste is too large. Paste smaller sections.';
        return;
      }
      inputQueue += data;
    });
    terminal.onResize(({cols, rows}) => { if (ready) send({type: 'resize', cols, rows}); });
    fitTerminal();
  }
  function connectShell() {
    if (socket) return;
    ready = false; finalMessage = ''; inputQueue = ''; closingByUser = false;
    connect.disabled = true; reconnect.hidden = true; disconnect.disabled = false;
    overlay.hidden = true; screen.hidden = false;
    setupTerminal(); status('CONNECTING', 'Opening your account’s shell…');
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const connection = new WebSocket(`${protocol}//${location.host}/ws/terminal`);
    socket = connection;
    connection.addEventListener('open', () => {
      send({type: 'open', csrf: el('terminal-csrf').value,
        cols: Math.min(500, Math.max(2, terminal.cols)), rows: Math.min(200, Math.max(2, terminal.rows))});
    });
    connection.addEventListener('message', event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === 'ready') { ready = true; status('CONNECTED', 'Connected. Commands run as your Linux account.'); terminal.focus(); }
      else if (message.type === 'output') terminal.write(message.data);
      else if (message.type === 'error' || message.type === 'exit') { finalMessage = message.message; status('DISCONNECTED', finalMessage); }
    });
    connection.addEventListener('close', () => {
      ready = false; socket = null; inputQueue = '';
      connect.disabled = false; disconnect.disabled = true;
      overlay.hidden = true; reconnect.hidden = false;
      terminal.writeln('\r\n[Session ended]');
      terminal.options.disableStdin = true; terminal.options.cursorBlink = false;
      status('DISCONNECTED', finalMessage || 'Connection closed. Start a new terminal to reconnect.');
    });
    connection.addEventListener('error', () => {
      if (closingByUser) return;
      finalMessage = 'Could not connect. Check your connection and sign in again if your session expired.';
      status('DISCONNECTED', finalMessage);
    });
  }
  connect.addEventListener('click', connectShell);
  reconnect.addEventListener('click', connectShell);
  disconnect.addEventListener('click', () => {
    closingByUser = true; finalMessage = 'Disconnected. The shell has ended.'; ready = false;
    send({type: 'close'}); socket?.close();
  });
  el('terminal-clear').addEventListener('click', () => { terminal?.clear(); if (ready) terminal.focus(); });
  new ResizeObserver(fitTerminal).observe(screen);
  window.addEventListener('pagehide', () => { send({type: 'close'}); socket?.close(); });
  screen.hidden = true;
})();
