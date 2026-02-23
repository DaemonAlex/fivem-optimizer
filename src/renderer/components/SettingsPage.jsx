import React, { useState, useEffect, useCallback } from 'react';

const SETTING_GROUPS = [
  {
    title: 'Texture Limits (.ytd)',
    settings: [
      { key: 'maxTextureResolution', label: 'Max texture resolution (px)', type: 'number', min: 256, max: 8192 },
      { key: 'recommendedMaxResolution', label: 'Recommended max resolution (px)', type: 'number', min: 128, max: 4096 },
      { key: 'maxYtdSizeMB', label: 'Max YTD file size (MB)', type: 'number', min: 1, max: 16 },
    ],
  },
  {
    title: 'Vehicle/Fragment Limits (.yft)',
    settings: [
      { key: 'maxVehiclePolys', label: 'Max polygon count', type: 'number', min: 10000, max: 500000 },
      { key: 'recommendedMaxVehiclePolys', label: 'Recommended max polygons', type: 'number', min: 10000, max: 200000 },
      { key: 'maxBones', label: 'Max bone count', type: 'number', min: 32, max: 255 },
      { key: 'maxYftSizeMB', label: 'Max YFT file size (MB)', type: 'number', min: 1, max: 16 },
    ],
  },
  {
    title: 'Prop/Drawable Limits (.ydr)',
    settings: [
      { key: 'maxPropPolys', label: 'Max polygon count', type: 'number', min: 1000, max: 200000 },
      { key: 'recommendedMaxPropPolys', label: 'Recommended max polygons', type: 'number', min: 500, max: 100000 },
      { key: 'maxYdrSizeMB', label: 'Max YDR file size (MB)', type: 'number', min: 1, max: 16 },
    ],
  },
  {
    title: 'Collision Limits (.ybn)',
    settings: [
      { key: 'maxCollisionPolys', label: 'Max collision polygons', type: 'number', min: 500, max: 50000 },
      { key: 'maxYbnSizeMB', label: 'Max YBN file size (MB)', type: 'number', min: 1, max: 16 },
      { key: 'maxBoundsDimension', label: 'Max bounding box dimension (units)', type: 'number', min: 50, max: 5000 },
    ],
  },
  {
    title: 'General',
    settings: [
      { key: 'maxSingleFileMB', label: 'FiveM streaming limit (MB)', type: 'number', min: 1, max: 16 },
      { key: 'largeFileWarningMB', label: 'Large file warning threshold (MB)', type: 'number', min: 1, max: 16 },
      { key: 'minLodLevels', label: 'Minimum required LOD levels', type: 'number', min: 1, max: 5 },
      { key: 'recommendedLodLevels', label: 'Recommended LOD levels', type: 'number', min: 2, max: 5 },
    ],
  },
  {
    title: 'Optimizer',
    settings: [
      { key: 'optimizerTargetResolution', label: 'Default target resolution (px)', type: 'number', min: 128, max: 4096 },
      { key: 'optimizerMinResizeSize', label: 'Min file size to optimize (bytes)', type: 'number', min: 0, max: 16777216 },
    ],
  },
];

export default function SettingsPage({ onBack }) {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    window.electronAPI.getSettings().then(setSettings);
    window.electronAPI.getHistory().then(h => setHistory(h || []));
  }, []);

  const handleChange = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: Number(value) }));
    setSaved(false);
  }, []);

  const handleSave = useCallback(async () => {
    await window.electronAPI.setSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, [settings]);

  const handleClearHistory = useCallback(async () => {
    await window.electronAPI.clearHistory();
    setHistory([]);
  }, []);

  if (!settings) {
    return <div className="settings-view"><p>Loading settings...</p></div>;
  }

  return (
    <div className="settings-view">
      <div className="settings-header">
        <button className="back-btn" onClick={onBack} aria-label="Back to main view">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6" /></svg>
          Back
        </button>
        <h2>Settings</h2>
        <button className={`save-btn ${saved ? 'save-btn-saved' : ''}`} onClick={handleSave}>
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>

      <div className="settings-groups">
        {SETTING_GROUPS.map((group) => (
          <div key={group.title} className="settings-group">
            <h3>{group.title}</h3>
            <div className="settings-fields">
              {group.settings.map((s) => (
                <div key={s.key} className="settings-field">
                  <label htmlFor={s.key}>{s.label}</label>
                  <input
                    id={s.key}
                    type="number"
                    min={s.min}
                    max={s.max}
                    value={settings[s.key] ?? ''}
                    onChange={(e) => handleChange(s.key, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Scan History */}
      <div className="settings-group">
        <div className="history-header">
          <h3>Scan History</h3>
          {history.length > 0 && (
            <button className="clear-history-btn" onClick={handleClearHistory}>Clear History</button>
          )}
        </div>
        {history.length === 0 ? (
          <p className="history-empty">No previous scans.</p>
        ) : (
          <div className="history-list">
            {history.map((entry, i) => (
              <div key={i} className="history-item">
                <div className="history-folder">{entry.folder}</div>
                <div className="history-meta">
                  <span>{new Date(entry.timestamp).toLocaleString()}</span>
                  <span>{entry.summary?.total_files || 0} files</span>
                  <span>{entry.summary?.critical_count || 0} critical</span>
                  <span>{entry.summary?.warning_count || 0} warnings</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
