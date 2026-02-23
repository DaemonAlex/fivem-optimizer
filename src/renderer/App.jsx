import React, { useState, useEffect, useCallback } from 'react';
import ErrorBoundary from './components/ErrorBoundary';
import TitleBar from './components/TitleBar';
import FolderPicker from './components/FolderPicker';
import ScanProgress from './components/ScanProgress';
import ResultsDashboard from './components/ResultsDashboard';
import OptimizerView from './components/OptimizerView';
import SettingsPage from './components/SettingsPage';

export default function App() {
  const [view, setView] = useState('picker'); // picker | scanning | results | optimizer | settings
  const [folderPath, setFolderPath] = useState(null);
  const [progress, setProgress] = useState('');
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [pythonStatus, setPythonStatus] = useState(null);

  // Load last folder and check Python on mount
  useEffect(() => {
    window.electronAPI.getLastFolder().then((f) => {
      if (f) setFolderPath(f);
    });
    window.electronAPI.getPythonStatus().then(setPythonStatus);
  }, []);

  // Progress listener with proper cleanup
  useEffect(() => {
    const removeListener = window.electronAPI.onProgress((msg) => {
      setProgress(msg);
    });
    return removeListener;
  }, []);

  const handleSelectFolder = useCallback(async () => {
    const path = await window.electronAPI.selectFolder();
    if (path) {
      setFolderPath(path);
      setError(null);
    }
  }, []);

  const handleDropFolder = useCallback(async (path) => {
    const result = await window.electronAPI.validateDrop(path);
    if (result.valid) {
      setFolderPath(result.path);
      setError(null);
    } else {
      setError(result.error);
    }
  }, []);

  const handleScan = useCallback(async () => {
    if (!folderPath) return;

    // Validate folder still exists
    const validation = await window.electronAPI.validateFolder(folderPath);
    if (!validation.valid) {
      setError(validation.error);
      return;
    }

    setView('scanning');
    setError(null);
    setProgress('0%|0/0|Starting analysis...');

    try {
      const data = await window.electronAPI.startAnalysis(folderPath);

      // Handle empty folder
      if (data.summary?.no_assets_found) {
        setError('No streaming assets found in this folder. Select a folder containing .ytd, .yft, .ydr, .ybn, .ymap, or .ytyp files.');
        setView('picker');
        return;
      }

      setResults(data);
      setView('results');
    } catch (err) {
      setError(err.message);
      setView('picker');
    }
  }, [folderPath]);

  const handleCancel = useCallback(() => {
    window.electronAPI.cancelAnalysis();
    setView('picker');
    setProgress('');
  }, []);

  const handleReset = useCallback(() => {
    setView('picker');
    setResults(null);
    setError(null);
    setProgress('');
  }, []);

  return (
    <div className="app">
      <TitleBar
        onSettingsClick={() => setView(view === 'settings' ? 'picker' : 'settings')}
        showBack={view === 'settings'}
      />
      <main className="app-content" role="main">
        <ErrorBoundary>
          {view === 'picker' && (
            <FolderPicker
              folderPath={folderPath}
              onSelectFolder={handleSelectFolder}
              onDropFolder={handleDropFolder}
              onScan={handleScan}
              error={error}
              pythonStatus={pythonStatus}
            />
          )}
          {view === 'scanning' && (
            <ScanProgress progress={progress} onCancel={handleCancel} />
          )}
          {view === 'results' && (
            <ResultsDashboard
              results={results}
              onReset={handleReset}
              folderPath={folderPath}
              onOptimize={() => setView('optimizer')}
            />
          )}
          {view === 'optimizer' && (
            <OptimizerView
              results={results}
              folderPath={folderPath}
              onBack={() => setView('results')}
            />
          )}
          {view === 'settings' && (
            <SettingsPage onBack={() => setView('picker')} />
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
