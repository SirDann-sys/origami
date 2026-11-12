// Origami · janela do app. O motor Python é o servidor (API + interface em 127.0.0.1:3950) e o único dono da GPU.
// Se o motor já estiver no ar (ex.: aberto pelo terminal), a janela só se conecta; senão, o app o sobe e o fecha ao sair.
// Tudo relativo à pasta do app: app\ fica ao lado de motor\, ambientes\, dados\…
// Cada passo vai para dados\logs\app.log, e a saída do motor para dados\logs\motor.log.
'use strict';
const { app, BrowserWindow, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');

const RAIZ = path.resolve(__dirname, '..');
const LER = (f, padrao) => { try { return JSON.parse(fs.readFileSync(f, 'utf-8')); } catch { return padrao; } };
const CFG = LER(path.join(RAIZ, 'config.json'), {});
const PORTA = CFG.porta || 3950;
const PY = path.join(RAIZ, 'ambientes', 'qwen', 'Scripts', 'python.exe');
const LOGS = path.join(RAIZ, 'dados', 'logs');
const LOG = path.join(LOGS, 'app.log');
const ICONE = path.join(__dirname, 'icone.png');
let motor = null, janela = null, abertura = null, fechando = false, religando = false, quedas = [];

function log(...x) {
  try { fs.mkdirSync(LOGS, { recursive: true }); fs.appendFileSync(LOG, `${new Date().toISOString()} ${x.join(' ')}\n`); } catch {}
}
process.on('uncaughtException', (e) => { log('ERRO', e.stack || e); try { dialog.showErrorBox('Origami', String(e.stack || e)); } catch {} });
log('--- abrindo', process.versions.electron, RAIZ);

app.setAppUserModelId('Origami.App');      // ícone e agrupamento próprios na barra de tarefas
if (!app.requestSingleInstanceLock()) { log('outra janela do Origami já está aberta: saindo'); app.quit(); }

function noAr() {
  return new Promise((ok) => {
    const r = http.get({ host: '127.0.0.1', port: PORTA, path: '/estado', timeout: 1500 }, (res) => { res.resume(); ok(res.statusCode === 200); });
    r.on('error', () => ok(false)); r.on('timeout', () => { r.destroy(); ok(false); });
  });
}

function mostrarAbertura() {
  abertura = new BrowserWindow({ width: 420, height: 300, frame: false, resizable: false, center: true,
    backgroundColor: '#0e1626', icon: ICONE, show: false, webPreferences: { contextIsolation: true, sandbox: true } });
  abertura.loadFile(path.join(__dirname, 'abertura.html'));
  abertura.once('ready-to-show', () => abertura && abertura.show());
}

async function subirMotor() {
  if (await noAr()) { log('motor já estava no ar'); return; }
  fs.mkdirSync(LOGS, { recursive: true });
  const saida = fs.openSync(path.join(LOGS, 'motor.log'), 'a');
  log('subindo o motor:', PY, 'em', RAIZ);
  motor = spawn(PY, ['-m', 'motor.cli', 'servidor'], { cwd: RAIZ, env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    windowsHide: true, stdio: ['ignore', saida, saida] });
  motor.on('error', (e) => log('ERRO ao subir o motor:', e.message));
  const este = motor;
  motor.on('exit', (cod) => {
    log('o motor saiu com código', cod);
    if (este === motor) motor = null;
    if (!fechando) religar(`o motor parou (código ${cod})`);   // a janela religa o motor sozinha
  });
  for (let i = 0; i < 120; i++) { if (await noAr()) { log('motor no ar'); return; } await new Promise((r) => setTimeout(r, 250)); }
  throw new Error('O motor do Origami não respondeu em 30 segundos.');
}

// O motor caiu ou travou: liga de novo e avisa. Mais de 3 quedas em 10 min → para e mostra o registro (algo está errado).
async function religar(motivo) {
  if (religando || fechando) return;
  religando = true;
  const agora = Date.now();
  quedas = quedas.filter((t) => agora - t < 10 * 60 * 1000).concat(agora);
  log('religando o motor:', motivo, `(${quedas.length} queda(s) em 10 min)`);
  if (quedas.length > 3) {
    religando = false;
    const r = await dialog.showMessageBox({ type: 'error', title: 'Origami', message: 'O motor do Origami parou várias vezes seguidas.',
      detail: `${motivo}\nO registro mostra o motivo (dados\\logs\\motor.log). Os trabalhos que estavam na fila continuam salvos.`,
      buttons: ['Abrir o registro', 'Tentar de novo', 'Fechar'], defaultId: 0 });
    if (r.response === 0) await shell.openPath(path.join(LOGS, 'motor.log'));
    if (r.response === 1) { quedas = []; return religar('pedido do usuário'); }
    return;
  }
  try {
    if (motor) { try { require('child_process').spawnSync('taskkill', ['/F', '/T', '/PID', String(motor.pid)], { windowsHide: true }); } catch {} motor = null; }
    await subirMotor();
    if (janela) janela.webContents.executeJavaScript(`window.avisoMotor && window.avisoMotor(${JSON.stringify('O motor reiniciou sozinho: ' + motivo)})`).catch(() => {});
  } catch (e) { log('ERRO ao religar:', e.message); }
  religando = false;
}

// vigia: 3 perguntas sem resposta seguidas (30 s) com o motor nosso vivo = travado
let semResposta = 0;
setInterval(async () => {
  if (fechando || religando || !janela) return;
  if (await noAr()) { semResposta = 0; return; }
  if (++semResposta >= 3) { semResposta = 0; religar('não respondia havia 30 s'); }
}, 10000);

function abrirJanela() {
  janela = new BrowserWindow({ width: 1560, height: 980, minWidth: 1100, minHeight: 680, title: 'Origami', backgroundColor: '#0e1626',
    icon: ICONE, show: false, autoHideMenuBar: true, webPreferences: { contextIsolation: true, sandbox: true } });
  janela.loadURL(`http://127.0.0.1:${PORTA}/`);
  janela.webContents.setWindowOpenHandler(({ url }) => { shell.openExternal(url); return { action: 'deny' }; });
  janela.once('ready-to-show', () => { janela.show(); if (abertura) { abertura.destroy(); abertura = null; } });
  janela.on('closed', () => { janela = null; });
  log('janela aberta');
}

app.on('second-instance', () => { if (janela) { if (janela.isMinimized()) janela.restore(); janela.focus(); } });
app.whenReady().then(async () => {
  mostrarAbertura();
  try { await subirMotor(); }
  catch (e) {
    log('ERRO', e.message);
    if (abertura) { abertura.destroy(); abertura = null; }
    const r = await dialog.showMessageBox({ type: 'error', title: 'Origami', message: e.message,
      detail: 'O registro do motor mostra o motivo (dados\\logs\\motor.log).', buttons: ['Abrir o registro', 'Fechar'], defaultId: 0 });
    if (r.response === 0) await shell.openPath(path.join(LOGS, 'motor.log'));
    return app.quit();
  }
  abrirJanela();
});
// enquanto só a tela de abertura existe, fechá-la não encerra o app
// ao fechar, derruba o motor E o que ele ligou (servidor de voz, ComfyUI): senão a placa de vídeo continua ocupada
app.on('window-all-closed', () => {
  if (!janela && abertura) return;
  log('fechando'); fechando = true;
  if (motor) { try { require('child_process').spawnSync('taskkill', ['/F', '/T', '/PID', String(motor.pid)], { windowsHide: true }); } catch { motor.kill(); } }
  app.quit();
});
