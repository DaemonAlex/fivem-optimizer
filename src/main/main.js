const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, execFileSync } = require('child_process');
const Store = require('electron-store');
const { autoUpdater } = require('electron-updater');

const store = new Store({
  defaults: {
    lastFolder: null,
    scanHistory: [],
    settings: {
      // Texture limits (community-validated)
      maxTextureResolution: 4096,
      recommendedMaxResolution: 2048,
      maxYtdSizeMB: 14,
      // Vehicle/fragment limits
      maxVehiclePolys: 150000,
      recommendedMaxVehiclePolys: 70000,
      maxBones: 200,
      maxYftSizeMB: 14,
      // Prop/drawable limits
      maxPropPolys: 50000,
      recommendedMaxPropPolys: 15000,
      maxYdrSizeMB: 8,
      // Collision limits
      maxCollisionPolys: 10000,
      maxYbnSizeMB: 4,
      maxBoundsDimension: 500,
      // General
      maxSingleFileMB: 16,
      largeFileWarningMB: 10,
      // LOD validation
      minLodLevels: 2,
      recommendedLodLevels: 4,
      // Optimizer settings
      optimizerTargetResolution: 1024,
      optimizerSkipScriptRt: true,
      optimizerSkipEmissive: true,
      optimizerMinResizeSize: 1048576,
    },
  },
});

let mainWindow;
let pythonProcess = null;
let pythonCancelled = false;
let pythonExe = null;

const isDev = !app.isPackaged;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    backgroundColor: '#0a0a0f',
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      devTools: isDev,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', '..', 'build', 'index.html'));
  }

  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window:maximized', true);
  });
  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window:maximized', false);
  });
}

function getPythonScriptsPath() {
  if (isDev) {
    return path.join(__dirname, '..', '..', 'python');
  }
  return path.join(process.resourcesPath, 'python');
}

function findPython() {
  // Check bundled Python embeddable first (shipped with installer)
  const bundledPython = path.join(
    app.isPackaged ? process.resourcesPath : path.join(__dirname, '..', '..'),
    'python-embed',
    'python.exe'
  );

  const candidates = [
    bundledPython,
    'python',
    'python3',
    'C:\\Python313\\python.exe',
    'C:\\Python312\\python.exe',
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
  ];

  for (const cmd of candidates) {
    try {
      const out = execFileSync(cmd, ['--version'], { stdio: 'pipe', timeout: 5000 });
      const version = out.toString().trim();
      // Ensure Python 3.10+
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match && (parseInt(match[1]) > 3 || (parseInt(match[1]) === 3 && parseInt(match[2]) >= 10))) {
        return cmd;
      }
    } catch {
      // try next
    }
  }
  return null;
}

function checkPythonDeps(exe) {
  try {
    execFileSync(exe, ['-c', 'import struct, hashlib, json, os, sys'], {
      stdio: 'pipe',
      timeout: 10000,
    });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

// Auto-update configuration
autoUpdater.autoDownload = true;
autoUpdater.autoInstallOnAppQuit = true;

function setupAutoUpdater() {
  if (isDev) return; // Skip updates in development

  autoUpdater.on('update-available', (info) => {
    mainWindow?.webContents.send('update:available', info.version);
  });

  autoUpdater.on('update-downloaded', (info) => {
    mainWindow?.webContents.send('update:downloaded', info.version);
  });

  autoUpdater.on('error', (err) => {
    // Silently ignore update errors — don't block the user
    console.error('Auto-update error:', err.message);
  });

  // Check for updates after a short delay (don't slow down startup)
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch(() => {});
  }, 5000);
}

app.whenReady().then(() => {
  pythonExe = findPython();
  createWindow();
  setupAutoUpdater();
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  app.quit();
});

