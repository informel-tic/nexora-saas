import { api, apiPost } from './api.js';
import { scoreColor, nxStatCard, nxGauge, nxAlert, nxTable, nxLoader, nxEmpty, nxBadge } from './components.js';

export async function loadDashboard(sec) {
  const [dash, health] = await Promise.all([api('dashboard'), api('health')]);
  document.getElementById('health-badge').textContent = health.status === 'ok' ? 'online' : 'offline';
  const node = dash.node || {};

  let html = `<div class="nx-grid nx-grid-4 mb">
    ${nxStatCard(node.apps_count || 0, 'Applications')}
    ${nxStatCard(node.domains_count || 0, 'Domaines')}
    ${nxStatCard(node.backups_count || 0, 'Sauvegardes')}
    ${nxStatCard((node.health_score || 0) + '%', 'Santé', scoreColor(node.health_score || 0))}
  </div>`;

  if (dash.alerts && dash.alerts.length) {
    html += dash.alerts.map(function(a) { return nxAlert(a, 'warning'); }).join('');
  } else {
    html += nxAlert('Aucune alerte active', 'success');
  }

  const apps = (dash.top_apps || []).slice(0, 8);
  const svcs = (dash.services || []).slice(0, 10);

  html += `<div class="nx-grid nx-grid-2 mt">
    <div class="nx-card"><div class="nx-card-header"><h3>Applications récentes</h3></div>
      <ul class="item-list">${apps.length ? apps.map(function(a) {
        const name = a.name || a.label || a.id || 'app';
        return '<li><span>' + name + '</span><span style="color:var(--muted);font-size:var(--text-xs)">' + (a.version || '') + '</span></li>';
      }).join('') : '<li style="color:var(--muted)">Aucune application</li>'}</ul>
    </div>
    <div class="nx-card"><div class="nx-card-header"><h3>Services</h3></div>
      <ul class="item-list">${svcs.length ? svcs.map(function(s) {
        const st = s.status || s.active || '?';
        const dot = st === 'running' ? 'status-running' : st === 'inactive' ? 'status-stopped' : 'status-warning';
        return '<li><span><span class="status-dot ' + dot + '"></span>' + s.name + '</span><span style="color:var(--muted);font-size:var(--text-xs)">' + st + '</span></li>';
      }).join('') : '<li style="color:var(--muted)">Aucun service</li>'}</ul>
    </div>
  </div>`;

  sec.innerHTML = html;
}

export async function loadScores(sec) {
  const [scores, report] = await Promise.all([api('scores'), api('governance/report')]);
  let html = `<div class="nx-grid nx-grid-4 mb">${[
    nxGauge(scores.security?.score || 0, 'Sécurité', scores.security?.grade || '-'),
    nxGauge(scores.pra?.score || 0, 'PRA', scores.pra?.grade || '-'),
    nxGauge(scores.health?.score || 0, 'Santé', scores.health?.grade || '-'),
    nxGauge(scores.compliance?.score || 0, 'Conformité', scores.compliance?.level || '-')
  ].join('')}</div>`;

  const priorities = report.priorities || [];
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Priorités d'action</h3></div>`;
  html += priorities.length
    ? '<ul class="item-list">' + priorities.map(function(p) { return '<li>' + p + '</li>'; }).join('') + '</ul>'
    : nxAlert('Aucune action prioritaire', 'success');
  html += '</div>';
  sec.innerHTML = html;
}

export async function loadApps(sec) {
  const data = await api('inventory/apps');
  const apps = data.apps || [];
  if (!apps.length) { sec.innerHTML = nxEmpty('Aucune application installée'); return; }
  sec.innerHTML = `<div class="nx-card"><div class="nx-card-header"><h3>Applications installées</h3></div>` +
    nxTable(['Application', 'Version', 'ID'], apps.map(function(a) {
      return [a.name || a.label || a.id, a.version || '-', a.id || '-'];
    })) + '</div>';
}

