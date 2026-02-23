import React, { useState, useMemo, useCallback } from 'react';

const MIN_SIZE_OPTIONS = [
  { label: 'All files', value: 0 },
  { label: '> 1 MB', value: 1024 * 1024 },
  { label: '> 4 MB', value: 4 * 1024 * 1024 },
  { label: '> 8 MB', value: 8 * 1024 * 1024 },
  { label: '> 16 MB', value: 16 * 1024 * 1024 },
];

export default function LargeFilesTab({ files, formatBytes, onShowInExplorer }) {
  const [typeFilter, setTypeFilter] = useState('all');
  const [minSize, setMinSize] = useState(1024 * 1024);

  const fileTypes = useMemo(() => {
    const types = new Set(files.map(f => f.ext));
    return Array.from(types).sort();
  }, [files]);

  const filteredFiles = useMemo(() => {
    let list = files;
    if (typeFilter !== 'all') {
      list = list.filter(f => f.ext === typeFilter);
    }
    if (minSize > 0) {
      list = list.filter(f => f.size >= minSize);
    }
    return list;
  }, [files, typeFilter, minSize]);

  return (
    <div className="opt-large-files" role="tabpanel" id="opt-tabpanel-large" aria-labelledby="opt-tab-large">
      <div className="opt-filters">
        <div className="filter-group">
          <label htmlFor="opt-type">Type:</label>
          <select id="opt-type" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
            <option value="all">All Types</option>
            {fileTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label htmlFor="opt-size">Min Size:</label>
          <select id="opt-size" value={minSize} onChange={e => setMinSize(Number(e.target.value))}>
            {MIN_SIZE_OPTIONS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <span className="opt-filter-count">
          Showing {filteredFiles.length} of {files.length} files
        </span>
      </div>

      <div className="opt-file-list">
        <div className="opt-file-header-row">
          <span className="opt-col-name">File</span>
          <span className="opt-col-type">Type</span>
          <span className="opt-col-size">Size</span>
          <span className="opt-col-issues">Issues</span>
          <span className="opt-col-action"></span>
        </div>
        {filteredFiles.length === 0 ? (
          <div className="opt-empty">No files match the current filters.</div>
        ) : (
          filteredFiles.map((file) => (
            <div key={file.rel_path} className={`opt-file-row ${file.issues > 0 ? 'opt-file-has-issues' : ''}`}>
              <span className="opt-col-name opt-file-name" title={file.rel_path}>
                {file.rel_path}
              </span>
              <span className="opt-col-type">
                <span className="opt-type-badge">{file.ext}</span>
              </span>
              <span className="opt-col-size opt-file-size">
                {formatBytes(file.size)}
              </span>
              <span className="opt-col-issues">
                {file.issues > 0 && (
                  <span className="opt-issue-badge">{file.issues}</span>
                )}
              </span>
              <span className="opt-col-action">
                <button
                  className="opt-action-btn"
                  onClick={() => onShowInExplorer(file.rel_path)}
                  title="Show in Explorer"
                  aria-label={`Show ${file.rel_path} in Explorer`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" /></svg>
                </button>
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
