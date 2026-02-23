import React, { useState, useCallback } from 'react';

const CATEGORY_LABELS = {
  texture_quality: 'Texture Quality',
  polygon_count: 'Polygon Count',
  lod_bones: 'LODs & Bones',
  file_size: 'File Size',
  streaming_bounds: 'Streaming Bounds',
  duplicates: 'Duplicates',
  resource_config: 'Resource Config',
};

const FIX_TYPE_LABELS = {
  resize_textures: 'Resize',
  resize_texture: 'Resize',
  recompress_texture: 'Recompress',
};

const SEVERITY_ICONS = {
  critical: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
  warning: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  info: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  ),
};

export default function IssueCard({ issue, folderPath }) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => setExpanded(prev => !prev), []);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle();
    } else if (e.key === 'Escape' && expanded) {
      e.preventDefault();
      setExpanded(false);
    }
  }, [toggle, expanded]);

  const handleShowInExplorer = useCallback((e) => {
    e.stopPropagation();
    if (issue.file && folderPath) {
      const fullPath = folderPath + '\\' + issue.file.replace(/\//g, '\\');
      window.electronAPI.showInExplorer(fullPath);
    }
  }, [issue.file, folderPath]);

  return (
    <div
      className={`issue-card issue-${issue.severity}`}
      onClick={toggle}
      onKeyDown={handleKeyDown}
      role="listitem"
      tabIndex={0}
      aria-expanded={expanded}
    >
      <div className="issue-header">
        <div className={`issue-severity severity-${issue.severity}`}>
          {SEVERITY_ICONS[issue.severity]}
        </div>
        <div className="issue-info">
          <div className="issue-title">{issue.message}</div>
          <div className="issue-meta">
            <span className="issue-file" title={issue.file}>{issue.file?.split(/[/\\]/).pop()}</span>
            {issue.file_type && <span className="issue-type">{issue.file_type}</span>}
            {issue.category && CATEGORY_LABELS[issue.category] && (
              <span className="issue-category">{CATEGORY_LABELS[issue.category]}</span>
            )}
            {issue.fixable && (
              <span className="issue-fixable-badge">
                {FIX_TYPE_LABELS[issue.fix_type] || 'Fixable'}
              </span>
            )}
          </div>
        </div>
        <svg className={`issue-chevron ${expanded ? 'expanded' : ''}`} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
      </div>
      {expanded && (
        <div className="issue-details">
          <div className="issue-filepath">{issue.file}</div>
          {issue.recommendation && (
            <div className="issue-recommendation">
              <strong>Fix:</strong> {issue.recommendation}
            </div>
          )}
          {issue.details && (
            <div className="issue-extra">
              {Object.entries(issue.details).map(([k, v]) => (
                <div key={k} className="detail-row">
                  <span className="detail-key">{k.replace(/_/g, ' ')}:</span>
                  <span className="detail-value">{typeof v === 'number' ? v.toLocaleString() : String(v)}</span>
                </div>
              ))}
            </div>
          )}
          {/* Action buttons */}
          <div className="issue-actions">
            {folderPath && issue.file && (
              <button className="issue-action-btn" onClick={handleShowInExplorer} title="Show in Explorer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" /></svg>
                Open in Explorer
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
