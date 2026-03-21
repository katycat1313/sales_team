const { app, BrowserWindow, Tray, Menu, nativeImage, shell, Notification } = require('electron');
const path = require('path');
const http = require('http');

const G14_IP = process.env.G14_IP || '100.x.x.x'; // Set to G14 Tailscale IP
const ORCH_URL = `http://${G14_IP}:8000`;
let win, tray;
let pendingApprovals = 0;

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#060608',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    icon: path.join(__dirname, 'icon.png'),
    title: 'Katy — Agent Command',
  });

  // Load the dashboard, pointing at the G14
  const dashPath = path.join(__dirname, '..', 'dashboard', 'index.html');

  // Inject the G14 IP into the dashboard before loading
  win.loadFile(dashPath);

  // Inject correct API URL after load
  win.webContents.on('did-finish-load', () => {
    win.webContents.executeJavaScript(`
      window.API_OVERRIDE = '${ORCH_URL}';
      console.log('Mac app connected to G14 at ${ORCH_URL}');
    `);
  });

  win.on('closed', () => { win = null; });
}

function createTray() {
  // Simple tray icon — dot
  const img = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAbwAAAG8B8aLcQwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAABYSURBVDiNY/z//z8DJYCJgUIwasCoAaMGjBgDGBkZGRkYGBhIMoSRkZERMJiRkZEBMJiRkYEBMJiRkYEBMJiRkYEBMJiRkYEBMJiRkYEBMBgVDQAA//8='
  );
  tray = new Tray(img);

  const updateMenu = () => {
    const menu = Menu.buildFromTemplate([
      { label: 'Katy — Agent Command', enabled: false },
      { type: 'separator' },
      { label: pendingApprovals > 0 ? `⚡ ${pendingApprovals} pending approvals` : '✓ No pending approvals', enabled: false },
      { type: 'separator' },
      { label: 'Open Dashboard', click: () => { if(!win) createWindow(); else win.focus(); } },
      { label: 'Open G14 directly', click: () => shell.openExternal(ORCH_URL) },
      { type: 'separator' },
      { label: 'Quit', click: () => app.quit() },
    ]);
    tray.setContextMenu(menu);
  };

  tray.setToolTip('Agent Team');
  updateMenu();

  tray.on('click', () => {
    if (!win) createWindow();
    else win.isVisible() ? win.hide() : win.show();
  });

  // Poll for approvals and update tray
  setInterval(async () => {
    try {
      const data = await fetchJSON(`${ORCH_URL}/approvals`);
      const count = data.length;
      if (count !== pendingApprovals) {
        pendingApprovals = count;
        updateMenu();
        if (count > 0) {
          new Notification({
            title: 'Agent Team',
            body: `${count} item${count > 1 ? 's' : ''} need${count === 1 ? 's' : ''} your approval`,
          }).show();
        }
      }
    } catch(e) {}
  }, 15000);
}

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch(e) { reject(e); } });
    }).on('error', reject);
  });
}

app.whenReady().then(() => {
  createWindow();
  createTray();
  app.on('activate', () => { if (!win) createWindow(); });
});

app.on('window-all-closed', () => {
  // Keep running in tray on Mac
  if (process.platform !== 'darwin') app.quit();
});
