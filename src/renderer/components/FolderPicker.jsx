import React, { useState, useCallback } from 'react';

export default function FolderPicker({ folderPath, onSelectFolder, onDropFolder, onScan, error, pythonStatus }) {
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const files = e.dataTransfer?.files;
    if (files?.length > 0) {
      const item = files[0];
      // Use the path from the file object
      if (item.path) {
        onDropFolder(item.path);
      }
    }
  }, [onDropFolder]);

  const handleKeyDown = useCallback((e) => {
    if ((e.key === 'Enter' || e.key === ' ') && folderPath) {
      e.preventDefault();
      onScan();
    }
  }, [folderPath, onScan]);

  const pythonMissing = pythonStatus && !pythonStatus.found;

  return (
    <div
      className={`picker-view ${dragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onKeyDown={handleKeyDown}
    >
      <div className="picker-hero">
        <div className="picker-icon" aria-hidden="true">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <h1>FiveM Streaming Optimizer</h1>
        <p className="picker-subtitle">Scan your streaming assets to find optimization issues, oversized textures, high-poly models, and duplicate files.</p>
      </div>

      {pythonMissing && (
        <div className="python-missing-banner" role="alert">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--warning)" strokeWidth="2" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
          <div>
            <strong>Python not found</strong>
            <p>This app needs Python 3.10+ to analyze files. If you installed via the official installer, this should be bundled automatically.</p>
            <p>To fix manually: install Python 3.10+ from <span style={{ color: 'var(--accent)', userSelect: 'text' }}>python.org/downloads</span> and restart the app.</p>
          </div>
        </div>
      )}

      <div className={`picker-card ${dragOver ? 'picker-card-drag' : ''}`}>
        <div className="drop-zone" role="button" tabIndex={0} aria-label="Select or drop a streaming folder" onClick={onSelectFolder} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectFolder(); } }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
          </svg>
          {dragOver ? 'Drop folder here' : folderPath ? 'Change Folder' : 'Select or Drop Streaming Folder'}
        </div>

        {folderPath && (
          <div className="folder-path" aria-label={`Selected folder: ${folderPath}`}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" /></svg>
            <span>{folderPath}</span>
          </div>
        )}

        {error && (
          <div className="error-banner" role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></svg>
            <span>{error}</span>
          </div>
        )}

        <button
          className="scan-btn"
          onClick={onScan}
          disabled={!folderPath || pythonMissing}
          aria-label="Start analysis scan"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          Start Analysis
        </button>
      </div>

      <div className="picker-features" role="list">
        <div className="feature" role="listitem">
          <div className="feature-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="M21 15l-5-5L5 21" /></svg>
          </div>
          <h3>Textures</h3>
          <p>Detect oversized .ytd textures, compression issues, and VRAM usage</p>
        </div>
        <div className="feature" role="listitem">
          <div className="feature-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 002 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0022 16z" /></svg>
          </div>
          <h3>Models</h3>
          <p>Check poly counts, LOD levels, bone limits, and dependencies</p>
        </div>
        <div className="feature" role="listitem">
          <div className="feature-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="8.5" cy="7" r="4" /><line x1="20" y1="8" x2="20" y2="14" /><line x1="23" y1="11" x2="17" y2="11" /></svg>
          </div>
          <h3>Duplicates</h3>
          <p>Find duplicate assets wasting streaming memory</p>
        </div>
        <div className="feature" role="listitem">
          <div className="feature-icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" /></svg>
          </div>
          <h3>Memory</h3>
          <p>Calculate total streaming and VRAM memory footprint</p>
        </div>
      </div>
    </div>
  );
}
