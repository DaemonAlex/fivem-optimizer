const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Window controls
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  onMaximized: (callback) => {
    const handler = (_e, val) => callback(val);
    ipcRenderer.on('window:maximized', handler);
    return () => ipcRenderer.removeListener('window:maximized', handler);
  },

  // App info & updates
  getAppVersion: () => ipcRenderer.invoke('app:getVersion'),
  installUpdate: () => ipcRenderer.send('update:install'),
  onUpdateAvailable: (callback) => {
    const handler = (_e, version) => callback(version);
    ipcRenderer.on('update:available', handler);
    return () => ipcRenderer.removeListener('update:available', handler);
  },
  onUpdateDownloaded: (callback) => {
    const handler = (_e, version) => callback(version);
    ipcRenderer.on('update:downloaded', handler);
    return () => ipcRenderer.removeListener('update:downloaded', handler);
  },

  // Python status
  getPythonStatus: () => ipcRenderer.invoke('python:status'),

  // Settings
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (settings) => ipcRenderer.invoke('settings:set', settings),

  // Scan history
  getHistory: () => ipcRenderer.invoke('history:get'),
  clearHistory: () => ipcRenderer.invoke('history:clear'),

  // Last folder
  getLastFolder: () => ipcRenderer.invoke('store:getLastFolder'),

  // Folder selection
  selectFolder: () => ipcRenderer.invoke('dialog:selectFolder'),
  validateFolder: (path) => ipcRenderer.invoke('folder:validate', path),
  validateDrop: (path) => ipcRenderer.invoke('drop:validatePath', path),

  // Export
  exportResults: (data, format) => ipcRenderer.invoke('export:save', { data, format }),

  // Analysis
  startAnalysis: (folderPath) => ipcRenderer.invoke('analysis:start', folderPath),
  cancelAnalysis: () => ipcRenderer.send('analysis:cancel'),
  onProgress: (callback) => {
    const handler = (_e, data) => callback(data);
    ipcRenderer.on('analysis:progress', handler);
    return () => ipcRenderer.removeListener('analysis:progress', handler);
  },

  // Optimizer
  showInExplorer: (filePath) => ipcRenderer.invoke('optimizer:showInExplorer', filePath),
  selectBackupFolder: () => ipcRenderer.invoke('optimizer:selectBackupFolder'),
  deleteFiles: (files, backupFolder, scanFolder) =>
    ipcRenderer.invoke('optimizer:deleteFiles', { files, backupFolder, scanFolder }),

  // Texture optimizer
  analyzePlan: (folderPath) => ipcRenderer.invoke('optimizer:analyzePlan', folderPath),
  optimizeTextures: (payload) => ipcRenderer.invoke('optimizer:execute', payload),
  onOptimizerProgress: (callback) => {
    const handler = (_e, data) => callback(data);
    ipcRenderer.on('optimizer:progress', handler);
    return () => ipcRenderer.removeListener('optimizer:progress', handler);
  },
  cancelOptimizer: () => ipcRenderer.send('optimizer:cancel'),
});