export async function loadServices(sec) {
  const data = await api('inventory/services');
  const svcs = Object.entries(data || {});
  if (!svcs.length) { sec.innerHTML = nxEmpty('Aucun service'); return; }
  sec.innerHTML = `<div class="nx-card"><div class="nx-card-header"><h3>État des services</h3></div>
    <ul class="item-list">${svcs.map(function([name, info]) {
      const st = (typeof info === 'object' ? info.status || info.active : info) || '?';
      const dot = st === 'running' ? 'status-running' : st === 'inactive' || st === 'dead' ? 'status-stopped' : 'status-warning';
      return '<li><span><span class="status-dot ' + dot + '"></span>' + name + '</span><span style="color:var(--muted)">' + st + '</span></li>';
    }).join('')}</ul></div>`;
}

export async function loadDomains(sec) {
  const [domains, certs] = await Promise.all([api('inventory/domains'), api('inventory/certs')]);
  const domList = domains.domains || [];
  const certMap = (certs || {}).certificates || certs || {};
  const certEntries = Object.entries(certMap);

  let html = `<div class="nx-grid nx-grid-2">
    <div class="nx-card"><div class="nx-card-header"><h3>Domaines</h3></div>`;
  html += domList.length
    ? '<ul class="item-list">' + domList.map(function(d) { return '<li>' + d + '</li>'; }).join('') + '</ul>'
    : nxEmpty('Aucun domaine');
  html += `</div><div class="nx-card"><div class="nx-card-header"><h3>Certificats</h3></div>`;
  html += certEntries.length
    ? nxTable(['Domaine', 'Validité', 'Style'], certEntries.map(function([d, info]) {
        const v = typeof info === 'object' ? info.validity || '-' : info;
        const s = typeof info === 'object' ? info.style || '-' : '-';
        return [d, v, s];
      }))
    : nxEmpty('Aucun certificat');
  html += '</div></div>';
  sec.innerHTML = html;
}

export async function loadSecurity(sec) {
  const [posture, risks] = await Promise.all([api('security/posture'), api('governance/risks')]);

  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Posture de sécurité</h3></div>
    <div class="nx-grid nx-grid-3 mb">
      ${nxStatCard(posture.security_score || '-', 'Score sécurité', scoreColor(posture.security_score || 0))}
      ${nxStatCard(posture.permissions_risk_count || 0, 'Permissions publiques', 'var(--orange)')}
      ${nxStatCard((posture.alerts || []).length, 'Alertes', (posture.alerts || []).length > 0 ? 'var(--red)' : 'var(--green)')}
    </div>`;
  if ((posture.public_permissions || []).length) {
    html += (posture.public_permissions || []).map(function(p) { return nxAlert('Public: ' + p, 'warning'); }).join('');
  }
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Registre des risques</h3></div>`;
  const riskList = risks.risks || [];
  html += riskList.length
    ? nxTable(['ID', 'Catégorie', 'Sévérité', 'Description'], riskList.map(function(r) {
        const sevColor = r.severity === 'critical' ? 'var(--red)' : r.severity === 'high' ? 'var(--orange)' : 'var(--yellow)';
        return [r.id, r.category, '<span style="color:' + sevColor + '">' + r.severity + '</span>', r.description];
      }))
    : nxAlert('Aucun risque identifié', 'success');
  html += '</div>';
  sec.innerHTML = html;
}

