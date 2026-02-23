import React, { useState, useEffect } from 'react';

export default function TitleBar({ onSettingsClick, showBack }) {
  const [maximized, setMaximized] = useState(false);
  const [updateReady, setUpdateReady] = useState(null); // version string when update downloaded
  const [appVersion, setAppVersion] = useState('');

  useEffect(() => {
    window.electronAPI.isMaximized().then(setMaximized);
    const removeListener = window.electronAPI.onMaximized(setMaximized);
    return removeListener;
  }, []);

  useEffect(() => {
    window.electronAPI.getAppVersion().then(setAppVersion);
    const cleanupDownloaded = window.electronAPI.onUpdateDownloaded((version) => {
      setUpdateReady(version);
    });
    return cleanupDownloaded;
  }, []);

  return (
    <header className="titlebar" role="banner">
      <div className="titlebar-drag">
        <div className="titlebar-logo">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span>FiveM Optimizer</span>
          {appVersion && <span className="titlebar-version">v{appVersion}</span>}
        </div>
      </div>
      {updateReady && (
        <button
          className="titlebar-update-btn"
          onClick={() => window.electronAPI.installUpdate()}
          title={`Update to v${updateReady} — click to restart`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="7 13 12 18 17 13" /><line x1="12" y1="18" x2="12" y2="6" /><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /></svg>
          Update ready
        </button>
      )}
      <div className="titlebar-actions">
        <button
          className="titlebar-btn titlebar-settings-btn"
          onClick={onSettingsClick}
          aria-label={showBack ? 'Back' : 'Settings'}
          title={showBack ? 'Back' : 'Settings'}
        >
          {showBack ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" /></svg>
          )}
        </button>
      </div>
      <div className="titlebar-controls">
        <button className="titlebar-btn" onClick={() => window.electronAPI.minimize()} aria-label="Minimize">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><rect y="5" width="12" height="1.5" fill="currentColor" /></svg>
        </button>
        <button className="titlebar-btn" onClick={() => window.electronAPI.maximize()} aria-label={maximized ? 'Restore' : 'Maximize'}>
          {maximized ? (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <rect x="1.5" y="3" width="7.5" height="7.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
              <path d="M3 3V1.5h7.5V9H9" fill="none" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <rect x="1" y="1" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          )}
        </button>
        <button className="titlebar-btn titlebar-btn-close" onClick={() => window.electronAPI.close()} aria-label="Close">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M1 1l10 10M11 1L1 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
    </header>
  );
}
