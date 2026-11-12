// Tira uma foto da interface (para conferir a tela sem abrir a janela): electron foto.js URL SAIDA.png [largura altura]
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const [url, saida, w = '1560', h = '980'] = process.argv.slice(2);
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: +w, height: +h, show: false, webPreferences: { offscreen: true } });
  await win.loadURL(url);
  await new Promise((r) => setTimeout(r, 1800));
  fs.writeFileSync(saida, (await win.webContents.capturePage()).toPNG());
  app.quit();
});