export async function loadPra(sec) {
  const data = await api('pra');
  let html = `<div class="nx-grid nx-grid-3 mb">
    ${nxStatCard(data.pra_score || '-', 'Score PRA', scoreColor(data.pra_score || 0))}
    ${nxStatCard(data.backups_count || 0, 'Sauvegardes', 'var(--blue)')}
    ${nxStatCard((data.runbooks || []).length, 'Runbooks', 'var(--purple)')}
  </div>`;

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Runbooks disponibles</h3></div>`;
  const runbooks = data.runbooks || [];
  html += runbooks.length
    ? '<ul class="item-list">' + runbooks.map(function(r) { return '<li>' + r + '</li>'; }).join('') + '</ul>'
    : nxEmpty('Aucun runbook');
  html += '</div>';

  html += `<div class="nx-card mt"><div class="nx-card-header"><h3>Actions PRA</h3></div>
    <div class="nx-actions">
      <button class="nx-btn nx-btn-sm nx-btn-outline" onclick="window.praAction('snapshot')">Snapshot</button>
      <button class="nx-btn nx-btn-sm nx-btn-outline" onclick="window.praAction('readiness')">Vérifier readiness</button>
      <button class="nx-btn nx-btn-sm nx-btn-outline" onclick="window.praAction('export')">Export config</button>
    </div>
    <div id="pra-action-result" class="mt"></div>
  </div>`;
  sec.innerHTML = html;
}

export async function loadFleet(sec, NexoraConsoleObj) {
  const [fleet, topo] = await Promise.all([api('fleet'), api('fleet/topology').catch(function() { return null; })]);
  const nodes = fleet.nodes || [];

  let html = `<div class="nx-grid nx-grid-4 mb">
    ${nxStatCard(fleet.total_nodes || 0, 'Nœuds', 'var(--accent)')}
    ${nxStatCard(fleet.total_apps || 0, 'Apps total', 'var(--blue)')}
    ${nxStatCard(fleet.total_domains || 0, 'Domaines total', 'var(--purple)')}
    ${nxStatCard((fleet.overall_health_score || 0) + '%', 'Santé globale', scoreColor(fleet.overall_health_score || 0))}
  </div>`;

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Nœuds de la flotte</h3></div>`;
  if (nodes.length) {
    html += nxTable(['Nœud', 'Apps', 'Domaines', 'Santé', 'État', 'Actions'], nodes.map(function(n) {
      const healthPct = (n.health_score || 0) + '%';
      const status = n.status || n.state || 'unknown';
      const statusBadge = nxBadge(status, status === 'enrolled' || status === 'active' ? 'success' : status === 'pending' ? 'warning' : 'neutral');
      const actions = `<div class="nx-actions">
        <button class="nx-btn nx-btn-sm nx-btn-outline" onclick="window.fleetAction('${n.node_id || n.hostname}','heartbeat')">Heartbeat</button>
      </div>`;
      return [n.node_id || n.hostname, n.apps_count || 0, n.domains_count || 0, healthPct, statusBadge, actions];
    }));
  } else {
    html += nxAlert('Nœud unique', 'info');
  }
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Topologie</h3></div>`;
  html += topo ? '<pre>' + JSON.stringify(topo, null, 2) + '</pre>' : nxEmpty('Topologie non disponible');
  html += '</div>';
  sec.innerHTML = html;
}

export async function loadBlueprints(sec) {
  const bps = await api('blueprints');
  if (!bps.length) { sec.innerHTML = nxEmpty('Aucun blueprint'); return; }
  sec.innerHTML = `<div class="nx-grid nx-grid-3">${bps.map(function(bp) {
    return '<div class="nx-card"><div class="nx-card-header"><h3 style="color:var(--accent)">' + bp.name + '</h3></div>' +
      '<p style="color:var(--muted);font-size:var(--text-sm);margin-bottom:var(--sp-sm)">' + bp.description + '</p>' +
      '<div style="font-size:var(--text-xs);color:var(--muted)">Apps: ' + (bp.recommended_apps || []).join(', ') +
      '<br/>Sous-domaines: ' + (bp.subdomains || []).join(', ') + '</div></div>';
  }).join('')}</div>`;
}

export async function loadAutomation(sec) {
  const [templates, checklists] = await Promise.all([api('automation/templates'), api('automation/checklists')]);
  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Templates d'automatisation</h3></div>`;
  html += (templates || []).length
    ? nxTable(['Job', 'Schedule', 'Risque'], (templates || []).map(function(t) { return [t.name, '<code>' + t.schedule + '</code>', t.risk]; }))
    : nxEmpty('Aucun template');
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Checklists</h3></div>
    <ul class="item-list">${(checklists || []).map(function(c) {
      return '<li><strong>' + c.name + '</strong><span class="nx-text-muted">' + (c.items || []).length + ' items</span></li>';
    }).join('')}</ul></div>`;
  sec.innerHTML = html;
}

export async function loadAdoption(sec, NexoraConsoleObj) {
  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Adoption / Enrollment</h3></div>
    <p class="nx-helper">Analyser la compatibilité d'un domaine YunoHost pour l'intégration Nexora.</p>
    <div class="nx-form-row">
      <label for="adopt-domain" class="nx-label">Domaine</label>
      <input id="adopt-domain" class="nx-input nx-input-grow" placeholder="example.tld"/>
    </div>
    <div class="nx-form-row">
      <label for="adopt-path" class="nx-label">Chemin</label>
      <input id="adopt-path" class="nx-input nx-input-grow" value="/nexora"/>
    </div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.runAdoption()">Analyser</button>
      <button class="nx-btn nx-btn-outline" onclick="window.runImport()">Importer état</button>
    </div>
    <div id="adoption-result" class="mt"></div>
  </div>`;
  sec.innerHTML = html;
}