// Window controls
ipcMain.on('window:minimize', () => mainWindow?.minimize());
ipcMain.on('window:maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
ipcMain.on('window:close', () => mainWindow?.close());
ipcMain.handle('window:isMaximized', () => mainWindow?.isMaximized());

// App version & updates
ipcMain.handle('app:getVersion', () => app.getVersion());
ipcMain.on('update:install', () => {
  autoUpdater.quitAndInstall(false, true);
});

// Python status
ipcMain.handle('python:status', () => {
  if (!pythonExe) {
    return { found: false, error: 'Python 3.10+ not found. Install Python and add it to your PATH.' };
  }
  const deps = checkPythonDeps(pythonExe);
  return { found: true, exe: pythonExe, depsOk: deps.ok, depsError: deps.error };
});

// Settings
ipcMain.handle('settings:get', () => store.get('settings'));
ipcMain.handle('settings:set', (_e, settings) => {
  store.set('settings', settings);
  return true;
});

// Scan history
ipcMain.handle('history:get', () => store.get('scanHistory'));
ipcMain.handle('history:clear', () => {
  store.set('scanHistory', []);
  return true;
});

// Last folder
ipcMain.handle('store:getLastFolder', () => store.get('lastFolder'));

// Folder picker
ipcMain.handle('dialog:selectFolder', async () => {
  const lastFolder = store.get('lastFolder');
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select FiveM Streaming Folder',
    defaultPath: lastFolder || undefined,
  });
  if (result.canceled) return null;
  const selected = result.filePaths[0];
  store.set('lastFolder', selected);
  return selected;
});

// Validate folder
ipcMain.handle('folder:validate', async (_e, folderPath) => {
  if (!folderPath) return { valid: false, error: 'No folder selected.' };
  try {
    const stat = fs.statSync(folderPath);
    if (!stat.isDirectory()) return { valid: false, error: 'Selected path is not a directory.' };
    fs.accessSync(folderPath, fs.constants.R_OK);
    return { valid: true };
  } catch (e) {
    return { valid: false, error: `Cannot access folder: ${e.message}` };
  }
});

// Export results
ipcMain.handle('export:save', async (_e, { data, format }) => {
  const filters = format === 'csv'
    ? [{ name: 'CSV Files', extensions: ['csv'] }]
    : [{ name: 'JSON Files', extensions: ['json'] }];

  const result = await dialog.showSaveDialog(mainWindow, {
    title: 'Export Analysis Results',
    defaultPath: `fivem-analysis-${Date.now()}`,
    filters,
  });

  if (result.canceled) return false;

  try {
    fs.writeFileSync(result.filePath, data, 'utf-8');
    return true;
  } catch (e) {
    throw new Error(`Failed to save: ${e.message}`);
  }
});

// Drop folder validation
ipcMain.handle('drop:validatePath', async (_e, filePath) => {
  try {
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      store.set('lastFolder', filePath);
      return { valid: true, path: filePath };
    }
    return { valid: false, error: 'Dropped item is not a folder.' };
  } catch {
    return { valid: false, error: 'Cannot access dropped path.' };
  }
});

