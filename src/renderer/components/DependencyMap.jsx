import React, { useState } from 'react';

export default function DependencyMap({ dependencies }) {
  const [expanded, setExpanded] = useState({});
  const refs = dependencies?.references || {};

  const toggle = (key) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (Object.keys(refs).length === 0) {
    return (
      <div className="deps-empty">
        <p>No cross-file dependencies detected.</p>
      </div>
    );
  }

  return (
    <div className="deps-section">
      <h3>Asset Dependencies</h3>
      <p className="deps-subtitle">Map/archetype files and the assets they reference</p>
      <div className="deps-list">
        {Object.entries(refs).map(([file, assets]) => (
          <div key={file} className="dep-group">
            <button
              className="dep-header"
              onClick={() => toggle(file)}
              aria-expanded={!!expanded[file]}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
              </svg>
              <span className="dep-filename">{file}</span>
              <span className="dep-count">{assets.length} references</span>
              <svg className={`dep-chevron ${expanded[file] ? 'expanded' : ''}`} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
            </button>
            {expanded[file] && (
              <ul className="dep-assets">
                {assets.map((asset) => (
                  <li key={asset}>{asset}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
