export function scoreColor(score) {
  if (score >= 85) return 'var(--green)';
  if (score >= 70) return 'var(--accent)';
  if (score >= 50) return 'var(--yellow)';
  if (score >= 30) return 'var(--orange)';
  return 'var(--red)';
}

export function nxStatCard(value, label, color, subtitle) {
  const c = color || 'var(--accent)';
  return `<div class="nx-stat-card">
    <div class="nx-stat-indicator" style="background:${c}"></div>
    <div class="nx-stat-value" style="color:${c}">${value}</div>
    <div class="nx-stat-title">${label}</div>
    ${subtitle ? `<div class="nx-stat-subtitle">${subtitle}</div>` : ''}
  </div>`;
}

export function nxGauge(score, label, grade) {
  const c = 283;
  const offset = c - (score / 100) * c;
  const color = scoreColor(score);
  return `<div class="nx-card nx-gauge">
    <div class="nx-gauge-ring"><svg viewBox="0 0 100 100">
      <circle class="nx-gauge-bg" cx="50" cy="50" r="45"/>
      <circle class="nx-gauge-fg" cx="50" cy="50" r="45" stroke="${color}" stroke-dasharray="${c}" stroke-dashoffset="${offset}"/>
    </svg><div class="nx-gauge-value" style="color:${color}">${score}</div></div>
    <div style="text-align:center;font-weight:600;color:${color}">${grade}</div>
    <div class="nx-gauge-label">${label}</div>
  </div>`;
}

export function nxAlert(text, level) {
  const lvl = level || 'info';
  const cls = { success: 'nx-alert-success', warning: 'nx-alert-warning', critical: 'nx-alert-danger', danger: 'nx-alert-danger', info: 'nx-alert-info' };
  return `<div class="nx-alert ${cls[lvl] || cls.info}" role="alert"><div class="nx-alert-content">${text}</div></div>`;
}

export function nxTable(headers, rows, opts) {
  const caption = (opts && opts.caption) ? `<caption>${opts.caption}</caption>` : '';
  let h = `<table class="nx-table">${caption}<thead><tr>` + headers.map(function(h) { return '<th>' + h + '</th>'; }).join('') + '</tr></thead><tbody>';
  for (const row of rows) h += '<tr>' + row.map(function(c) { return '<td>' + c + '</td>'; }).join('') + '</tr>';
  return h + '</tbody></table>';
}

export function nxLoader(text) {
  return `<div class="nx-loader"><div class="nx-loader-spinner"></div><div class="nx-loader-text">${text || 'Chargement…'}</div></div>`;
}

export function nxEmpty(message) {
  return `<div class="nx-empty"><div class="nx-empty-message">${message}</div></div>`;
}

export function nxBadge(text, variant) {
  return `<span class="nx-badge nx-badge-${variant || 'neutral'}">${text}</span>`;
}
