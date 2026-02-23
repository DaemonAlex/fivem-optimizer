import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';

export default function TextureOptimizerTab({ folderPath, formatBytes, onShowInExplorer }) {
  const [texPlan, setTexPlan] = useState(null);
  const [texLoading, setTexLoading] = useState(false);
  const [texProgress, setTexProgress] = useState('');
  const [texError, setTexError] = useState(null);
  const [texSelected, setTexSelected] = useState(new Set());
  const progressCleanupRef = useRef(null);

  const [optimizing, setOptimizing] = useState(false);
  const [optProgress, setOptProgress] = useState('');
  const [optResults, setOptResults] = useState(null);
  const [texBackupFolder, setTexBackupFolder] = useState(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const texOptimizable = useMemo(() => {
    if (!texPlan?.files) return [];
    return texPlan.files.filter(f => f.should_optimize);
  }, [texPlan]);

  const texSelectedFiles = useMemo(() => {
    if (!texPlan?.files) return [];
    return texPlan.files.filter(f => texSelected.has(f.rel_path));
  }, [texPlan, texSelected]);

  const texSelectedSavings = useMemo(() => {
    return texSelectedFiles.reduce((sum, f) => sum + (f.estimated_savings || 0), 0);
  }, [texSelectedFiles]);

  useEffect(() => {
    return () => {
      if (progressCleanupRef.current) {
        progressCleanupRef.current();
        progressCleanupRef.current = null;
      }
    };
  }, []);

  const handleAnalyzeTextures = useCallback(async () => {
    if (!folderPath) return;
    setTexLoading(true);
    setTexError(null);
    setTexPlan(null);
    setTexProgress('Starting texture analysis...');
    setTexSelected(new Set());

    if (progressCleanupRef.current) {
      progressCleanupRef.current();
    }
    progressCleanupRef.current = window.electronAPI.onOptimizerProgress((msg) => {
      setTexProgress(msg);
    });

    try {
      const plan = await window.electronAPI.analyzePlan(folderPath);
      setTexPlan(plan);
      if (plan.files) {
        const optimizable = plan.files.filter(f => f.should_optimize).map(f => f.rel_path);
        setTexSelected(new Set(optimizable));
      }
    } catch (e) {
      setTexError(e.message);
    } finally {
      setTexLoading(false);
      setTexProgress('');
      if (progressCleanupRef.current) {
        progressCleanupRef.current();
        progressCleanupRef.current = null;
      }
    }
  }, [folderPath]);

  const handleCancelTexAnalysis = useCallback(() => {
    window.electronAPI.cancelOptimizer();
    setTexLoading(false);
    setTexProgress('');
  }, []);

  const handleToggleTexFile = useCallback((relPath) => {
    setTexSelected(prev => {
      const next = new Set(prev);
      if (next.has(relPath)) next.delete(relPath);
      else next.add(relPath);
      return next;
    });
  }, []);

  const handleSelectAllTex = useCallback(() => {
    if (texSelected.size === texOptimizable.length) {
      setTexSelected(new Set());
    } else {
      setTexSelected(new Set(texOptimizable.map(f => f.rel_path)));
    }
  }, [texOptimizable, texSelected]);

  const handleSelectTexBackup = useCallback(async () => {
    const folder = await window.electronAPI.selectBackupFolder();
    if (folder) setTexBackupFolder(folder);
  }, []);

  const handleExecuteOptimization = useCallback(async () => {
    setShowConfirmDialog(false);
    setOptimizing(true);
    setOptResults(null);
    setOptProgress('Starting optimization...');

    if (progressCleanupRef.current) {
      progressCleanupRef.current();
    }
    progressCleanupRef.current = window.electronAPI.onOptimizerProgress((msg) => {
      setOptProgress(msg);
    });

    try {
      const payload = {
        folder_path: folderPath,
        selected_files: Array.from(texSelected),
        backup_folder: texBackupFolder,
        target_resolution: texPlan?.target_resolution || 1024,
      };
      const result = await window.electronAPI.optimizeTextures(payload);
      setOptResults(result);
    } catch (e) {
      setOptResults({
        status: 'error',
        files_processed: 0,
        files_succeeded: 0,
        files_failed: 0,
        files_skipped: 0,
        errors: [{ file: '', error: e.message }],
      });
    } finally {
      setOptimizing(false);
      setOptProgress('');
      if (progressCleanupRef.current) {
        progressCleanupRef.current();
        progressCleanupRef.current = null;
      }
    }
  }, [folderPath, texSelected, texBackupFolder, texPlan]);

  const handleCancelOptimization = useCallback(() => {
    window.electronAPI.cancelOptimizer();
    setOptimizing(false);
    setOptProgress('');
  }, []);

  const handleDismissResults = useCallback(() => {
    setOptResults(null);
  }, []);

  const texProgressParsed = useMemo(() => {
    if (!texProgress) return { pct: 0, status: '' };
    const parts = texProgress.split('|');
    if (parts.length >= 3) {
      return { pct: parseInt(parts[0]) || 0, count: parts[1], status: parts[2] };
    }
    return { pct: 0, status: texProgress };
  }, [texProgress]);

  const optProgressParsed = useMemo(() => {
    if (!optProgress) return { pct: 0, status: '' };
    const parts = optProgress.split('|');
    if (parts.length >= 3) {
      return { pct: parseInt(parts[0]) || 0, count: parts[1], status: parts[2] };
    }
    return { pct: 0, status: optProgress };
  }, [optProgress]);

  return (
    <div className="opt-textures" role="tabpanel" id="opt-tabpanel-textures" aria-labelledby="opt-tab-textures">
      {/* Not yet analyzed */}
      {!texPlan && !texLoading && !texError && (
        <div className="opt-tex-start">
          <div className="opt-tex-start-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" aria-hidden="true">
              <rect x="2" y="2" width="20" height="20" rx="2" />
              <path d="M7 2v20" /><path d="M17 2v20" /><path d="M2 7h20" /><path d="M2 17h20" />
            </svg>
          </div>
          <h3>Texture Optimization</h3>
          <p className="opt-tex-start-desc">
            Scan all .ytd files to identify oversized textures that can be safely resized.
            This analysis checks texture dimensions, formats, and types to create an optimization plan.
          </p>
          <button className="opt-tex-analyze-btn" onClick={handleAnalyzeTextures}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
            Analyze Textures
          </button>
        </div>
      )}

      {/* Loading state */}
      {texLoading && (
        <div className="opt-tex-loading">
          <div className="opt-tex-spinner">
            <svg width="40" height="40" viewBox="0 0 40 40">
              <circle cx="20" cy="20" r="16" fill="none" stroke="var(--border)" strokeWidth="3" />
              <circle
                cx="20" cy="20" r="16" fill="none"
                stroke="var(--accent)" strokeWidth="3"
                strokeDasharray="100.53"
                strokeDashoffset={100.53 - (100.53 * texProgressParsed.pct / 100)}
                strokeLinecap="round"
                style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
              />
            </svg>
            <span className="opt-tex-spinner-pct">{texProgressParsed.pct}%</span>
          </div>
          <p className="opt-tex-loading-status">{texProgressParsed.status || 'Scanning textures...'}</p>
          {texProgressParsed.count && (
            <p className="opt-tex-loading-count">{texProgressParsed.count}</p>
          )}
          <button className="cancel-btn" onClick={handleCancelTexAnalysis}>Cancel</button>
        </div>
      )}

      {/* Error state */}
      {texError && (
        <div className="opt-tex-error">
          <div className="error-banner">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></svg>
            {texError}
          </div>
          <button className="opt-tex-analyze-btn" onClick={handleAnalyzeTextures} style={{ marginTop: 12 }}>
            Retry Analysis
          </button>
        </div>
      )}

      {/* Results */}
      {texPlan && !texLoading && (
        <>
          {texPlan.status === 'no_files' ? (
            <div className="opt-empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" aria-hidden="true"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
              <p>{texPlan.message}</p>
            </div>
          ) : (
            <>
              {/* Texture summary cards */}
              <div className="opt-tex-summary">
                <div className="opt-tex-stat">
                  <span className="opt-tex-stat-value">{texPlan.total_files}</span>
                  <span className="opt-tex-stat-label">YTD Files Scanned</span>
                </div>
                <div className="opt-tex-stat">
                  <span className="opt-tex-stat-value opt-tex-stat-highlight">{texPlan.optimizable_files}</span>
                  <span className="opt-tex-stat-label">Can Be Optimized</span>
                </div>
                <div className="opt-tex-stat">
                  <span className="opt-tex-stat-value">{formatBytes(texPlan.total_size)}</span>
                  <span className="opt-tex-stat-label">Total Size</span>
                </div>
                <div className="opt-tex-stat opt-tex-stat-accent">
                  <span className="opt-tex-stat-value">{formatBytes(texPlan.estimated_savings)}</span>
                  <span className="opt-tex-stat-label">Est. Savings</span>
                </div>
              </div>

              {/* Optimization results banner */}
              {optResults && (
                <div className="opt-tex-results">
                  <div className="opt-tex-results-header">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={optResults.files_failed > 0 ? 'var(--warning)' : 'var(--success)'} strokeWidth="2">
                      {optResults.files_failed > 0 ? (
                        <><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></>
                      ) : (
                        <><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></>
                      )}
                    </svg>
                    <div className="opt-tex-results-text">
                      <strong>Optimization Complete</strong>
                      <div className="opt-tex-result-stats">
                        <span className="opt-tex-result-stat opt-tex-result-success">{optResults.files_succeeded} optimized</span>
                        {optResults.files_skipped > 0 && (
                          <span className="opt-tex-result-stat">{optResults.files_skipped} skipped</span>
                        )}
                        {optResults.files_failed > 0 && (
                          <span className="opt-tex-result-stat opt-tex-result-error">{optResults.files_failed} failed</span>
                        )}
                      </div>
                      {optResults.errors.length > 0 && (
                        <div className="opt-tex-result-errors">
                          {optResults.errors.slice(0, 5).map((err, i) => (
                            <div key={`${err.file}-${i}`} className="opt-tex-result-error-item">
                              {err.file && <span className="opt-tex-result-error-file">{err.file}:</span>}
                              {err.error}
                            </div>
                          ))}
                          {optResults.errors.length > 5 && (
                            <div className="opt-tex-result-error-item">...and {optResults.errors.length - 5} more</div>
                          )}
                        </div>
                      )}
                    </div>
                    <button className="opt-action-btn" onClick={handleDismissResults} title="Dismiss">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                    </button>
                  </div>
                </div>
              )}

              {/* Optimizing progress */}
              {optimizing && (
                <div className="opt-tex-loading">
                  <div className="opt-tex-spinner">
                    <svg width="40" height="40" viewBox="0 0 40 40">
                      <circle cx="20" cy="20" r="16" fill="none" stroke="var(--border)" strokeWidth="3" />
                      <circle
                        cx="20" cy="20" r="16" fill="none"
                        stroke="var(--success)" strokeWidth="3"
                        strokeDasharray="100.53"
                        strokeDashoffset={100.53 - (100.53 * optProgressParsed.pct / 100)}
                        strokeLinecap="round"
                        style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
                      />
                    </svg>
                    <span className="opt-tex-spinner-pct">{optProgressParsed.pct}%</span>
                  </div>
                  <p className="opt-tex-loading-status">{optProgressParsed.status || 'Optimizing textures...'}</p>
                  {optProgressParsed.count && (
                    <p className="opt-tex-loading-count">{optProgressParsed.count}</p>
                  )}
                  <button className="cancel-btn" onClick={handleCancelOptimization}>Cancel</button>
                </div>
              )}

              {/* Confirmation dialog overlay */}
              {showConfirmDialog && (
                <div className="opt-tex-confirm-overlay" onClick={() => setShowConfirmDialog(false)}>
                  <div className="opt-tex-confirm-dialog" onClick={e => e.stopPropagation()}>
                    <h3>Confirm Optimization</h3>
                    <div className="opt-tex-confirm-details">
                      <div className="opt-tex-confirm-row">
                        <span>Files to optimize:</span>
                        <strong>{texSelected.size}</strong>
                      </div>
                      <div className="opt-tex-confirm-row">
                        <span>Target resolution:</span>
                        <strong>{texPlan.target_resolution}px</strong>
                      </div>
                      <div className="opt-tex-confirm-row">
                        <span>Estimated savings:</span>
                        <strong>{formatBytes(texSelectedSavings)}</strong>
                      </div>
                      <div className="opt-tex-confirm-row">
                        <span>Backup folder:</span>
                        <strong>{texBackupFolder || <span style={{ color: 'var(--warning)' }}>None (no backup!)</span>}</strong>
                      </div>
                    </div>
                    {!texBackupFolder && (
                      <div className="opt-backup-warning" style={{ marginTop: 12 }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
                        No backup folder set. Changes cannot be undone!
                      </div>
                    )}
                    <div className="opt-tex-confirm-actions">
                      <button className="cancel-btn" onClick={() => setShowConfirmDialog(false)}>Cancel</button>
                      <button className="opt-tex-execute-btn" onClick={handleExecuteOptimization}>
                        Optimize {texSelected.size} Files
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Execute toolbar + info banner */}
              {!optimizing && (
                <>
                  <div className="opt-tex-execute-bar">
                    <div className="opt-dup-toolbar-left">
                      <button className="opt-backup-btn" onClick={handleSelectTexBackup}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
                        {texBackupFolder ? 'Change Backup' : 'Set Backup Folder'}
                      </button>
                      {texBackupFolder && (
                        <span className="opt-tex-backup-path" title={texBackupFolder}>
                          {texBackupFolder.length > 40 ? '...' + texBackupFolder.slice(-37) : texBackupFolder}
                        </span>
                      )}
                    </div>
                    <div className="opt-dup-toolbar-right">
                      <button
                        className="opt-tex-execute-btn"
                        disabled={texSelected.size === 0}
                        onClick={() => setShowConfirmDialog(true)}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z" /><polyline points="13 2 13 9 20 9" /><path d="M9 15l2 2 4-4" /></svg>
                        Optimize Selected ({texSelected.size})
                      </button>
                    </div>
                  </div>

                  <div className="opt-tex-info-banner">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></svg>
                    <div>
                      In-place mipmap replacement &mdash; downsizes textures to {texPlan.target_resolution}px by
                      copying lower mip levels. Files stay the same size (freed space is zeroed).
                    </div>
                  </div>
                </>
              )}

              {/* Toolbar */}
              {!optimizing && (
                <div className="opt-tex-toolbar">
                  <div className="opt-dup-toolbar-left">
                    <button className="opt-select-all-btn" onClick={handleSelectAllTex}>
                      {texSelected.size === texOptimizable.length ? 'Deselect All' : 'Select All'}
                    </button>
                    <span className="opt-dup-selected">
                      {texSelected.size} of {texOptimizable.length} files selected
                      {texSelectedSavings > 0 && <> &middot; ~{formatBytes(texSelectedSavings)} est. savings</>}
                    </span>
                  </div>
                  <div className="opt-dup-toolbar-right">
                    <button className="opt-tex-rescan-btn" onClick={handleAnalyzeTextures}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 102.13-9.36L1 10" /></svg>
                      Re-scan
                    </button>
                  </div>
                </div>
              )}

              {/* File list */}
              <div className="opt-file-list">
                <div className="opt-file-header-row opt-tex-header">
                  <span className="opt-col-check"></span>
                  <span className="opt-col-name">File</span>
                  <span className="opt-col-dim">Max Dimension</span>
                  <span className="opt-col-size">Size</span>
                  <span className="opt-col-savings">Est. Savings</span>
                  <span className="opt-col-action"></span>
                </div>
                {texPlan.files.map((file) => {
                  const isOptimizable = file.should_optimize;
                  const isSelected = texSelected.has(file.rel_path);
                  return (
                    <div
                      key={file.rel_path}
                      className={`opt-file-row opt-tex-row ${isOptimizable ? '' : 'opt-tex-row-skip'} ${isSelected ? 'opt-tex-row-selected' : ''}`}
                    >
                      <span className="opt-col-check">
                        {isOptimizable && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleTexFile(file.rel_path)}
                            className="opt-dup-checkbox"
                          />
                        )}
                      </span>
                      <span className="opt-col-name opt-file-name" title={file.rel_path}>
                        {file.rel_path}
                        {file.has_script_rt && <span className="opt-tex-tag opt-tex-tag-danger">script_rt</span>}
                        {file.has_emissive && <span className="opt-tex-tag opt-tex-tag-warn">emissive</span>}
                      </span>
                      <span className="opt-col-dim">
                        {file.max_dimension > 0 ? `${file.max_dimension}px` : '?'}
                      </span>
                      <span className="opt-col-size opt-file-size">
                        {formatBytes(file.size)}
                      </span>
                      <span className="opt-col-savings">
                        {isOptimizable ? (
                          <span className="opt-tex-savings">
                            ~{formatBytes(file.estimated_savings)}
                            <span className="opt-tex-savings-pct">-{file.estimated_savings_pct}%</span>
                          </span>
                        ) : (
                          <span className="opt-tex-skip-reason" title={file.skip_reason}>
                            {file.skip_reason}
                          </span>
                        )}
                      </span>
                      <span className="opt-col-action">
                        <button
                          className="opt-action-btn"
                          onClick={() => onShowInExplorer(file.rel_path)}
                          title="Show in Explorer"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" /></svg>
                        </button>
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
