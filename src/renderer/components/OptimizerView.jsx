import React, { useState, useMemo, useCallback } from 'react';
import LargeFilesTab from './LargeFilesTab';
import DuplicatesTab from './DuplicatesTab';
import TextureOptimizerTab from './TextureOptimizerTab';

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export default function OptimizerView({ results, folderPath, onBack }) {
  const [tab, setTab] = useState('large');

  const files = results?.files || [];
  const duplicates = results?.duplicates || [];

  const totalDuplicateWaste = useMemo(() => {
    return duplicates.reduce((sum, g) => sum + g.size * (g.files.length - 1), 0);
  }, [duplicates]);

  const handleShowInExplorer = useCallback(async (relPath) => {
    const fullPath = [folderPath, ...relPath.split(/[/\\]/)].join('\\');
    await window.electronAPI.showInExplorer(fullPath);
  }, [folderPath]);

  const largeFileCount = files.filter(f => f.size >= 8 * 1024 * 1024).length;
  const totalSize = files.reduce((s, f) => s + f.size, 0);

  return (
    <div className="optimizer-view">
      <div className="optimizer-header">
        <button className="back-btn" onClick={onBack} aria-label="Back to results">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
          Results
        </button>
        <div>
          <h2>Optimizer</h2>
          <p className="optimizer-subtitle">
            {files.length} files &middot; {formatBytes(totalSize)} total
            {duplicates.length > 0 && <> &middot; {formatBytes(totalDuplicateWaste)} duplicate waste</>}
          </p>
        </div>
      </div>

      {/* Summary cards */}
      <div className="optimizer-cards">
        <div className="opt-card">
          <span className="opt-card-value">{largeFileCount}</span>
          <span className="opt-card-label">Large Files (8 MB+)</span>
        </div>
        <div className="opt-card">
          <span className="opt-card-value">{duplicates.length}</span>
          <span className="opt-card-label">Duplicate Groups</span>
        </div>
        <div className="opt-card opt-card-accent">
          <span className="opt-card-value">{formatBytes(totalDuplicateWaste)}</span>
          <span className="opt-card-label">Potential Savings</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="results-tabs" role="tablist">
        <button
          role="tab"
          id="opt-tab-large"
          aria-selected={tab === 'large'}
          aria-controls="opt-tabpanel-large"
          className={`tab-btn ${tab === 'large' ? 'tab-active' : ''}`}
          onClick={() => setTab('large')}
        >
          Large Files
        </button>
        <button
          role="tab"
          id="opt-tab-duplicates"
          aria-selected={tab === 'duplicates'}
          aria-controls="opt-tabpanel-duplicates"
          className={`tab-btn ${tab === 'duplicates' ? 'tab-active' : ''}`}
          onClick={() => setTab('duplicates')}
        >
          Duplicates ({duplicates.length})
        </button>
        <button
          role="tab"
          id="opt-tab-textures"
          aria-selected={tab === 'textures'}
          aria-controls="opt-tabpanel-textures"
          className={`tab-btn ${tab === 'textures' ? 'tab-active' : ''}`}
          onClick={() => setTab('textures')}
        >
          Textures
        </button>
      </div>

      {tab === 'large' && (
        <LargeFilesTab
          files={files}
          formatBytes={formatBytes}
          onShowInExplorer={handleShowInExplorer}
        />
      )}

      {tab === 'duplicates' && (
        <DuplicatesTab
          duplicates={duplicates}
          folderPath={folderPath}
          formatBytes={formatBytes}
          onShowInExplorer={handleShowInExplorer}
        />
      )}

      {tab === 'textures' && (
        <TextureOptimizerTab
          folderPath={folderPath}
          formatBytes={formatBytes}
          onShowInExplorer={handleShowInExplorer}
        />
      )}
    </div>
  );
}
