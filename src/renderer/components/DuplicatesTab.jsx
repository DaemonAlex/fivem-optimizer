import React, { useState, useMemo, useCallback } from 'react';

export default function DuplicatesTab({ duplicates, folderPath, formatBytes, onShowInExplorer }) {
  const [selectedDups, setSelectedDups] = useState(new Set());
  const [backupFolder, setBackupFolder] = useState(null);
  const [deleteStatus, setDeleteStatus] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const selectedDupFiles = useMemo(() => {
    const toDelete = [];
    for (const dup of duplicates) {
      if (selectedDups.has(dup.hash)) {
        toDelete.push(...dup.files.slice(1));
      }
    }
    return toDelete;
  }, [duplicates, selectedDups]);

  const selectedWaste = useMemo(() => {
    let waste = 0;
    for (const dup of duplicates) {
      if (selectedDups.has(dup.hash)) {
        waste += dup.size * (dup.files.length - 1);
      }
    }
    return waste;
  }, [duplicates, selectedDups]);

  const handleToggleDup = useCallback((hash) => {
    setSelectedDups(prev => {
      const next = new Set(prev);
      if (next.has(hash)) next.delete(hash);
      else next.add(hash);
      return next;
    });
  }, []);

  const handleSelectAllDups = useCallback(() => {
    if (selectedDups.size === duplicates.length) {
      setSelectedDups(new Set());
    } else {
      setSelectedDups(new Set(duplicates.map(d => d.hash)));
    }
  }, [duplicates, selectedDups]);

  const handleSelectBackup = useCallback(async () => {
    const folder = await window.electronAPI.selectBackupFolder();
    if (folder) setBackupFolder(folder);
  }, []);

  const handleDeleteSelected = useCallback(async () => {
    if (selectedDupFiles.length === 0) return;
    setDeleting(true);
    setDeleteStatus(null);
    try {
      const result = await window.electronAPI.deleteFiles(
        selectedDupFiles,
        backupFolder,
        folderPath
      );
      setDeleteStatus(result);
      if (result.deleted > 0) {
        setSelectedDups(new Set());
      }
    } catch (e) {
      setDeleteStatus({ deleted: 0, backed: 0, errors: [{ file: '', error: e.message }] });
    }
    setDeleting(false);
  }, [selectedDupFiles, backupFolder, folderPath]);

  return (
    <div className="opt-duplicates" role="tabpanel" id="opt-tabpanel-duplicates" aria-labelledby="opt-tab-duplicates">
      {duplicates.length === 0 ? (
        <div className="opt-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" aria-hidden="true"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
          <p>No duplicate files found across resources.</p>
        </div>
      ) : (
        <>
          <div className="opt-dup-toolbar">
            <div className="opt-dup-toolbar-left">
              <button className="opt-select-all-btn" onClick={handleSelectAllDups}>
                {selectedDups.size === duplicates.length ? 'Deselect All' : 'Select All'}
              </button>
              <span className="opt-dup-selected">
                {selectedDups.size} of {duplicates.length} groups selected
                {selectedWaste > 0 && <> &middot; {formatBytes(selectedWaste)} savings</>}
              </span>
            </div>
            <div className="opt-dup-toolbar-right">
              <button className="opt-backup-btn" onClick={handleSelectBackup}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>
                {backupFolder ? 'Change Backup' : 'Set Backup Folder'}
              </button>
              <button
                className="opt-delete-btn"
                disabled={selectedDupFiles.length === 0 || deleting}
                onClick={handleDeleteSelected}
              >
                {deleting ? 'Removing...' : `Remove ${selectedDupFiles.length} Duplicates`}
              </button>
            </div>
          </div>

          {backupFolder && (
            <div className="opt-backup-info">
              Backup folder: <span>{backupFolder}</span>
            </div>
          )}

          {!backupFolder && selectedDups.size > 0 && (
            <div className="opt-backup-warning">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
              No backup folder set. Files will be permanently deleted.
            </div>
          )}

          {deleteStatus && (
            <div className={`opt-delete-result ${deleteStatus.errors.length > 0 ? 'opt-delete-result-error' : ''}`}>
              {deleteStatus.deleted > 0 && (
                <span>Removed {deleteStatus.deleted} files.</span>
              )}
              {deleteStatus.backed > 0 && (
                <span> Backed up {deleteStatus.backed} files.</span>
              )}
              {deleteStatus.errors.length > 0 && (
                <span> {deleteStatus.errors.length} errors occurred.</span>
              )}
            </div>
          )}

          <div className="opt-dup-list">
            {duplicates.map((group) => {
              const isSelected = selectedDups.has(group.hash);
              const waste = group.size * (group.files.length - 1);
              return (
                <div key={group.hash} className={`opt-dup-group ${isSelected ? 'opt-dup-selected' : ''}`}>
                  <label className="opt-dup-header">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleToggleDup(group.hash)}
                      className="opt-dup-checkbox"
                    />
                    <div className="opt-dup-info">
                      <span className="opt-dup-name">{group.files[0].split(/[/\\]/).pop()}</span>
                      <span className="opt-dup-meta">
                        {group.files.length} copies &middot; {formatBytes(group.size)} each &middot;
                        <span className="opt-dup-waste"> {formatBytes(waste)} wasted</span>
                      </span>
                    </div>
                    <button
                      className="opt-action-btn"
                      onClick={(e) => { e.preventDefault(); onShowInExplorer(group.files[0]); }}
                      title="Show in Explorer"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" /></svg>
                    </button>
                  </label>
                  <div className="opt-dup-files">
                    {group.files.map((f, j) => (
                      <div key={f} className={`opt-dup-file ${j === 0 ? 'opt-dup-keep' : 'opt-dup-remove'}`}>
                        <span className="opt-dup-file-tag">{j === 0 ? 'KEEP' : 'REMOVE'}</span>
                        <span className="opt-dup-file-path">{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