// Run analysis
ipcMain.handle('analysis:start', async (_event, folderPath) => {
  // Re-check Python at analysis time
  if (!pythonExe) {
    pythonExe = findPython();
  }
  if (!pythonExe) {
    throw new Error('Python 3.10+ not found. Please install Python and ensure it is in your PATH.');
  }

  // Validate folder
  try {
    const stat = fs.statSync(folderPath);
    if (!stat.isDirectory()) throw new Error('Not a directory');
    fs.accessSync(folderPath, fs.constants.R_OK);
  } catch (e) {
    throw new Error(`Cannot access folder: ${e.message}`);
  }

  // Validate script exists
  const scriptPath = path.join(getPythonScriptsPath(), 'analyze.py');
  if (!fs.existsSync(scriptPath)) {
    throw new Error(`Analysis script not found at ${scriptPath}`);
  }

  if (pythonProcess) {
    pythonCancelled = true;
    pythonProcess.kill();
    pythonProcess = null;
  }
  pythonCancelled = false;

  // Pass settings as JSON via env
  const settings = store.get('settings');

  return new Promise((resolve, reject) => {
    let settled = false;

    pythonProcess = spawn(pythonExe, [scriptPath, folderPath, JSON.stringify(settings)], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout.on('data', (data) => {
      const text = data.toString();
      output += text;

      const lines = text.split('\n');
      for (const line of lines) {
        if (line.startsWith('PROGRESS:')) {
          mainWindow?.webContents.send('analysis:progress', line.substring(9));
        }
      }
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code, signal) => {
      pythonProcess = null;
      if (settled) return;
      settled = true;

      // If cancelled by user or replaced by new analysis, silently reject
      if (pythonCancelled || code === null) {
        reject(new Error('Analysis was cancelled.'));
        return;
      }

      if (code === 0) {
        try {
          // Find the JSON object in output: look for first { and last }
          const firstBrace = output.indexOf('{');
          const lastBrace = output.lastIndexOf('}');
          if (firstBrace === -1 || lastBrace === -1) {
            reject(new Error('Analysis produced no results. The folder may not contain streaming assets.'));
            return;
          }
          const jsonStr = output.substring(firstBrace, lastBrace + 1);
          const results = JSON.parse(jsonStr);

          // Save to scan history
          const history = store.get('scanHistory') || [];
          history.unshift({
            folder: folderPath,
            timestamp: Date.now(),
            summary: results.summary,
          });
          store.set('scanHistory', history.slice(0, 20)); // Keep last 20

          resolve(results);
        } catch (e) {
          reject(new Error(`Failed to parse results: ${e.message}\nRaw output (last 500 chars): ${output.slice(-500)}`));
        }
      } else {
        const detail = errorOutput || output.slice(-1000) || '(no output captured)';
        reject(new Error(`Analysis failed (exit code ${code}):\n${detail}`));
      }
    });

    pythonProcess.on('error', (err) => {
      pythonProcess = null;
      if (settled) return;
      settled = true;
      reject(new Error(`Failed to start Python: ${err.message}`));
    });
  });
});

// Cancel analysis
ipcMain.on('analysis:cancel', () => {
  if (pythonProcess) {
    pythonCancelled = true;
    pythonProcess.kill();
    pythonProcess = null;
  }
});

// === Optimizer file operations ===

// Open file in system explorer
ipcMain.handle('optimizer:showInExplorer', async (_e, filePath) => {
  try {
    shell.showItemInFolder(filePath);
    return true;
  } catch {
    return false;
  }
});

// Select backup folder
ipcMain.handle('optimizer:selectBackupFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: 'Select Backup Folder',
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});

// Delete files with backup
ipcMain.handle('optimizer:deleteFiles', async (_e, { files, backupFolder, scanFolder }) => {
  const results = { deleted: 0, backed: 0, errors: [] };

  for (const relPath of files) {
    const absPath = path.resolve(scanFolder, relPath);
    // Path traversal protection: ensure resolved path is within scanFolder
    if (!absPath.startsWith(path.resolve(scanFolder))) {
      results.errors.push({ file: relPath, error: 'Invalid path: outside scan folder' });
      continue;
    }
    try {
      // Verify file exists
      if (!fs.existsSync(absPath)) {
        results.errors.push({ file: relPath, error: 'File not found' });
        continue;
      }

      // Create backup if backup folder specified
      if (backupFolder) {
        const backupPath = path.join(backupFolder, relPath);
        const backupDir = path.dirname(backupPath);
        fs.mkdirSync(backupDir, { recursive: true });
        fs.copyFileSync(absPath, backupPath);
        results.backed++;
      }

      // Delete the file
      fs.unlinkSync(absPath);
      results.deleted++;
    } catch (e) {
      results.errors.push({ file: relPath, error: e.message });
    }
  }

  return results;
});

// Run texture optimization analysis (dry-run/plan)
let optimizerProcess = null;

