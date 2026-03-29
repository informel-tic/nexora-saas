import { api, apiPost } from './api.js';
import { scoreColor, nxStatCard, nxGauge, nxAlert, nxTable, nxLoader, nxEmpty, nxBadge } from './components.js';

function stripAnsi(value) {
  return String(value || '').replace(/\u001b\[[0-9;]*m/g, '').trim();
}

function inventoryEntries(payload) {
  return Object.entries(payload || {}).filter(function(entry) {
    return entry[0] && entry[0].charAt(0) !== '_';
  });
}

function inventoryError(payload, fallback) {
  const raw = stripAnsi(payload && payload._error);
  if (!raw) return '';
  if (raw.toLowerCase().indexOf('must be run as root') >= 0) {
    return fallback;
  }
  return raw;
}

export async function loadDashboard(sec) {
  const [dash, health, identity] = await Promise.all([api('dashboard'), api('health'), api('identity').catch(function() { return {}; })]);
  document.getElementById('health-badge').textContent = health.status === 'ok' ? 'online' : 'offline';
  const node = dash.node || {};

  let html = `<div class="nx-grid nx-grid-4 mb">
    ${nxStatCard(node.apps_count || 0, 'Applications')}
    ${nxStatCard(node.domains_count || 0, 'Domaines')}
    ${nxStatCard(node.backups_count || 0, 'Sauvegardes')}
    ${nxStatCard((node.health_score || 0) + '%', 'Santé', scoreColor(node.health_score || 0))}
  </div>`;

  /* Host node identity card */
  const hostId = identity.node_id || node.node_id || '—';
  const hostRole = identity.role || 'host';
  const ynhVer = identity.yunohost_version || node.yunohost_version || '—';
  const debVer = identity.debian_version || node.debian_version || '—';
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Nœud hôte SaaS</h3></div>
    <div class="nx-grid nx-grid-4 p-md">
      ${nxStatCard(hostId, 'Node ID', 'var(--accent)')}
      ${nxStatCard(hostRole, 'Rôle', 'var(--purple)')}
      ${nxStatCard(ynhVer, 'YunoHost', 'var(--blue)')}
      ${nxStatCard(debVer, 'Debian', 'var(--fg)')}
    </div>
  </div>`;

  /* Session / token context card */
  const token = sessionStorage.getItem('nexora_token') || '';
  const tenantId = sessionStorage.getItem('nexora_tenant_id') || 'aucun';
  const actorRole = sessionStorage.getItem('nexora_actor_role') || 'admin';
  const tokenPreview = token ? (token.slice(0, 8) + '\u2026' + token.slice(-4)) : 'non d\u00e9fini';
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Session console</h3></div>
    <div class="nx-grid nx-grid-3 p-md">
      ${nxStatCard(tokenPreview, 'Token', 'var(--accent)')}
      ${nxStatCard(actorRole, 'R\u00f4le', 'var(--purple)')}
      ${nxStatCard(tenantId, 'Tenant', 'var(--blue)')}
    </div>
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
  const data = await api('inventory/services').catch(function(e) {
    // Try new fallback endpoint
    return api('services').catch(function() { return {_error: e.message}; });
  });
  const svcs = inventoryEntries(data);
  const error = inventoryError(data, '');
  if (!svcs.length && !error) { sec.innerHTML = nxEmpty('Aucun service'); return; }
  let html = `<div class="nx-card"><div class="nx-card-header"><h3>État des services</h3>
    <div style="font-size:var(--text-sm);color:var(--muted)">Gérez les services YunoHost / systemd</div>
  </div>`;
  if (error) html += nxAlert(error, 'warning');
  html += `<div id="services-action-result" class="mb"></div>
  <ul class="item-list">${svcs.map(function([name, info]) {
    const st = (typeof info === 'object' ? info.status || info.active : info) || '?';
    const dot = st === 'running' || st === 'active' ? 'status-running' : st === 'inactive' || st === 'dead' ? 'status-stopped' : 'status-warning';
    const statusBadge = st === 'running' || st === 'active' ? nxBadge('running', 'success') : nxBadge(st, 'neutral');
    return `<li style="flex-wrap:wrap;gap:var(--sp-xs)">
      <span><span class="status-dot ${dot}"></span><strong>${name}</strong></span>
      <span style="display:flex;gap:var(--sp-xs);align-items:center">
        ${statusBadge}
        <button class="nx-btn nx-btn-xs" onclick="window.serviceAction('${name}','restart')" title="Redémarrer">↻ Restart</button>
        <button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.serviceAction('${name}','stop')" title="Stopper">■ Stop</button>
        <button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.serviceAction('${name}','start')" title="Démarrer">▶ Start</button>
        <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="window.serviceViewLogs('${name}')" title="Logs">📋 Logs</button>
      </span>
    </li>`;
  }).join('')}</ul></div>
  <div id="service-logs-panel" class="nx-card mt" style="display:none">
    <div class="nx-card-header">
      <h3 id="service-logs-title">Logs</h3>
      <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="document.getElementById('service-logs-panel').style.display='none'">✕</button>
    </div>
    <pre id="service-logs-content" style="max-height:400px;overflow:auto;font-size:var(--text-xs);color:var(--fg);padding:var(--sp-md)"></pre>
  </div>`;
  sec.innerHTML = html;
}

export async function loadDomains(sec) {
  const [domains, certs] = await Promise.all([api('inventory/domains'), api('inventory/certs')]);
  const domainError = inventoryError(domains, 'Inventaire des domaines indisponible sur cet hôte sans privilèges YunoHost.');
  const certError = inventoryError(certs, 'Inventaire des certificats indisponible sur cet hôte sans privilèges YunoHost.');
  const domList = Array.isArray(domains.domains) ? domains.domains : [];
  const certMap = (certs || {}).certificates || certs || {};
  const certEntries = inventoryEntries(certMap);

  let html = `<div class="nx-grid nx-grid-2">
    <div class="nx-card"><div class="nx-card-header"><h3>Domaines</h3></div>`;
  if (domainError) {
    html += nxAlert(domainError, 'warning');
  }
  html += domList.length
    ? '<ul class="item-list">' + domList.map(function(d) { return '<li>' + d + '</li>'; }).join('') + '</ul>'
    : nxEmpty('Aucun domaine');
  html += `</div><div class="nx-card"><div class="nx-card-header"><h3>Certificats</h3></div>`;
  if (certError) {
    html += nxAlert(certError, 'warning');
  }
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
  const [posture, risks, updates, f2b, ports, perms, logins] = await Promise.all([
    api('security/posture'),
    api('governance/risks'),
    api('security/updates').catch(function() { return {}; }),
    api('security/fail2ban/status').catch(function() { return {}; }),
    api('security/open-ports').catch(function() { return { ports: [] }; }),
    api('security/permissions-audit').catch(function() { return {}; }),
    api('security/recent-logins').catch(function() { return { logins: [] }; })
  ]);

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

  /* Security sub-panels */
  html += `<div class="nx-grid nx-grid-2 mt">`;

  /* Updates */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Mises à jour système</h3></div>`;
  if (updates.updates_available) {
    html += nxAlert(updates.packages.length + ' mise(s) à jour disponible(s)', 'warning');
    html += nxTable(['Paquet', 'Version', 'Disponible'], (updates.packages || []).map(function(p) {
      return [p.name, p.current || '-', p.available || '-'];
    }));
  } else {
    html += nxAlert('Système à jour', 'success');
  }
  html += '</div>';

  /* Fail2ban */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Fail2ban</h3></div>`;
  html += '<div class="p-md">' + nxStatCard(f2b.active ? 'Actif' : 'Inactif', 'État', f2b.active ? 'var(--green)' : 'var(--red)');
  html += nxStatCard((f2b.banned_ips || []).length, 'IPs bannies', 'var(--orange)') + '</div>';
  if ((f2b.banned_ips || []).length) {
    html += '<ul class="item-list">' + f2b.banned_ips.map(function(ip) { return '<li><code>' + ip + '</code></li>'; }).join('') + '</ul>';
  }
  html += '</div>';

  /* Open ports */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Ports ouverts</h3></div>`;
  const portList = ports.ports || [];
  html += portList.length
    ? '<div class="p-md">' + portList.map(function(p) { return nxBadge(p, 'info'); }).join(' ') + '</div>'
    : nxEmpty('Aucun port détecté');
  html += '</div>';

  /* Permissions audit */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Audit des permissions</h3></div>`;
  const auditStatus = perms.audit || 'ok';
  html += nxAlert('Statut: ' + auditStatus, auditStatus === 'ok' ? 'success' : 'warning');
  if ((perms.public_apps || []).length) {
    html += '<ul class="item-list">' + perms.public_apps.map(function(a) { return '<li>Public: <strong>' + a + '</strong></li>'; }).join('') + '</ul>';
  }
  html += '</div>';

  html += '</div>';

  /* Recent logins */
  html += `<div class="nx-card mt"><div class="nx-card-header"><h3>Connexions récentes (${(logins.logins || []).length})</h3></div>`;
  const loginList = logins.logins || [];
  html += loginList.length
    ? nxTable(['Date', 'Action', 'Sévérité'], loginList.slice(-20).reverse().map(function(l) {
        const sevBadge = l.severity === 'critical' ? nxBadge(l.severity, 'danger') :
                         l.severity === 'warning' ? nxBadge(l.severity, 'warning') :
                         nxBadge(l.severity, 'info');
        return [(l.timestamp || '').slice(0, 19).replace('T', ' '), l.action || '-', sevBadge];
      }))
    : nxAlert('Aucune connexion enregistrée', 'info');
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
  html += `<div class="p-md"><button class="nx-btn" onclick="window.enrollNode()">Enrôler un nœud</button></div>`;
  html += '</div>';

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Topologie</h3></div>`;
  html += topo ? '<pre>' + JSON.stringify(topo, null, 2) + '</pre>' : nxEmpty('Topologie non disponible');
  html += '</div>';
  sec.innerHTML = html;
}

export async function loadBlueprints(sec) {
  const bps = await api('blueprints').catch(function() { return []; });
  if (!bps.length) { sec.innerHTML = nxEmpty('Aucun blueprint'); return; }
  let html = `<div id="blueprint-action-result" class="mb"></div>
  <div class="nx-grid nx-grid-3">${bps.map(function(bp) {
    const apps = (bp.recommended_apps || bp.apps || []);
    const appsPreview = Array.isArray(apps) ? apps.slice(0,4).map(function(a){ return typeof a === 'object' ? a.id || a.name || a : a; }).join(', ') : '';
    return `<div class="nx-card">
      <div class="nx-card-header"><h3 style="color:var(--accent)">${bp.name}</h3></div>
      <p style="color:var(--muted);font-size:var(--text-sm);margin-bottom:var(--sp-sm)">${bp.description || ''}</p>
      <div style="font-size:var(--text-xs);color:var(--muted);margin-bottom:var(--sp-sm)">
        ${appsPreview ? 'Apps: ' + appsPreview : ''}
        ${(bp.subdomains || []).length ? '<br/>Sous-domaines: ' + bp.subdomains.join(', ') : ''}
      </div>
      <div class="nx-actions">
        <button class="nx-btn" onclick="window.deployBlueprint('${bp.slug}')">🚀 Déployer</button>
        <button class="nx-btn nx-btn-outline" onclick="window.blueprintParams('${bp.slug}')">⚙ Paramètres</button>
      </div>
    </div>`;
  }).join('')}</div>
  <!-- Blueprint deploy modal -->
  <div id="blueprint-deploy-modal" style="display:none" class="nx-card mt">
    <div class="nx-card-header">
      <h3 id="blueprint-modal-title">Déployer un blueprint</h3>
      <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="document.getElementById('blueprint-deploy-modal').style.display='none'">✕</button>
    </div>
    <div class="nx-form-row"><label class="nx-label">Domaine cible</label>
      <input id="bp-domain" class="nx-input nx-input-grow" placeholder="example.com"/></div>
    <div class="nx-form-row"><label class="nx-label">Email admin</label>
      <input id="bp-admin-email" class="nx-input nx-input-grow" placeholder="admin@example.com"/></div>
    <div id="bp-extra-params"></div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.deployBlueprintConfirm()">Lancer le déploiement</button>
      <button class="nx-btn nx-btn-outline" onclick="window.deployBlueprintDry()">Dry run</button>
    </div>
    <div id="bp-deploy-result" class="mt"></div>
  </div>`;
  sec.innerHTML = html;
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

  const runtimeBadge = document.getElementById('runtime-mode-badge');
  if (runtimeBadge) runtimeBadge.textContent = 'mode: ' + (mode.mode || 'observer');

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

  if (!available) html += nxAlert('Docker non disponible sur ce nœud — installez Docker pour activer cette fonctionnalité.', 'warning');

  /* ── Docker Hub search ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>🔍 Docker Hub</h3></div>
    <div class="nx-form-row" style="align-items:center">
      <input id="docker-hub-query" class="nx-input nx-input-grow" placeholder="Rechercher: nginx, postgres, wordpress…" onkeydown="if(event.key==='Enter')window.dockerHubSearch()"/>
      <button class="nx-btn" onclick="window.dockerHubSearch()">Rechercher</button>
    </div>
    <div id="docker-hub-results" class="mt"></div>
  </div>`;

  /* ── Deploy custom container ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>🚀 Déployer un conteneur</h3></div>
    <div class="nx-form-row"><label class="nx-label">Image</label>
      <input id="docker-deploy-image" class="nx-input nx-input-grow" placeholder="nginx:alpine"/></div>
    <div class="nx-form-row"><label class="nx-label">Nom</label>
      <input id="docker-deploy-name" class="nx-input nx-input-grow" placeholder="mon-nginx"/></div>
    <div class="nx-form-row"><label class="nx-label">Ports</label>
      <input id="docker-deploy-ports" class="nx-input nx-input-grow" placeholder="8080:80, 443:443"/></div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.dockerDeploy()">Lancer</button>
    </div>
    <div id="docker-deploy-result" class="mt"></div>
  </div>`;

  /* ── Running containers ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>📦 Conteneurs</h3>
    <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="NexoraConsole.navigate('docker')">↻ Rafraîchir</button>
  </div>
  <div id="docker-containers-action-result" class="mb"></div>`;
  if ((containers || []).length) {
    html += `<div style="overflow-x:auto"><table class="nx-table"><thead><tr><th>Nom</th><th>Image</th><th>État</th><th>Ports</th><th>Actions</th></tr></thead><tbody>`;
    (containers || []).forEach(function(c) {
      const name = c.name || c.Names || c.id || '—';
      const displayName = name.replace(/^\//, '');
      const image = c.image || c.Image || '—';
      const state = c.state || c.status || c.Status || 'unknown';
      const isRunning = state === 'running';
      const stateBadge = isRunning ? nxBadge('running', 'success') : nxBadge(state, 'neutral');
      const ports = (c.ports || c.Ports || []).join ? (c.ports || c.Ports || []).join(', ') : '';
      html += `<tr>
        <td><strong>${displayName}</strong></td>
        <td><code style="font-size:var(--text-xs)">${image}</code></td>
        <td>${stateBadge}</td>
        <td><code style="font-size:var(--text-xs)">${ports || '—'}</code></td>
        <td style="white-space:nowrap">
          ${isRunning ? `<button class="nx-btn nx-btn-xs" onclick="window.dockerContainerAction('${displayName}','restart')" title="Restart">↻</button>
          <button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.dockerContainerAction('${displayName}','stop')" title="Stop">■</button>` :
          `<button class="nx-btn nx-btn-xs" onclick="window.dockerContainerAction('${displayName}','start')" title="Start">▶</button>`}
          <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="window.dockerContainerLogs('${displayName}')" title="Logs">📋</button>
          <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="window.dockerContainerAction('${displayName}','remove')" title="Supprimer" style="color:var(--red)">🗑</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  } else {
    html += nxEmpty('Aucun conteneur actif — déployez depuis Docker Hub ou un template');
  }
  html += '</div>';

  /* ── Container logs panel ── */
  html += `<div id="docker-logs-panel" class="nx-card mb" style="display:none">
    <div class="nx-card-header">
      <h3 id="docker-logs-title">Logs conteneur</h3>
      <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="document.getElementById('docker-logs-panel').style.display='none'">✕</button>
    </div>
    <pre id="docker-logs-content" style="max-height:400px;overflow:auto;font-size:var(--text-xs);white-space:pre-wrap;padding:var(--sp-md)"></pre>
  </div>`;

  /* ── Docker Compose ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>🐙 Docker Compose</h3></div>
    <div class="nx-form-row"><label class="nx-label">Contenu YAML</label>
      <textarea id="docker-compose-content" class="nx-input" rows="10" style="font-family:monospace;font-size:var(--text-xs)" placeholder="version: '3'&#10;services:&#10;  web:&#10;    image: nginx:alpine&#10;    ports:&#10;      - '8080:80'"></textarea>
    </div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.dockerComposeApply()">▶ docker compose up</button>
      <button class="nx-btn nx-btn-outline" onclick="window.dockerComposeDown()">■ docker compose down</button>
    </div>
    <div id="docker-compose-result" class="mt"></div>
  </div>`;

  /* ── Templates ── */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>📋 Templates pré-configurés</h3></div>`;
  html += (templates || []).length
    ? `<div class="nx-grid nx-grid-3">${(templates || []).map(function(t) {
        return `<div class="nx-card">
          <strong>${t.name}</strong>
          <p style="font-size:var(--text-xs);color:var(--muted)"><code>${t.image || '—'}</code></p>
          <p style="font-size:var(--text-xs);color:var(--muted)">${t.description || ''}</p>
          <p style="font-size:var(--text-xs)">${nxBadge(t.mem_limit || 'N/A', 'info')}</p>
          <button class="nx-btn nx-btn-xs mt" onclick="window.dockerTemplateDeploy('${t.name}')">🚀 Déployer</button>
        </div>`;
      }).join('')}</div>`
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
        const mountLabel = m.mountpoint || m.device || m.path || '—';
        return [mountLabel, m.total_human || '—', m.used_human || '—', m.free_human || '—',
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


/* ── Subscription Management ── */
export async function loadSubscription(sec) {
  const [plans, orgs, subs] = await Promise.all([
    api('plans').catch(function() { return []; }),
    api('organizations').catch(function() { return []; }),
    api('subscriptions').catch(function() { return []; })
  ]);

  const planList = Array.isArray(plans) ? plans : [];
  const orgList = Array.isArray(orgs) ? orgs : [];
  const subList = Array.isArray(subs) ? subs : [];

  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Plans disponibles</h3></div>
    <div class="nx-grid nx-grid-3 p-md">`;

  planList.forEach(function(p) {
    const price = p.price_monthly_eur === 0 ? 'Gratuit' : p.price_monthly_eur + '\u20ac/mois';
    html += `<div class="nx-card" style="text-align:center">
      <strong>${p.name || p.tier}</strong>
      <div style="font-size:1.5rem;font-weight:700;color:var(--primary);margin:.5rem 0">${price}</div>
      <div style="font-size:.85rem;color:var(--muted)">
        ${p.max_nodes} n\u0153uds \u00b7 ${p.max_apps_per_node} apps/n\u0153ud \u00b7 ${p.max_storage_gb}GB
      </div>
      <ul style="text-align:left;font-size:.8rem;margin:.5rem 0;padding-left:1rem">
        ${(p.features || []).map(function(f) { return '<li>' + f + '</li>'; }).join('')}
      </ul>
    </div>`;
  });
  html += '</div></div>';

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Organisations (${orgList.length})</h3></div>`;
  if (orgList.length) {
    html += nxTable(['ID', 'Nom', 'Email', 'Cr\u00e9\u00e9 le'], orgList.map(function(o) {
      return [o.org_id || '-', o.name || '-', o.contact_email || '-', (o.created_at || '').slice(0, 10)];
    }));
  } else {
    html += nxEmpty('Aucune organisation');
  }
  html += `<div class="p-md"><button class="nx-btn" onclick="window.createOrg()">Cr\u00e9er une organisation</button></div></div>`;

  html += `<div class="nx-card"><div class="nx-card-header"><h3>Souscriptions (${subList.length})</h3></div>`;
  if (subList.length) {
    html += nxTable(['ID', 'Org', 'Tier', 'Tenant', 'Status', 'Cr\u00e9\u00e9 le', 'Actions'], subList.map(function(s) {
      const statusBadge = s.status === 'active' ? nxBadge(s.status, 'success') :
                          s.status === 'suspended' ? nxBadge(s.status, 'warning') :
                          nxBadge(s.status, 'danger');
      let actions = '';
      if (s.status === 'active') {
        actions = `<button class="nx-btn nx-btn-sm" onclick="window.suspendSubscription('${s.subscription_id}')">Suspendre</button>
          <button class="nx-btn nx-btn-sm nx-btn-danger" onclick="window.cancelSubscription('${s.subscription_id}')">R\u00e9silier</button>`;
      } else if (s.status === 'suspended') {
        actions = `<button class="nx-btn nx-btn-sm" onclick="window.reactivateSubscription('${s.subscription_id}')">R\u00e9activer</button>`;
      }
      return [s.subscription_id || '-', s.org_id || '-', s.tier || '-', s.tenant_id || '-', statusBadge, (s.created_at || '').slice(0, 10), actions];
    }));
  } else {
    html += nxEmpty('Aucune souscription');
  }
  html += `<div class="p-md"><button class="nx-btn" onclick="window.createSubscription()">Cr\u00e9er une souscription</button></div></div>`;

  sec.innerHTML = html;
}


/* ── Feature Provisioning ── */
export async function loadProvisioning(sec) {
  const fleet = await api('fleet').catch(function() { return { nodes: [] }; });
  const nodes = fleet.nodes || [];

  let html = `<div class="nx-card mb"><div class="nx-card-header"><h3>Provisioning des fonctionnalit\u00e9s</h3>
    <button class="nx-btn nx-btn-sm" onclick="NexoraConsole.navigate('provisioning')" style="margin-left:auto">\u21bb Rafra\u00eechir</button></div>
    <p class="p-md" style="color:var(--muted)">
      Le SaaS pousse les fonctionnalit\u00e9s vers les n\u0153uds enroll\u00e9s. Les n\u0153uds sont des interfaces passives.
    </p>`;

  if (nodes.length) {
    html += `<div class="nx-grid nx-grid-2 p-md">`;
    for (const node of nodes) {
      const nodeId = node.node_id || node.hostname || '-';
      const status = node.status || 'unknown';
      const tenant = node.tenant_id || 'aucun';
      const dot = status === 'healthy' || status === 'registered' ? 'status-running' :
                  status === 'degraded' ? 'status-warning' : 'status-stopped';

      let provStatus = null;
      let features = null;
      try {
        provStatus = await api('provisioning/nodes/' + encodeURIComponent(nodeId) + '/status');
        features = await api('provisioning/nodes/' + encodeURIComponent(nodeId) + '/features');
      } catch(e) { /* silent */ }

      html += `<div class="nx-card">
        <div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem">
          <span class="status-dot ${dot}"></span>
          <strong>${nodeId}</strong>
          <span style="color:var(--muted);font-size:.8rem">(${status})</span>
        </div>
        <div style="font-size:.85rem;color:var(--muted)">Tenant: ${tenant}</div>`;

      if (features && features.features) {
        html += `<div style="margin-top:.5rem"><strong style="font-size:.85rem">Fonctionnalit\u00e9s:</strong>
          <ul style="font-size:.8rem;padding-left:1rem;margin:.25rem 0">
            ${features.features.map(function(f) { return '<li>' + f.name + ' <span style="color:var(--muted)">(' + f.kind + ')</span></li>'; }).join('')}
          </ul></div>`;
      }

      if (provStatus && provStatus.last_event) {
        const evt = provStatus.last_event;
        html += `<div style="font-size:.8rem;color:var(--muted);margin-top:.25rem">
          Dernier provisioning: ${(evt.provisioned_at || evt.deprovisioned_at || '').slice(0, 16)} \u2014 ${evt.status}
        </div>`;
      }

      html += `<div style="margin-top:.5rem;display:flex;gap:.5rem">
        <button class="nx-btn nx-btn-sm" onclick="window.provisionNode('${nodeId}')">Provisionner</button>
        <button class="nx-btn nx-btn-sm nx-btn-danger" onclick="window.deprovisionNode('${nodeId}')">D\u00e9provisionner</button>
      </div></div>`;
    }
    html += '</div>';
  } else {
    html += nxEmpty('Aucun n\u0153ud dans la flotte. Enrollez d\'abord un n\u0153ud via Fleet.');
  }
  html += '</div>';

  sec.innerHTML = html;
}

export async function loadSettings(sec) {
  const [settings, accessContext] = await Promise.all([
    api('settings').catch(function() { return {}; }),
    api('console/access-context').catch(function() { return {}; })
  ]);

  const profile = settings.profile || {};
  const tenant = settings.tenant || accessContext.tenant || {};
  const operator = settings.operator || {};
  const state = settings.state || {};
  const security = settings.security || {};
  const allowed = accessContext.allowed_sections || [];

  let html = `<div class="nx-grid nx-grid-3 mb">
    ${nxStatCard(profile.actor_role || 'observer', 'Rôle d\'accès', 'var(--accent)')}
    ${nxStatCard(profile.runtime_mode || 'observer', 'Mode runtime', 'var(--blue)')}
    ${nxStatCard(accessContext.tenant_id || 'aucun', 'Tenant effectif', 'var(--purple)')}
  </div>`;

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Contexte opérateur</h3></div>`;
  html += nxTable(
    ['Clé', 'Valeur'],
    [
      ['is_operator', String(!!profile.is_operator)],
      ['operator_tenant_id', operator.tenant_id || accessContext.operator_tenant_id || '-'],
      ['operator_org_id', operator.organization_id || '-'],
      ['tenant_source', accessContext.tenant_source || '-'],
      ['platform_version', accessContext.platform_version || settings.version || '-']
    ]
  );
  html += '</div>';

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Tenant courant</h3></div>`;
  html += nxTable(
    ['Champ', 'Valeur'],
    [
      ['tenant_id', tenant.tenant_id || accessContext.tenant_id || '-'],
      ['org_id', tenant.org_id || '-'],
      ['tier', tenant.tier || '-'],
      ['status', tenant.status || '-'],
      ['label', tenant.label || '-']
    ]
  );
  html += '</div>';

  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Surfaces autorisées</h3></div>`;
  html += allowed.length
    ? '<div class="p-md">' + allowed.map(function(section) { return nxBadge(section, 'info'); }).join(' ') + '</div>'
    : nxEmpty('Aucune section autorisée détectée');
  html += '</div>';

  html += `<div class="nx-grid nx-grid-2">
    <div class="nx-card"><div class="nx-card-header"><h3>État plateforme</h3></div>
      ${nxTable(
        ['Indicateur', 'Valeur'],
        [
          ['tenants_count', String(state.tenants_count || 0)],
          ['organizations_count', String(state.organizations_count || 0)],
          ['subscriptions_count', String(state.subscriptions_count || 0)],
          ['nodes_count', String(state.nodes_count || 0)]
        ]
      )}
    </div>
    <div class="nx-card"><div class="nx-card-header"><h3>Guardrails sécurité</h3></div>
      ${nxTable(
        ['Contrôle', 'État'],
        [
          ['operator_only_enforce', security.operator_only_enforce ? nxBadge('enabled', 'success') : nxBadge('disabled', 'warning')],
          ['token_scope_file_configured', security.token_scope_file_configured ? nxBadge('yes', 'success') : nxBadge('no', 'warning')],
          ['token_role_file_configured', security.token_role_file_configured ? nxBadge('yes', 'success') : nxBadge('no', 'warning')],
          ['deployment_scope', security.deployment_scope || 'non défini']
        ]
      )}
    </div>
  </div>`;

  sec.innerHTML = html;
}

// ── YunoHost App Catalog ──────────────────────────────────────────────────

export async function loadYnhCatalog(sec) {
  sec.innerHTML = `<div class="nx-card mb"><div class="nx-card-header"><h3>📦 Catalogue d'applications YunoHost</h3></div>
    <div class="nx-form-row" style="align-items:center">
      <input id="catalog-query" class="nx-input nx-input-grow" placeholder="Rechercher: wordpress, nextcloud, gitea…" onkeydown="if(event.key==='Enter')window.catalogSearch()"/>
      <button class="nx-btn" onclick="window.catalogSearch()">Rechercher</button>
    </div>
    <div id="catalog-action-result" class="mt"></div>
    <div id="catalog-results" class="mt"></div>
  </div>
  <!-- Install modal -->
  <div id="catalog-install-modal" style="display:none" class="nx-card mt">
    <div class="nx-card-header">
      <h3 id="catalog-install-title">Installer une application</h3>
      <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="document.getElementById('catalog-install-modal').style.display='none'">✕</button>
    </div>
    <div class="nx-form-row"><label class="nx-label">App ID</label>
      <input id="catalog-install-appid" class="nx-input nx-input-grow" readonly/></div>
    <div class="nx-form-row"><label class="nx-label">Domaine</label>
      <input id="catalog-install-domain" class="nx-input nx-input-grow" placeholder="mondomaine.tld"/></div>
    <div class="nx-form-row"><label class="nx-label">Chemin</label>
      <input id="catalog-install-path" class="nx-input" value="/"/></div>
    <div class="nx-form-row"><label class="nx-label">Label (optionnel)</label>
      <input id="catalog-install-label" class="nx-input nx-input-grow" placeholder="Mon app"/></div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.catalogInstallConfirm()">Installer</button>
    </div>
    <div id="catalog-install-result" class="mt"></div>
  </div>
  <!-- Installed apps management -->
  <div class="nx-card mt"><div class="nx-card-header"><h3>Applications installées</h3>
    <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="window.ynhAppsRefresh()">↻ Rafraîchir</button>
  </div>
  <div id="ynh-apps-list" class="mt">${nxLoader('Chargement…')}</div>
  </div>`;
  // Load installed apps right away
  window.ynhAppsRefresh();
}

// ── Failover ──────────────────────────────────────────────────────────────

export async function loadFailover(sec) {
  const [strategies, status] = await Promise.all([
    api('failover/strategies').catch(function() { return []; }),
    api('failover/status').catch(function() { return {pairs:[], total_protected_apps:0}; })
  ]);

  const pairs = status.pairs || [];
  let html = `<div class="nx-grid nx-grid-3 mb">
    ${nxStatCard(pairs.length, 'Paires configurées', 'var(--blue)')}
    ${nxStatCard(status.active_failovers || 0, 'Failovers actifs', status.active_failovers > 0 ? 'var(--orange)' : 'var(--green)')}
    ${nxStatCard(status.total_protected_apps || 0, 'Apps protégées', 'var(--accent)')}
  </div>`;

  html += `<div id="failover-action-result" class="mb"></div>`;

  /* ── Configure failover pair ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>⚙ Configurer une paire de failover</h3></div>
    <div class="nx-form-row"><label class="nx-label">App ID</label>
      <input id="fo-app-id" class="nx-input nx-input-grow" placeholder="nextcloud"/></div>
    <div class="nx-form-row"><label class="nx-label">Domaine</label>
      <input id="fo-domain" class="nx-input nx-input-grow" placeholder="nextcloud.example.com"/></div>
    <div class="nx-form-row"><label class="nx-label">Hôte principal</label>
      <input id="fo-primary-host" class="nx-input nx-input-grow" placeholder="192.168.1.10"/></div>
    <div class="nx-form-row"><label class="nx-label">Hôte secondaire</label>
      <input id="fo-secondary-host" class="nx-input nx-input-grow" placeholder="192.168.1.20"/></div>
    <div class="nx-form-row"><label class="nx-label">Stratégie</label>
      <select id="fo-strategy" class="nx-input nx-select">
        ${(strategies || []).map(function(s) { return '<option value="' + (s.strategy || s) + '">' + (s.strategy || s) + '</option>'; }).join('')}
      </select>
    </div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.failoverConfigure()">Enregistrer la paire</button>
    </div>
  </div>`;

  /* ── Existing pairs ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>Paires configurées</h3></div>`;
  if (pairs.length) {
    html += `<div style="overflow-x:auto"><table class="nx-table"><thead><tr><th>App</th><th>Domaine</th><th>Nœud actif</th><th>Dernier failover</th><th>Actions</th></tr></thead><tbody>`;
    pairs.forEach(function(p) {
      const activeNode = p.active_node || 'primary';
      const activeBadge = activeNode === 'secondary' ? nxBadge('secondary', 'warning') : nxBadge('primary', 'success');
      html += `<tr>
        <td><strong>${p.app_id}</strong></td>
        <td><code>${p.domain || '—'}</code></td>
        <td>${activeBadge}</td>
        <td style="font-size:var(--text-xs)">${(p.last_failover || '').slice(0,19).replace('T',' ') || '—'}</td>
        <td style="white-space:nowrap">
          <button class="nx-btn nx-btn-xs" onclick="window.failoverExecute('${p.app_id}','secondary')">→ Basculer</button>
          <button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.failoverExecute('${p.app_id}','primary')">← Failback</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  } else {
    html += nxAlert('Aucune paire de failover configurée. Configurez la première ci-dessus.', 'info');
  }
  html += '</div>';

  /* ── Health check strategies info ── */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Stratégies de health check</h3></div>`;
  html += (strategies || []).length
    ? nxTable(['Stratégie', 'Interval', 'Timeout', 'Seuil', 'Description'], (strategies || []).map(function(s) {
        return [nxBadge(s.strategy, 'info'), s.interval_s + 's', s.timeout_s + 's', s.threshold, s.description || '—'];
      }))
    : nxEmpty('Aucune stratégie disponible');
  html += '</div>';

  sec.innerHTML = html;
}

// ── App Migration ─────────────────────────────────────────────────────────

export async function loadMigration(sec) {
  const [migratable, jobs] = await Promise.all([
    api('fleet/apps/migratable').catch(function() { return []; }),
    api('fleet/apps/migration').catch(function() { return []; })
  ]);

  let html = `<div class="nx-grid nx-grid-3 mb">
    ${nxStatCard(migratable.length, 'Apps migrables', 'var(--blue)')}
    ${nxStatCard(jobs.filter(function(j) { return j.status === 'completed'; }).length, 'Migrations OK', 'var(--green)')}
    ${nxStatCard(jobs.filter(function(j) { return j.status === 'running'; }).length, 'En cours', 'var(--orange)')}
  </div>`;

  html += `<div id="migration-action-result" class="mb"></div>`;

  /* ── Create migration job ── */
  html += `<div class="nx-card mb"><div class="nx-card-header"><h3>🚚 Nouvelle migration</h3></div>
    <div class="nx-form-row"><label class="nx-label">Application</label>
      <select id="mig-app-id" class="nx-input nx-select">
        <option value="">-- Sélectionner une app --</option>
        ${migratable.map(function(a) { return '<option value="' + a.id + '">' + (a.name || a.id) + ' (' + (a.domain || '') + ')</option>'; }).join('')}
      </select>
    </div>
    <div class="nx-form-row"><label class="nx-label">Nœud source</label>
      <input id="mig-source-node" class="nx-input nx-input-grow" placeholder="local"/></div>
    <div class="nx-form-row"><label class="nx-label">Nœud cible (ID)</label>
      <input id="mig-target-node" class="nx-input nx-input-grow" placeholder="node-2"/></div>
    <div class="nx-form-row"><label class="nx-label">Hôte SSH cible</label>
      <input id="mig-target-ssh" class="nx-input nx-input-grow" placeholder="192.168.1.20 ou vide si même nœud"/></div>
    <div class="nx-actions mt">
      <button class="nx-btn" onclick="window.migrationCreate()">Créer la migration</button>
    </div>
  </div>`;

  /* ── Jobs history ── */
  html += `<div class="nx-card"><div class="nx-card-header"><h3>Historique des migrations</h3>
    <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="NexoraConsole.navigate('migration')">↻</button>
  </div>`;
  if (jobs.length) {
    html += `<div style="overflow-x:auto"><table class="nx-table"><thead><tr><th>Job ID</th><th>App</th><th>Source → Cible</th><th>Statut</th><th>Créé</th><th>Actions</th></tr></thead><tbody>`;
    jobs.forEach(function(j) {
      const statusBadge = {
        completed: nxBadge('terminé', 'success'),
        running: nxBadge('en cours', 'warning'),
        failed: nxBadge('échoué', 'danger'),
        pending: nxBadge('en attente', 'info'),
      }[j.status] || nxBadge(j.status, 'neutral');
      html += `<tr>
        <td><code style="font-size:var(--text-xs)">${j.job_id}</code></td>
        <td><strong>${j.app_id}</strong></td>
        <td style="font-size:var(--text-xs)">${j.source_node_id} → ${j.target_node_id}</td>
        <td>${statusBadge}</td>
        <td style="font-size:var(--text-xs)">${(j.created_at || '').slice(0,19).replace('T',' ')}</td>
        <td>
          ${j.status === 'pending' || j.status === 'failed' ?
            '<button class="nx-btn nx-btn-xs" onclick="window.migrationExecute(\'' + j.job_id + '\')">▶ Exécuter</button>' : ''}
          <button class="nx-btn nx-btn-xs nx-btn-ghost" onclick="window.migrationStatus('${j.job_id}')">👁 Détails</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table></div>';
  } else {
    html += nxAlert('Aucune migration créée. Créez une migration ci-dessus.', 'info');
  }
  html += '</div>';

  sec.innerHTML = html;
}
