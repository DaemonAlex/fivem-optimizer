import React, { useMemo } from 'react';

const SPINNER_CIRCUMFERENCE = 2 * Math.PI * 34;

export default function ScanProgress({ progress, onCancel }) {
  // Parse progress format: "pct%|current/total|message"
  const { percent, current, total, message } = useMemo(() => {
    if (!progress) return { percent: 0, current: 0, total: 0, message: 'Starting analysis...' };
    const parts = progress.split('|');
    if (parts.length >= 3) {
      const pctStr = parts[0].replace('%', '');
      const [cur, tot] = parts[1].split('/');
      return {
        percent: parseInt(pctStr) || 0,
        current: parseInt(cur) || 0,
        total: parseInt(tot) || 0,
        message: parts.slice(2).join('|'),
      };
    }
    return { percent: 0, current: 0, total: 0, message: progress };
  }, [progress]);

  return (
    <div className="scan-view" role="status" aria-live="polite">
      <div className="scan-spinner" aria-hidden="true">
        <svg className="spinner-svg" width="80" height="80" viewBox="0 0 80 80">
          <circle className="spinner-track" cx="40" cy="40" r="34" fill="none" stroke="var(--border)" strokeWidth="4" />
          <circle
            className="spinner-fill"
            cx="40" cy="40" r="34"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={SPINNER_CIRCUMFERENCE}
            strokeDashoffset={SPINNER_CIRCUMFERENCE * (1 - percent / 100)}
          />
          <text x="40" y="44" textAnchor="middle" fill="var(--text-primary)" fontSize="16" fontWeight="700" transform="rotate(90 40 40)">
            {percent}%
          </text>
        </svg>
      </div>
      <h2>Analyzing Assets</h2>
      {total > 0 && (
        <p className="scan-counter">{current} / {total} files</p>
      )}
      <p className="scan-status">{message}</p>
      <div className="progress-bar-container" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <button className="cancel-btn" onClick={onCancel} aria-label="Cancel analysis">Cancel</button>
    </div>
  );
}