ipcMain.handle('optimizer:analyzePlan', async (_event, folderPath) => {
  if (!pythonExe) {
    pythonExe = findPython();
  }
  if (!pythonExe) {
    throw new Error('Python 3.10+ not found.');
  }

  const scriptPath = path.join(getPythonScriptsPath(), 'optimize_textures.py');
  if (!fs.existsSync(scriptPath)) {
    throw new Error(`Optimizer script not found at ${scriptPath}`);
  }

  const settings = store.get('settings');

  if (optimizerProcess) {
    optimizerProcess.kill();
    optimizerProcess = null;
  }

  return new Promise((resolve, reject) => {
    optimizerProcess = spawn(pythonExe, [scriptPath, folderPath, JSON.stringify(settings)], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });

    let output = '';
    let errorOutput = '';

    optimizerProcess.stdout.on('data', (data) => {
      const text = data.toString();
      output += text;
      const lines = text.split('\n');
      for (const line of lines) {
        if (line.startsWith('PROGRESS:')) {
          mainWindow?.webContents.send('optimizer:progress', line.substring(9));
        }
      }
    });

    optimizerProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    optimizerProcess.on('close', (code, signal) => {
      optimizerProcess = null;
      if (code === 0) {
        try {
          const firstBrace = output.indexOf('{');
          const lastBrace = output.lastIndexOf('}');
          if (firstBrace === -1 || lastBrace === -1) {
            reject(new Error('Optimizer produced no results.'));
            return;
          }
          resolve(JSON.parse(output.substring(firstBrace, lastBrace + 1)));
        } catch (e) {
          reject(new Error(`Failed to parse optimizer results: ${e.message}`));
        }
      } else {
        const detail = errorOutput || output.slice(-1000) || '(no output captured)';
        const sigInfo = signal ? ` signal=${signal}` : '';
        reject(new Error(`Optimizer failed (code ${code}${sigInfo}):\n${detail}`));
      }
    });

    optimizerProcess.on('error', (err) => {
      optimizerProcess = null;
      reject(new Error(`Failed to start optimizer: ${err.message}`));
    });
  });
});

ipcMain.on('optimizer:cancel', () => {
  if (optimizerProcess) {
    optimizerProcess.kill();
    optimizerProcess = null;
  }
});

// Execute texture optimization (in-place mipmap replacement)
ipcMain.handle('optimizer:execute', async (_event, payload) => {
  if (!pythonExe) {
    pythonExe = findPython();
  }
  if (!pythonExe) {
    throw new Error('Python 3.10+ not found.');
  }

  const scriptPath = path.join(getPythonScriptsPath(), 'optimize_textures.py');
  if (!fs.existsSync(scriptPath)) {
    throw new Error(`Optimizer script not found at ${scriptPath}`);
  }

  if (optimizerProcess) {
    optimizerProcess.kill();
    optimizerProcess = null;
  }

  return new Promise((resolve, reject) => {
    optimizerProcess = spawn(pythonExe, [scriptPath, '--execute', JSON.stringify(payload)], {
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });

    let output = '';
    let errorOutput = '';

    optimizerProcess.stdout.on('data', (data) => {
      const text = data.toString();
      output += text;
      const lines = text.split('\n');
      for (const line of lines) {
        if (line.startsWith('PROGRESS:')) {
          mainWindow?.webContents.send('optimizer:progress', line.substring(9));
        }
      }
    });

    optimizerProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    optimizerProcess.on('close', (code, signal) => {
      optimizerProcess = null;
      if (code === 0) {
        try {
          const firstBrace = output.indexOf('{');
          const lastBrace = output.lastIndexOf('}');
          if (firstBrace === -1 || lastBrace === -1) {
            reject(new Error('Optimizer produced no results.'));
            return;
          }
          resolve(JSON.parse(output.substring(firstBrace, lastBrace + 1)));
        } catch (e) {
          reject(new Error(`Failed to parse optimizer results: ${e.message}`));
        }
      } else {
        const detail = errorOutput || output.slice(-1000) || '(no output captured)';
        const sigInfo = signal ? ` signal=${signal}` : '';
        reject(new Error(`Optimizer failed (code ${code}${sigInfo}):\n${detail}`));
      }
    });

    optimizerProcess.on('error', (err) => {
      optimizerProcess = null;
      reject(new Error(`Failed to start optimizer: ${err.message}`));
    });
  });
});
