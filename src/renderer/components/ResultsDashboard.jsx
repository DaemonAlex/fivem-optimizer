import React, { useState, useMemo, useCallback } from 'react';
import IssueCard from './IssueCard';
import DependencyMap from './DependencyMap';

const CATEGORY_CONFIG = [
  { key: 'texture_quality', label: 'Texture Quality' },
  { key: 'polygon_count', label: 'Polygon Count' },
  { key: 'lod_bones', label: 'LODs & Bones' },
  { key: 'file_size', label: 'File Size' },
  { key: 'streaming_bounds', label: 'Streaming Bounds' },
  { key: 'duplicates', label: 'Duplicates' },
  { key: 'resource_config', label: 'Resource Config' },
];

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

export default function ResultsDashboard({ results, onReset, folderPath, onOptimize }) {
  const [filter, setFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [categoryFilters, setCategoryFilters] = useState(new Set());
  const [tab, setTab] = useState('issues'); // issues | dependencies

  const summary = results?.summary || {};
  const issues = results?.issues || [];
  const duplicates = results?.duplicates || [];
  const fileStats = results?.file_stats || {};
  const dependencies = results?.dependencies || {};

  const filteredIssues = useMemo(() => {
    let filtered = issues;
    if (filter !== 'all') {
      filtered = filtered.filter(i => i.severity === filter);
    }
    if (typeFilter !== 'all') {
      filtered = filtered.filter(i => i.file_type === typeFilter);
    }
    if (categoryFilters.size > 0) {
      filtered = filtered.filter(i => categoryFilters.has(i.category));
    }
    return filtered.sort((a, b) => {
      const order = { critical: 0, warning: 1, info: 2 };
      return (order[a.severity] ?? 3) - (order[b.severity] ?? 3);
    });
  }, [issues, filter, typeFilter, categoryFilters]);

  const severityCounts = useMemo(() => {
    const counts = { critical: 0, warning: 0, info: 0 };
    issues.forEach(i => counts[i.severity] = (counts[i.severity] || 0) + 1);
    return counts;
  }, [issues]);

  const fileTypes = useMemo(() => {
    const types = new Set(issues.map(i => i.file_type).filter(Boolean));
    return Array.from(types).sort();
  }, [issues]);

  const categoryCounts = useMemo(() => {
    const counts = {};
    issues.forEach(i => {
      if (i.category) counts[i.category] = (counts[i.category] || 0) + 1;
    });
    return counts;
  }, [issues]);

  const toggleCategory = useCallback((key) => {
    setCategoryFilters(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const handleExportJSON = useCallback(async () => {
    const data = JSON.stringify(results, null, 2);
    await window.electronAPI.exportResults(data, 'json');
  }, [results]);

  const handleExportCSV = useCallback(async () => {
    const headers = ['Severity', 'Category', 'File', 'File Type', 'Message', 'Recommendation'];
    const rows = issues.map(i => [
      i.severity,
      i.category || '',
      `"${(i.file || '').replace(/"/g, '""')}"`,
      i.file_type || '',
      `"${(i.message || '').replace(/"/g, '""')}"`,
      `"${(i.recommendation || '').replace(/"/g, '""')}"`,
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    await window.electronAPI.exportResults(csv, 'csv');
  }, [issues]);

  const hasDeps = Object.keys(dependencies?.references || {}).length > 0;

  return (
    <div className="results-view">
      <div className="results-header">
        <div>
          <h2>Analysis Results</h2>
          <p className="results-subtitle">
            {summary.total_files || 0} files scanned &middot; {summary.total_size ? formatBytes(summary.total_size) : '0 B'} total
            {summary.vram_estimate > 0 && <> &middot; ~{formatBytes(summary.vram_estimate)} estimated VRAM</>}
          </p>
        </div>
        <div className="results-actions">
          <button className="optimize-btn" onClick={onOptimize} aria-label="Open optimizer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>
            Optimize
          </button>
          <div className="export-dropdown">
            <button className="export-btn" aria-label="Export results" aria-haspopup="true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Export
            </button>
            <div className="export-menu" role="menu">
              <button role="menuitem" onClick={handleExportJSON}>Export as JSON</button>
              <button role="menuitem" onClick={handleExportCSV}>Export as CSV</button>
            </div>
          </div>
          <button className="reset-btn" onClick={onReset} aria-label="Start a new scan">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 102.13-9.36L1 10" /></svg>
            New Scan
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="stat-cards" role="list">
        <button className={`stat-card stat-critical ${filter === 'critical' ? 'stat-active' : ''}`} onClick={() => setFilter(filter === 'critical' ? 'all' : 'critical')} aria-label={`Filter by critical: ${severityCounts.critical} issues`} role="listitem">
          <span className="stat-count">{severityCounts.critical}</span>
          <span className="stat-label">Critical</span>
        </button>
        <button className={`stat-card stat-warning ${filter === 'warning' ? 'stat-active' : ''}`} onClick={() => setFilter(filter === 'warning' ? 'all' : 'warning')} aria-label={`Filter by warning: ${severityCounts.warning} issues`} role="listitem">
          <span className="stat-count">{severityCounts.warning}</span>
          <span className="stat-label">Warnings</span>
        </button>
        <button className={`stat-card stat-info ${filter === 'info' ? 'stat-active' : ''}`} onClick={() => setFilter(filter === 'info' ? 'all' : 'info')} aria-label={`Filter by info: ${severityCounts.info} issues`} role="listitem">
          <span className="stat-count">{severityCounts.info}</span>
          <span className="stat-label">Info</span>
        </button>
        <div className="stat-card stat-memory" role="listitem">
          <span className="stat-count">{summary.total_size ? formatBytes(summary.total_size) : '—'}</span>
          <span className="stat-label">Streaming Memory</span>
        </div>
      </div>

      {/* File type breakdown */}
      {Object.keys(fileStats).length > 0 && (
        <div className="file-breakdown">
          <h3>File Breakdown</h3>
          <div className="breakdown-grid">
            {Object.entries(fileStats).map(([ext, stats]) => (
              <div key={ext} className="breakdown-item">
                <span className="breakdown-ext">{ext}</span>
                <span className="breakdown-count">{stats.count} files</span>
                <span className="breakdown-size">{formatBytes(stats.size)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      {hasDeps && (
        <div className="results-tabs" role="tablist">
          <button role="tab" id="tab-issues" aria-selected={tab === 'issues'} aria-controls="tabpanel-issues" className={`tab-btn ${tab === 'issues' ? 'tab-active' : ''}`} onClick={() => setTab('issues')}>
            Issues ({issues.length})
          </button>
          <button role="tab" id="tab-dependencies" aria-selected={tab === 'dependencies'} aria-controls="tabpanel-dependencies" className={`tab-btn ${tab === 'dependencies' ? 'tab-active' : ''}`} onClick={() => setTab('dependencies')}>
            Dependencies
          </button>
        </div>
      )}

      {/* Dependencies tab */}
      {tab === 'dependencies' && hasDeps && (
        <div role="tabpanel" id="tabpanel-dependencies" aria-labelledby="tab-dependencies">
          <DependencyMap dependencies={dependencies} />
        </div>
      )}

      {/* Issues tab */}
      {tab === 'issues' && (
        <div role="tabpanel" id="tabpanel-issues" aria-labelledby="tab-issues">
          {/* Duplicates */}
          {duplicates.length > 0 && (
            <div className="duplicates-section">
              <h3>Duplicate Files ({duplicates.length} groups)</h3>
              {duplicates.map((group) => (
                <div key={group.hash} className="duplicate-group">
                  <div className="duplicate-header">
                    <span className="duplicate-hash">{group.hash?.substring(0, 12)}...</span>
                    <span className="duplicate-size">{formatBytes(group.size)}</span>
                    <span className="duplicate-waste">Wasting {formatBytes(group.size * (group.files.length - 1))}</span>
                  </div>
                  <ul className="duplicate-files">
                    {group.files.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

          {/* Filters */}
          <div className="results-filters">
            <div className="filter-group">
              <label htmlFor="severity-filter">Severity:</label>
              <select id="severity-filter" value={filter} onChange={e => setFilter(e.target.value)}>
                <option value="all">All ({issues.length})</option>
                <option value="critical">Critical ({severityCounts.critical})</option>
                <option value="warning">Warning ({severityCounts.warning})</option>
                <option value="info">Info ({severityCounts.info})</option>
              </select>
            </div>
            {fileTypes.length > 1 && (
              <div className="filter-group">
                <label htmlFor="type-filter">File Type:</label>
                <select id="type-filter" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
                  <option value="all">All Types</option>
                  {fileTypes.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            )}
          </div>

          {/* Category chips */}
          {CATEGORY_CONFIG.some(c => categoryCounts[c.key] > 0) && (
            <div className="category-chips" role="group" aria-label="Filter by category">
              {CATEGORY_CONFIG.filter(c => categoryCounts[c.key] > 0).map(c => (
                <button
                  key={c.key}
                  className={`category-chip ${categoryFilters.has(c.key) ? 'chip-active' : ''}`}
                  onClick={() => toggleCategory(c.key)}
                  aria-pressed={categoryFilters.has(c.key)}
                >
                  {c.label}
                  <span className="chip-count">{categoryCounts[c.key]}</span>
                </button>
              ))}
            </div>
          )}

          {/* Issues list */}
          <div className="issues-list" role="list">
            {filteredIssues.length === 0 ? (
              <div className="no-issues">
                {issues.length === 0 ? (
                  <>
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" aria-hidden="true"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                    <p>No issues found! Your assets are well optimized.</p>
                  </>
                ) : (
                  <p>No issues match the current filter.</p>
                )}
              </div>
            ) : (
              filteredIssues.map((issue, i) => (
                <IssueCard key={`${issue.file}-${issue.severity}-${i}`} issue={issue} folderPath={folderPath} />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