export async function loadModes(sec, NexoraConsoleObj) {
  const [mode, escalations, confirmations, log] = await Promise.all([
    api('mode'), api('mode/escalations'), api('mode/confirmations'), api('admin/log').catch(function() { return []; })
  ]);

  const modeColor = { observer: 'var(--blue)', operator: 'var(--accent)', architect: 'var(--purple)', admin: 'var(--red)' };
  const color = modeColor[mode.mode] || 'var(--fg)';

  let html = `<div class="nx-grid nx-grid-2 mb">
    <div class="nx-card nx-card-center-padded">
      <div class="nx-text-3xl" style="font-weight:700;color:${color}">${mode.mode.toUpperCase()}</div>
      <div class="nx-text-muted nx-mb-sm">${mode.description || ''}</div>
      <div class="nx-text-xs nx-text-muted">Niveau ${mode.level} — ${(mode.capabilities || []).length} capacités</div>
      <div class="nx-capabilities-wrap">
        ${(mode.capabilities || []).map(function(c) { return nxBadge(c, 'success'); }).join('')}
      </div>
    </div>
    <div class="nx-card">
      <div class="nx-card-header"><h3>Changer de mode</h3></div>
      <div class="nx-form-row">
        <select id="mode-select" class="nx-input nx-select" aria-label="Mode cible">
          <option value="observer">Observer</option>
          <option value="operator">Operator</option>
          <option value="architect">Architect</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <div class="nx-form-row">
        <input id="mode-reason" class="nx-input nx-input-grow" placeholder="Raison (optionnel)" aria-label="Raison du changement"/>
      </div>
      <button class="nx-btn mt" onclick="window.switchMode()">Changer</button>
      <div id="mode-switch-result" class="mt"></div>
    </div>
  </div>`;

  setTimeout(function() {
    const sel = document.getElementById('mode-select');
    if (sel) sel.value = mode.mode;
  }, 0);

  const badge = document.getElementById('profile-badge');
  if (badge) badge.textContent = mode.mode;

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Escalations actives</h3></div>`;
  html += (escalations && escalations.length)
    ? nxTable(['Token', 'Mode cible', 'Reste', 'Raison'], escalations.map(function(e) {
        return [e.token_prefix, e.target_mode, Math.round(e.remaining_seconds / 60) + ' min', e.reason || '-'];
      }))
    : '<p style="color:var(--muted);font-size:var(--text-sm);padding:var(--sp-sm)">Aucune escalation active</p>';
  html += '</div>';

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Actions en attente</h3></div>`;
  html += (confirmations && confirmations.length)
    ? nxTable(['Token', 'Action', 'Expire dans'], confirmations.map(function(c) {
        return [c.token_prefix, c.action, Math.round(c.remaining_seconds / 60) + ' min'];
      }))
    : '<p style="color:var(--muted);font-size:var(--text-sm);padding:var(--sp-sm)">Aucune action en attente</p>';
  html += '</div>';

  const history = mode.history || [];
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Historique des modes</h3></div>`;
  html += history.length
    ? nxTable(['De', 'Vers', 'Direction', 'Raison', 'Date'], history.slice().reverse().map(function(h) {
        return [h.from, h.to, h.direction, h.reason || '-', new Date(h.timestamp).toLocaleString()];
      }))
    : '<p style="color:var(--muted);font-size:var(--text-sm);padding:var(--sp-sm)">Aucun changement</p>';
  html += '</div>';

  const logEntries = Array.isArray(log) ? log : [];
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Journal admin</h3></div>`;
  html += logEntries.length
    ? nxTable(['Action', 'Résultat', 'Date'], logEntries.slice().reverse().slice(0, 20).map(function(e) {
        return [e.action, e.success ? nxBadge('OK', 'success') : nxBadge('Échec', 'danger'), new Date(e.timestamp).toLocaleString()];
      }))
    : '<p style="color:var(--muted);font-size:var(--text-sm);padding:var(--sp-sm)">Aucune action admin</p>';
  html += '</div>';

  sec.innerHTML = html;
}
export async function loadDocker(sec) {
  const [status, containers, templates] = await Promise.all([
    api('docker/status'),
    api('docker/containers').catch(function() { return []; }),
    api('docker/templates').catch(function() { return []; })
  ]);

  const available = status.available !== false;
  let html = `<div class="nx-grid nx-grid-4 mb">
    ${nxStatCard(available ? status.version || 'N/A' : 'N/A', 'Version', available ? 'var(--accent)' : 'var(--muted)')}
    ${nxStatCard(status.containers_running || 0, 'Conteneurs actifs', 'var(--blue)')}
    ${nxStatCard(status.containers_total || 0, 'Conteneurs total', 'var(--purple)')}
    ${nxStatCard(status.images || 0, 'Images', 'var(--fg)')}
  </div>`;

  if (!available) {
    html += nxAlert('Docker non disponible sur ce nœud', 'warning');
  }

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Conteneurs</h3></div>`;
  html += (containers || []).length
    ? nxTable(['ID', 'Image', 'État', 'Ports'], (containers || []).map(function(c) {
        const state = c.state || c.status || 'unknown';
        return [c.id ? c.id.slice(0, 12) : '—', c.image || '—', nxBadge(state, state === 'running' ? 'success' : 'neutral'), (c.ports || []).join(', ') || '—'];
      }))
    : nxEmpty('Aucun conteneur actif');
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Templates disponibles</h3></div>`;
  html += (templates || []).length
    ? nxTable(['Nom', 'Image', 'Mémoire', 'Description'], (templates || []).map(function(t) {
        return [t.name, '<code>' + (t.image || '—') + '</code>', t.mem_limit || '—', t.description || '—'];
      }))
    : nxEmpty('Aucun template Docker');
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadStorage(sec) {
  const [usage, ynh] = await Promise.all([
    api('storage/usage').catch(function() { return { mounts: [] }; }),
    api('storage/ynh-map').catch(function() { return { storage_map: {} }; })
  ]);

  const mounts = usage.mounts || [];
  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Utilisation disque</h3></div>`;
  html += mounts.length
    ? nxTable(['Point de montage', 'Total', 'Utilisé', 'Libre', 'Usage %'], mounts.map(function(m) {
        const pct = m.percent || 0;
        const color = pct > 90 ? 'var(--red)' : pct > 75 ? 'var(--warning)' : 'var(--success)';
        return [m.mountpoint || m.device, m.total_human || '—', m.used_human || '—', m.free_human || '—',
          '<span style="color:' + color + ';font-weight:600">' + pct + '%</span>'];
      }))
    : nxEmpty('Aucune donnée de disque disponible');
  html += '</div>';

  const storageMap = ynh.storage_map || {};
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Carte stockage YunoHost</h3></div>`;
  const mapEntries = Object.entries(storageMap);
  html += mapEntries.length
    ? nxTable(['Répertoire', 'Taille'], mapEntries.map(function(e) { return [e[0], e[1] === 'N/A' ? nxBadge('N/A', 'neutral') : e[1]]; }))
    : nxEmpty('Carte stockage non disponible');
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadNotifications(sec) {
  const templates = await api('notifications/templates').catch(function() { return []; });
  const levelColor = { critical: 'danger', warning: 'warning', info: 'info', success: 'success' };

  let html = `<div class="nx-card"><div class="nx-card-header"><h3>Templates de notification</h3></div>`;
  html += (templates || []).length
    ? `<div class="nx-grid nx-grid-2">${(templates || []).map(function(t) {
        const lvl = t.level || 'info';
        return `<div class="nx-card">
          <div style="display:flex;align-items:center;gap:var(--sp-sm);margin-bottom:var(--sp-sm)">
            ${nxBadge(lvl, levelColor[lvl] || 'neutral')}
            <strong>${t.id || '—'}</strong>
          </div>
          <p style="font-weight:600;margin:0 0 var(--sp-xs)">${t.title || '—'}</p>
          <p style="font-size:var(--text-sm);color:var(--muted);margin:0">${t.body || '—'}</p>
        </div>`;
      }).join('')}</div>`
    : nxEmpty('Aucun template de notification');
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadHooks(sec) {
  const [events, presets] = await Promise.all([
    api('hooks/events').catch(function() { return []; }),
    api('hooks/presets').catch(function() { return []; })
  ]);

  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Événements disponibles</h3></div>`;
  html += (events || []).length
    ? nxTable(['Événement', 'Description'], (events || []).map(function(e) {
        return ['<code>' + (e.event || e.name || '—') + '</code>', e.description || '—'];
      }))
    : nxEmpty('Aucun événement disponible');
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Presets</h3></div>`;
  html += (presets || []).length
    ? nxTable(['Nom', 'Hooks', 'Événements couverts'], (presets || []).map(function(p) {
        return [p.name, p.hooks_count || 0, (p.events || []).map(function(ev) { return nxBadge(ev, 'info'); }).join(' ')];
      }))
    : nxEmpty('Aucun preset défini');
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadGovernanceRisks(sec) {
  const risks = await api('governance/risks').catch(function() { return { risks: [] }; });
  const items = risks.risks || risks.items || [];
  const riskColor = { critical: 'danger', high: 'danger', medium: 'warning', low: 'success', info: 'info' };

  let html = '';
  const score = risks.risk_score !== undefined ? risks.risk_score : risks.score;
  if (score !== undefined) {
    const scoreColor = score >= 80 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--red)';
    html += `<div class="nx-grid nx-grid-4 mb">${nxStatCard(score, 'Score de risque', scoreColor)}</div>`;
  }

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Registre des risques</h3>`;
  if (risks.tenant_id) html += `<span style="font-size:var(--text-sm);color:var(--muted)">Tenant: ${risks.tenant_id}</span>`;
  html += '</div>';

  html += items.length
    ? nxTable(
        ['Risque', 'Sévérité', 'Composant', 'Recommandation'],
        items.map(function(r) {
          const sev = (r.severity || r.level || 'info').toLowerCase();
          return [
            r.risk || r.title || r.name || '—',
            nxBadge(sev, riskColor[sev] || 'neutral'),
            r.component || r.domain || '—',
            '<span style="font-size:var(--text-sm);color:var(--muted)">' + (r.recommendation || r.description || '—') + '</span>'
          ];
        })
      )
    : nxEmpty('Aucun risque détecté');
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadSlaTracking(sec) {
  const tiers = await api('sla/tiers').catch(function() { return []; });
  const tierList = Array.isArray(tiers) ? tiers : (tiers.tiers || []);

  let html = `<div class="nx-card"><div class="nx-card-header"><h3>Paliers SLA</h3></div>`;

  if (tierList.length) {
    html += `<div class="nx-grid nx-grid-2 p-md">` + tierList.map(function(t) {
      const raw = typeof t.uptime_target === 'number' ? t.uptime_target : parseFloat(t.uptime_sla || '0');
      const uptimePct = (raw >= 1 ? raw : raw * 100).toFixed(2);
      const uptimeColor = parseFloat(uptimePct) >= 99.9 ? 'var(--success)' : parseFloat(uptimePct) >= 99 ? 'var(--blue)' : 'var(--warning)';
      return `<div class="nx-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--sp-sm)">
          <strong style="font-size:var(--text-base)">${t.name || t.tier || '—'}</strong>
          <span style="color:${uptimeColor};font-weight:700">${uptimePct}% uptime</span>
        </div>
        ${t.description ? `<p style="font-size:var(--text-sm);color:var(--muted);margin:0 0 var(--sp-xs)">${t.description}</p>` : ''}
        ${t.rto ? `<p style="font-size:var(--text-sm);margin:0"><b>RTO:</b> ${t.rto} &nbsp;|&nbsp; <b>RPO:</b> ${t.rpo || '—'}</p>` : ''}
        ${t.support_hours ? `<p style="font-size:var(--text-sm);color:var(--muted);margin:var(--sp-xs) 0 0">Support: ${t.support_hours}</p>` : ''}
      </div>`;
    }).join('') + '</div>';
  } else {
    html += nxEmpty('Aucun palier SLA défini');
  }
  html += '</div>';

  sec.innerHTML = html;
}