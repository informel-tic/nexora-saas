import { initToken, api, apiPost, loadAccessContext, refreshTenantClaim, showTokenPrompt } from './api.js';
import { nxAlert, nxLoader } from './components.js';
import * as views from './views.js';

// Init token
initToken();

// Toast notification helper
window.nxToast = function(message, level) {
  const container = document.getElementById('nx-toast-container') || (function() {
    const div = document.createElement('div');
    div.id = 'nx-toast-container';
    div.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:10000;display:flex;flex-direction:column;gap:.5rem;max-width:400px';
    document.body.appendChild(div);
    return div;
  })();
  const toast = document.createElement('div');
  const colors = { success: '#059669', warning: '#d97706', danger: '#dc2626', info: '#2563eb' };
  const bg = colors[level] || colors.info;
  toast.style.cssText = 'padding:.75rem 1rem;border-radius:8px;color:#fff;font-size:.9rem;box-shadow:0 4px 12px rgba(0,0,0,.15);animation:fade-in .3s ease;background:' + bg;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(function() { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(function() { toast.remove(); }, 300); }, 5000);
};

// Make API helpers globally available for onclick handlers in views
window.api = api;
window.apiPost = apiPost;

window.closeServiceLogsPanel = function() {
  const panel = document.getElementById('service-logs-panel');
  if (panel) panel.style.display = 'none';
};

window.closeBlueprintModal = function() {
  const modal = document.getElementById('blueprint-deploy-modal');
  if (modal) modal.style.display = 'none';
};

window.closeDockerLogsPanel = function() {
  const panel = document.getElementById('docker-logs-panel');
  if (panel) panel.style.display = 'none';
};

window.closeCatalogInstallModal = function() {
  const modal = document.getElementById('catalog-install-modal');
  if (modal) modal.style.display = 'none';
};

// Define specific actions from views that need to be global for onclick
window.praAction = async function(action) {
  const result = document.getElementById('pra-action-result');
  result.innerHTML = nxLoader('Exécution…');
  try {
    const endpoints = { snapshot: 'pra/snapshot', readiness: 'pra/readiness', export: 'pra/export' };
    const data = await api(endpoints[action] || 'pra');
    result.innerHTML = nxAlert('Action terminée', 'success') + '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) { result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.fleetAction = async function(nodeId, action) {
  try {
    const data = await apiPost('fleet/' + encodeURIComponent(nodeId) + '/' + action);
    alert(JSON.stringify(data));
  } catch(e) { alert('Erreur: ' + e.message); }
};

window.runAdoption = async function() {
  const domain = document.getElementById('adopt-domain').value;
  const path = document.getElementById('adopt-path').value || '/nexora';
  const result = document.getElementById('adoption-result');
  result.innerHTML = nxLoader('Analyse…');
  try {
    const data = await api('adoption/report?domain=' + encodeURIComponent(domain) + '&path=' + encodeURIComponent(path));
    result.innerHTML = nxAlert('Mode recommandé: <strong>' + data.recommended_mode + '</strong>' +
      (data.suggested_path ? ' — Chemin: <strong>' + data.suggested_path + '</strong>' : ''),
      data.safe_to_install ? 'success' : 'warning') +
      '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) { result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.runImport = async function() {
  const domain = document.getElementById('adopt-domain').value;
  const path = document.getElementById('adopt-path').value || '/nexora';
  const result = document.getElementById('adoption-result');
  result.innerHTML = nxLoader('Import…');
  try {
    const data = await apiPost('adoption/import?domain=' + encodeURIComponent(domain) + '&path=' + encodeURIComponent(path));
    result.innerHTML = nxAlert('État importé avec succès', 'success') + '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) { result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.switchMode = async function() {
  const target = document.getElementById('mode-select').value;
  const reason = document.getElementById('mode-reason').value || '';
  const result = document.getElementById('mode-switch-result');
  result.innerHTML = nxLoader('Changement…');
  try {
    const data = await apiPost('mode/switch?target=' + encodeURIComponent(target) + '&reason=' + encodeURIComponent(reason));
    if (data.success) {
      result.innerHTML = nxAlert('Mode changé: ' + data.previous_mode + ' → ' + data.current_mode, 'success');
      const runtimeBadge = document.getElementById('runtime-mode-badge');
      if (runtimeBadge) runtimeBadge.textContent = 'mode: ' + (data.current_mode || 'observer');
      setTimeout(function() { NexoraConsole.navigate('modes'); }, 800);
    } else {
      result.innerHTML = nxAlert(data.error || 'Erreur', 'critical');
    }
  } catch (e) {
    result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.createOrg = async function() {
  const name = prompt('Nom de l\'organisation :');
  if (!name) return;
  const email = prompt('Email de contact :');
  if (!email) return;
  try {
    const data = await apiPost('organizations', { name: name, contact_email: email, billing_address: '' });
    if (data && data.org_id) {
      alert('Organisation créée : ' + data.org_id);
      NexoraConsole.navigate('subscription');
    } else {
      alert('Erreur : ' + JSON.stringify(data));
    }
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.createSubscription = async function() {
  const orgId = prompt('ID de l\'organisation :');
  if (!orgId) return;
  const tier = prompt('Tier (free / pro / enterprise) :', 'free');
  if (!tier) return;
  const label = prompt('Label tenant (optionnel) :', '');
  try {
    const data = await apiPost('subscriptions', { org_id: orgId, plan_tier: tier, tenant_label: label || '' });
    if (data && data.subscription_id) {
      alert('Souscription créée : ' + data.subscription_id + ' (tenant: ' + (data.tenant_id || '-') + ')');
      NexoraConsole.navigate('subscription');
    } else {
      alert('Erreur : ' + JSON.stringify(data));
    }
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.suspendSubscription = async function(subId) {
  if (!confirm('Suspendre la souscription ' + subId + ' ?')) return;
  const reason = prompt('Raison de la suspension :', 'impayé');
  try {
    const data = await apiPost('subscriptions/' + encodeURIComponent(subId) + '/suspend', { reason: reason || 'manual' });
    window.nxToast('Souscription suspendue', 'success');
    NexoraConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.cancelSubscription = async function(subId) {
  if (!confirm('Résilier définitivement la souscription ' + subId + ' ?')) return;
  try {
    const data = await apiPost('subscriptions/' + encodeURIComponent(subId) + '/cancel', {});
    window.nxToast('Souscription résiliée', 'success');
    NexoraConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.reactivateSubscription = async function(subId) {
  if (!confirm('Réactiver la souscription ' + subId + ' ?')) return;
  try {
    const data = await apiPost('subscriptions/' + encodeURIComponent(subId) + '/reactivate', {});
    window.nxToast('Souscription réactivée', 'success');
    NexoraConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.provisionNode = async function(nodeId) {
  const url = prompt('URL du nœud (ex: https://node.example.tld:38121) :');
  if (!url) return;
  const secret = prompt('HMAC secret (min 32 caractères) :');
  if (!secret || secret.length < 32) { alert('Secret HMAC trop court (min 32 caractères)'); return; }
  try {
    const data = await apiPost('provisioning/provision', {
      node_id: nodeId, node_url: url, hmac_secret: secret, api_token: '', tenant_id: (sessionStorage.getItem('nexora_tenant_id') || '')
    });
    alert('Provisioning ' + (data.status || 'effectué') + ' pour ' + nodeId);
    NexoraConsole.navigate('provisioning');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.deprovisionNode = async function(nodeId) {
  if (!confirm('Déprovisionner le nœud ' + nodeId + ' ?')) return;
  const url = prompt('URL du nœud :');
  if (!url) return;
  try {
    const data = await apiPost('provisioning/deprovision', { node_id: nodeId, node_url: url, hmac_secret: '' });
    alert('Déprovisionnement ' + (data.status || 'effectué') + ' pour ' + nodeId);
    NexoraConsole.navigate('provisioning');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.enrollNode = async function() {
  const hostname = prompt('Hostname ou adresse du nœud à enrôler :');
  if (!hostname) return;
  try {
    const data = await apiPost('fleet/enroll/request', { hostname: hostname, requested_by: 'console' });
    if (data && data.token) {
      alert('Token d\'enrollment généré : ' + data.token + '\nCopiez ce token sur le nœud cible.');
    } else {
      alert('Enrollment initié : ' + JSON.stringify(data));
    }
    window.nxToast('Enrollment initié pour ' + hostname, 'success');
    NexoraConsole.navigate('fleet');
  } catch (e) { alert('Erreur : ' + e.message); }
};

// ── Service management handlers ──────────────────────────────────────────

window.serviceAction = async function(serviceName, action) {
  const result = document.getElementById('services-action-result');
  if (result) result.innerHTML = nxLoader('Action en cours…');
  try {
    const data = await apiPost('services/' + encodeURIComponent(serviceName) + '/' + action, {});
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert((ok ? '✓ ' : '✗ ') + serviceName + ' ' + action + (data.via ? ' (via ' + data.via + ')' : ''), ok ? 'success' : 'warning');
    window.nxToast(serviceName + ' ' + action, ok ? 'success' : 'warning');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.serviceViewLogs = async function(serviceName) {
  const panel = document.getElementById('service-logs-panel');
  const title = document.getElementById('service-logs-title');
  const content = document.getElementById('service-logs-content');
  if (!panel) return;
  if (title) title.textContent = 'Logs — ' + serviceName;
  if (content) content.textContent = 'Chargement…';
  panel.style.display = '';
  try {
    const data = await api('services/' + encodeURIComponent(serviceName) + '/logs?lines=200');
    const logs = Array.isArray(data.logs) ? data.logs.join('\n') : String(data.logs || data._error || 'Aucun log');
    if (content) content.textContent = logs;
  } catch (e) {
    if (content) content.textContent = 'Erreur: ' + e.message;
  }
};

// ── Blueprint deployment handlers ────────────────────────────────────────

window._currentBlueprintSlug = null;

window.blueprintParams = async function(slug) {
  window._currentBlueprintSlug = slug;
  try {
    const params = await api('blueprints/' + encodeURIComponent(slug) + '/parameters');
    const modal = document.getElementById('blueprint-deploy-modal');
    const titleEl = document.getElementById('blueprint-modal-title');
    if (titleEl) titleEl.textContent = 'Déployer — ' + (params.name || slug);
    if (modal) modal.style.display = '';
    window.nxToast('Paramètres chargés pour ' + slug, 'info');
  } catch (e) {
    window.nxToast('Erreur: ' + e.message, 'danger');
  }
};

window.deployBlueprint = function(slug) {
  window._currentBlueprintSlug = slug;
  const modal = document.getElementById('blueprint-deploy-modal');
  const titleEl = document.getElementById('blueprint-modal-title');
  if (titleEl) titleEl.textContent = 'Déployer — ' + slug;
  if (modal) modal.style.display = '';
};

window.deployBlueprintConfirm = async function() {
  await window._doBlueprintDeploy(false);
};

window.deployBlueprintDry = async function() {
  await window._doBlueprintDeploy(true);
};

window._doBlueprintDeploy = async function(dryRun) {
  const slug = window._currentBlueprintSlug;
  if (!slug) { alert('Aucun blueprint sélectionné'); return; }
  const domain = (document.getElementById('bp-domain') || {}).value || '';
  const email = (document.getElementById('bp-admin-email') || {}).value || '';
  const result = document.getElementById('bp-deploy-result');
  if (result) result.innerHTML = nxLoader('Déploiement en cours…');
  try {
    const data = await apiPost('blueprints/' + encodeURIComponent(slug) + '/deploy', {
      slug: slug,
      domain: domain,
      parameters: { domain: domain, admin_email: email },
      dry_run: dryRun,
    });
    const ok = data && (data.deployed > 0 || data.dry_run);
    if (result) result.innerHTML = nxAlert(
      dryRun ? 'Dry run: ' + JSON.stringify(data.apps_planned || []) :
        'Déploiement terminé: ' + (data.deployed || 0) + '/' + (data.total || 0) + ' apps',
      ok ? 'success' : 'warning'
    ) + '<pre style="font-size:var(--text-xs)">' + JSON.stringify(data, null, 2) + '</pre>';
    window.nxToast('Blueprint ' + slug + (dryRun ? ' (dry run)' : ' déployé'), ok ? 'success' : 'warning');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

// ── Docker handlers ──────────────────────────────────────────────────────

window.dockerHubSearch = async function() {
  const q = (document.getElementById('docker-hub-query') || {}).value || '';
  const results = document.getElementById('docker-hub-results');
  if (!q.trim()) return;
  if (results) results.innerHTML = nxLoader('Recherche sur Docker Hub…');
  try {
    const data = await api('docker/hub/search?q=' + encodeURIComponent(q) + '&limit=12');
    if (!data || !data.length) {
      if (results) results.innerHTML = nxAlert('Aucun résultat pour "' + q + '"', 'info');
      return;
    }
    if (results) results.innerHTML = '<div class="nx-grid nx-grid-3">' + data.map(function(r) {
      const name = r.name || r.slug || r.repo_name || '?';
      const stars = r.star_count || r.star || 0;
      const desc = (r.short_description || r.description || '').slice(0, 100);
      return '<div class="nx-card">' +
        '<strong>' + name + '</strong>' +
        '<p style="font-size:var(--text-xs);color:var(--muted)">' + desc + '</p>' +
        '<p style="font-size:var(--text-xs)">⭐ ' + stars + '</p>' +
        '<button class="nx-btn nx-btn-xs mt" onclick="window.dockerQuickDeploy(\'' + name + '\')" title="Déployer ' + name + '">🚀 Déployer</button>' +
        '</div>';
    }).join('') + '</div>';
  } catch (e) {
    if (results) results.innerHTML = nxAlert('Erreur Hub: ' + e.message, 'warning');
  }
};

window.dockerQuickDeploy = function(image) {
  const imgInput = document.getElementById('docker-deploy-image');
  const nameInput = document.getElementById('docker-deploy-name');
  if (imgInput) imgInput.value = image + ':latest';
  if (nameInput) nameInput.value = image.replace(/[^a-z0-9-]/gi, '-').toLowerCase();
  imgInput && imgInput.scrollIntoView({ behavior: 'smooth' });
};

window.dockerDeploy = async function() {
  const image = (document.getElementById('docker-deploy-image') || {}).value || '';
  const name = (document.getElementById('docker-deploy-name') || {}).value || '';
  const portsRaw = (document.getElementById('docker-deploy-ports') || {}).value || '';
  const result = document.getElementById('docker-deploy-result');
  if (!image || !name) { alert('Image et nom requis'); return; }
  if (result) result.innerHTML = nxLoader('Déploiement…');
  const ports = portsRaw ? portsRaw.split(',').map(function(p) { return p.trim(); }).filter(Boolean) : [];
  try {
    const data = await apiPost('docker/deploy', { image: image, name: name, ports: ports, env: {}, volumes: [], restart: 'unless-stopped', network: '', labels: {} });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Conteneur lancé: ' + name : '✗ Erreur: ' + (data.error || data.stderr || ''), ok ? 'success' : 'critical');
    if (ok) window.nxToast('Conteneur ' + name + ' démarré', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.dockerTemplateDeploy = async function(templateName) {
  const result = document.getElementById('docker-deploy-result');
  if (!confirm('Déployer le template "' + templateName + '" ?')) return;
  if (result) result.innerHTML = nxLoader('Déploiement du template…');
  try {
    const data = await apiPost('docker/templates/deploy', { template_name: templateName, overrides: {} });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Template déployé: ' + templateName : '✗ ' + (data.error || ''), ok ? 'success' : 'critical');
    if (ok) window.nxToast('Template ' + templateName + ' déployé', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.dockerContainerAction = async function(name, action) {
  const result = document.getElementById('docker-containers-action-result');
  if (action === 'remove' && !confirm('Supprimer le conteneur "' + name + '" ?')) return;
  if (result) result.innerHTML = nxLoader(action + ' ' + name + '…');
  try {
    let data;
    if (action === 'remove') {
      data = await api('docker/containers/' + encodeURIComponent(name) + '/remove', { method: 'DELETE' });
    } else {
      data = await apiPost('docker/containers/' + encodeURIComponent(name) + '/' + action, {});
    }
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert((ok ? '✓ ' : '✗ ') + name + ' ' + action, ok ? 'success' : 'warning');
    window.nxToast(name + ' ' + action, ok ? 'success' : 'warning');
    if (ok && action !== 'remove') setTimeout(function() { NexoraConsole.navigate('docker'); }, 1500);
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.dockerContainerLogs = async function(name) {
  const panel = document.getElementById('docker-logs-panel');
  const title = document.getElementById('docker-logs-title');
  const content = document.getElementById('docker-logs-content');
  if (!panel) return;
  if (title) title.textContent = 'Logs — ' + name;
  if (content) content.textContent = 'Chargement…';
  panel.style.display = '';
  try {
    const data = await api('docker/containers/' + encodeURIComponent(name) + '/logs?lines=200');
    const logs = Array.isArray(data.logs) ? data.logs.join('\n') : String(data.logs || data._error || 'Aucun log');
    if (content) content.textContent = logs;
  } catch (e) {
    if (content) content.textContent = 'Erreur: ' + e.message;
  }
};

window.dockerComposeApply = async function() {
  const content = (document.getElementById('docker-compose-content') || {}).value || '';
  const result = document.getElementById('docker-compose-result');
  if (!content.trim()) { alert('Contenu YAML requis'); return; }
  if (result) result.innerHTML = nxLoader('Application du compose…');
  try {
    const data = await apiPost('docker/compose/apply', { content: content, path: '', project_name: '' });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Compose appliqué' : '✗ ' + (data.error || data.stderr || ''), ok ? 'success' : 'critical')
      + (data.output ? '<pre style="font-size:var(--text-xs);max-height:200px;overflow:auto">' + data.output + '</pre>' : '');
    if (ok) window.nxToast('Compose déployé', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.dockerComposeDown = async function() {
  if (!confirm('Arrêter les services compose en cours ?')) return;
  const result = document.getElementById('docker-compose-result');
  if (result) result.innerHTML = nxLoader('Arrêt…');
  try {
    const data = await apiPost('docker/compose/down', { path: '', remove_volumes: false });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Compose arrêté' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) window.nxToast('Compose arrêté', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

// ── YunoHost catalog handlers ─────────────────────────────────────────────

window.catalogSearch = async function() {
  const q = (document.getElementById('catalog-query') || {}).value || '';
  const results = document.getElementById('catalog-results');
  if (results) results.innerHTML = nxLoader('Recherche dans le catalogue YunoHost…');
  try {
    const data = await api('ynh/catalog?q=' + encodeURIComponent(q));
    if (!data || !data.length) {
      if (results) results.innerHTML = nxAlert('Aucune application trouvée. Le catalogue YunoHost nécessite une connexion internet.', 'info');
      return;
    }
    if (results) results.innerHTML = '<div class="nx-grid nx-grid-3">' + data.slice(0, 30).map(function(a) {
      const id = a.id || a.app_id || '?';
      const name = a.name || a.label || id;
      const desc = (a.description || '').slice(0, 120);
      return '<div class="nx-card"><strong>' + name + '</strong><code style="font-size:var(--text-xs);display:block">' + id + '</code>' +
        '<p style="font-size:var(--text-xs);color:var(--muted)">' + desc + '</p>' +
        '<button class="nx-btn nx-btn-xs mt" onclick="window.catalogShowInstall(\'' + id + '\')">📥 Installer</button></div>';
    }).join('') + '</div>';
  } catch (e) {
    if (results) results.innerHTML = nxAlert('Erreur catalogue: ' + e.message, 'warning');
  }
};

window.catalogShowInstall = function(appId) {
  const modal = document.getElementById('catalog-install-modal');
  const titleEl = document.getElementById('catalog-install-title');
  const appIdInput = document.getElementById('catalog-install-appid');
  if (titleEl) titleEl.textContent = 'Installer — ' + appId;
  if (appIdInput) appIdInput.value = appId;
  if (modal) modal.style.display = '';
  modal && modal.scrollIntoView({ behavior: 'smooth' });
};

window.catalogInstallConfirm = async function() {
  const appId = (document.getElementById('catalog-install-appid') || {}).value || '';
  const domain = (document.getElementById('catalog-install-domain') || {}).value || '';
  const path = (document.getElementById('catalog-install-path') || {}).value || '/';
  const label = (document.getElementById('catalog-install-label') || {}).value || '';
  const result = document.getElementById('catalog-install-result');
  if (!appId || !domain) { alert('App ID et domaine requis'); return; }
  if (result) result.innerHTML = nxLoader('Installation de ' + appId + '… (peut prendre quelques minutes)');
  try {
    const data = await apiPost('ynh/apps/install', { app_id: appId, domain: domain, path: path, label: label, args: {} });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' installé sur ' + domain : '✗ ' + (data.error || ''), ok ? 'success' : 'critical');
    if (ok) { window.nxToast(appId + ' installé', 'success'); window.ynhAppsRefresh(); }
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.ynhAppsRefresh = async function() {
  const list = document.getElementById('ynh-apps-list');
  if (!list) return;
  list.innerHTML = nxLoader('Chargement…');
  try {
    const data = await api('ynh/apps');
    const apps = data.apps || (Array.isArray(data) ? data : []);
    if (!apps.length) { list.innerHTML = nxAlert('Aucune application installée', 'info'); return; }
    list.innerHTML = '<div style="overflow-x:auto"><table class="nx-table"><thead><tr><th>App</th><th>Version</th><th>Domaine</th><th>Actions</th></tr></thead><tbody>' +
      apps.map(function(a) {
        const id = a.id || '?';
        return '<tr><td><strong>' + (a.label || a.name || id) + '</strong><br/><code style="font-size:var(--text-xs)">' + id + '</code></td>' +
          '<td>' + (a.version || '—') + '</td>' +
          '<td><code style="font-size:var(--text-xs)">' + (a.domain || '—') + '</code></td>' +
          '<td><button class="nx-btn nx-btn-xs" onclick="window.ynhUpgradeApp(\'' + id + '\')">⬆ Upgrade</button> ' +
          '<button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.ynhRemoveApp(\'' + id + '\')" style="color:var(--red)">🗑 Supprimer</button></td></tr>';
      }).join('') + '</tbody></table></div>';
  } catch (e) {
    list.innerHTML = nxAlert('Erreur: ' + e.message, 'warning');
  }
};

window.ynhUpgradeApp = async function(appId) {
  if (!confirm('Mettre à jour ' + appId + ' ?')) return;
  const result = document.getElementById('catalog-action-result');
  if (result) result.innerHTML = nxLoader('Mise à jour de ' + appId + '…');
  try {
    const data = await apiPost('ynh/apps/' + encodeURIComponent(appId) + '/upgrade', {});
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' mis à jour' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) window.nxToast(appId + ' mis à jour', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.ynhRemoveApp = async function(appId) {
  if (!confirm('Supprimer définitivement ' + appId + ' ?')) return;
  const result = document.getElementById('catalog-action-result');
  if (result) result.innerHTML = nxLoader('Suppression de ' + appId + '…');
  try {
    const data = await apiPost('ynh/apps/remove', { app_id: appId, purge: false });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' supprimé' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast(appId + ' supprimé', 'success'); window.ynhAppsRefresh(); }
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

// ── Failover handlers ─────────────────────────────────────────────────────

window.failoverConfigure = async function() {
  const appId = (document.getElementById('fo-app-id') || {}).value || '';
  const domain = (document.getElementById('fo-domain') || {}).value || '';
  const primaryHost = (document.getElementById('fo-primary-host') || {}).value || '';
  const secondaryHost = (document.getElementById('fo-secondary-host') || {}).value || '';
  const strategy = (document.getElementById('fo-strategy') || {}).value || 'combined';
  const result = document.getElementById('failover-action-result');
  if (!appId || !domain || !primaryHost || !secondaryHost) { alert('Tous les champs sont requis'); return; }
  if (result) result.innerHTML = nxLoader('Configuration…');
  try {
    const data = await apiPost('failover/configure', {
      app_id: appId, domain: domain,
      primary_host: primaryHost, secondary_host: secondaryHost,
      health_strategy: strategy
    });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Paire configurée pour ' + appId : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast('Failover configuré pour ' + appId, 'success'); setTimeout(function() { NexoraConsole.navigate('failover'); }, 1000); }
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.failoverExecute = async function(appId, targetNode) {
  const label = targetNode === 'secondary' ? 'Basculer vers secondaire' : 'Failback vers primaire';
  if (!confirm(label + ' pour ' + appId + ' ?')) return;
  const result = document.getElementById('failover-action-result');
  if (result) result.innerHTML = nxLoader('Exécution du failover…');
  try {
    const data = await apiPost('failover/execute', { app_id: appId, target_node: targetNode, reason: 'manual' });
    const ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Failover exécuté: ' + appId + ' → ' + targetNode : '✗ ' + (data.nginx && data.nginx.error || data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast('Failover: ' + appId + ' → ' + targetNode, 'success'); setTimeout(function() { NexoraConsole.navigate('failover'); }, 1500); }
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

// ── Migration handlers ────────────────────────────────────────────────────

window.migrationCreate = async function() {
  const appId = (document.getElementById('mig-app-id') || {}).value || '';
  const sourceNode = (document.getElementById('mig-source-node') || {}).value || 'local';
  const targetNode = (document.getElementById('mig-target-node') || {}).value || '';
  const sshHost = (document.getElementById('mig-target-ssh') || {}).value || '';
  const result = document.getElementById('migration-action-result');
  if (!appId || !targetNode) { alert('App et nœud cible requis'); return; }
  if (result) result.innerHTML = nxLoader('Création du job de migration…');
  try {
    const data = await apiPost('fleet/apps/migrate', {
      app_id: appId,
      source_node_id: sourceNode,
      target_node_id: targetNode,
      target_ssh_host: sshHost,
      options: {},
    });
    const ok = data && data.job_id;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Job créé: ' + data.job_id : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) {
      window.nxToast('Migration créée: ' + data.job_id, 'success');
      setTimeout(function() { NexoraConsole.navigate('migration'); }, 800);
    }
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.migrationExecute = async function(jobId) {
  if (!confirm('Exécuter la migration ' + jobId + ' ? Cette opération peut être longue.')) return;
  const result = document.getElementById('migration-action-result');
  if (result) result.innerHTML = nxLoader('Migration en cours… (peut prendre plusieurs minutes)');
  try {
    const data = await apiPost('fleet/apps/migration/' + encodeURIComponent(jobId) + '/execute', {});
    const ok = data && data.status === 'completed';
    if (result) result.innerHTML = nxAlert(ok ? '✓ Migration terminée' : '⚠ ' + (data.error || 'Statut: ' + data.status), ok ? 'success' : 'warning')
      + (data.steps ? '<pre style="font-size:var(--text-xs)">' + JSON.stringify(data.steps, null, 2) + '</pre>' : '');
    if (ok) window.nxToast('Migration ' + jobId + ' terminée', 'success');
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

window.migrationStatus = async function(jobId) {
  const result = document.getElementById('migration-action-result');
  if (result) result.innerHTML = nxLoader('Chargement…');
  try {
    const data = await api('fleet/apps/migration/' + encodeURIComponent(jobId) + '/status');
    if (result) result.innerHTML = '<pre style="font-size:var(--text-xs)">' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) {
    if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical');
  }
};

/* ── Section renderers map ── */
const sectionRenderers = {
  dashboard: views.loadDashboard,
  sla: views.loadScores,
  scores: views.loadScores,
  apps: views.loadApps,
  services: views.loadServices,
  domains: views.loadDomains,
  security: views.loadSecurity,
  pra: views.loadPra,
  fleet: views.loadFleet,
  blueprints: views.loadBlueprints,
  automation: views.loadAutomation,
  adoption: views.loadAdoption,
  modes: views.loadModes,
  docker: views.loadDocker,
  storage: views.loadStorage,
  notifications: views.loadNotifications,
  hooks: views.loadHooks,
  governance: views.loadGovernanceRisks,
  'sla-tracking': views.loadSlaTracking,
  subscription: views.loadSubscription,
  provisioning: views.loadProvisioning,
  settings: views.loadSettings,
  catalog: views.loadYnhCatalog,
  'ynh-catalog': views.loadYnhCatalog,
  failover: views.loadFailover,
  migration: views.loadMigration,
};

/* ── NexoraConsole controller ── */
const NexoraConsole = {
  loaded: new Set(),
  currentSection: null,
  main: null,
  accessContext: null,

  init: async function() {
    this.main = document.getElementById('main-content');
    const token = (sessionStorage.getItem('nexora_token') || '').trim();
    if (!token) {
      if (this.main) {
        this.main.innerHTML = nxAlert('Authentification requise. Entrez un token pour continuer.', 'warning');
      }
      showTokenPrompt();
      return;
    }
    await this.loadAccessContext();
    if (!this.accessContext) {
      return;
    }
    this.bindNav();
    this.navigate(this.defaultSection());
    this.loadModeBadge();
  },

  defaultSection: function() {
    const allowed = (this.accessContext && this.accessContext.allowed_sections) || [];
    if (allowed.length > 0) {
      if (allowed.indexOf('dashboard') >= 0) {
        return 'dashboard';
      }
      return allowed[0];
    }
    return 'dashboard';
  },

  loadAccessContext: async function() {
    try {
      const storedTenant = (sessionStorage.getItem('nexora_tenant_id') || '').trim();
      const storedToken = (sessionStorage.getItem('nexora_token') || '').trim();
      if (storedToken && storedTenant) {
        try { await refreshTenantClaim(); } catch (e) { /* noop */ }
      }
      const context = await loadAccessContext();
      this.accessContext = context;
      if (context && context.actor_role) {
        sessionStorage.setItem('nexora_actor_role', context.actor_role);
      }
      if (context && context.tenant_id) {
        sessionStorage.setItem('nexora_tenant_id', context.tenant_id);
      } else {
        sessionStorage.removeItem('nexora_tenant_id');
      }
      try { await refreshTenantClaim(); } catch (e) { /* noop */ }
      this.applyAccessContext();
    } catch (e) {
      this.accessContext = null;
    }
  },

  applyAccessContext: function() {
    const badge = document.getElementById('profile-badge');
    const actorRole = (this.accessContext && this.accessContext.actor_role) || 'observer';
    if (badge) {
      badge.textContent = actorRole;
    }
    this.setRuntimeBadge((this.accessContext && this.accessContext.runtime_mode) || 'observer');

    const allowed = new Set((this.accessContext && this.accessContext.allowed_sections) || []);
    const enforceAllowed = allowed.size > 0;

    document.querySelectorAll('#main-nav a[data-section]').forEach(function(link) {
      const section = link.dataset.section;
      const visible = !enforceAllowed || allowed.has(section);
      link.style.display = visible ? '' : 'none';
    });
  },

  isSectionAllowed: function(name) {
    const allowed = (this.accessContext && this.accessContext.allowed_sections) || [];
    if (!allowed.length) return true;
    return allowed.indexOf(name) >= 0;
  },

  setRuntimeBadge: function(mode) {
    const runtimeBadge = document.getElementById('runtime-mode-badge');
    if (runtimeBadge) {
      runtimeBadge.textContent = 'mode: ' + (mode || 'observer');
    }
  },

  bindNav: function() {
    const self = this;
    document.querySelectorAll('#main-nav a[data-section]').forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        self.navigate(link.dataset.section);
      });
      link.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          self.navigate(link.dataset.section);
        }
      });
    });
  },

  navigate: function(name) {
    if (!this.isSectionAllowed(name)) {
      window.nxToast('Section non autorisée pour ce profil: ' + name, 'warning');
      const fallback = this.defaultSection();
      if (!this.isSectionAllowed(fallback)) {
        this.main.innerHTML = nxAlert('Aucune section autorisée pour ce profil.', 'warning');
        return;
      }
      name = fallback;
    }
    document.querySelectorAll('#main-nav a[data-section]').forEach(function(a) {
      a.classList.toggle('active', a.dataset.section === name);
      a.setAttribute('aria-current', a.dataset.section === name ? 'page' : 'false');
    });
    this.currentSection = name;
    this.renderSection(name);
  },

  renderSection: function(name) {
    const renderer = sectionRenderers[name];
    if (!renderer) {
      this.main.innerHTML = nxAlert('Section inconnue: ' + name, 'danger');
      return;
    }
    this.main.innerHTML = `<div class="section active" id="sec-${name}">${nxLoader()}</div>`;
    this.loaded.delete(name);
    renderer(document.getElementById('sec-' + name), this).catch(function(e) {
      const sec = document.getElementById('sec-' + name);
      if (sec) sec.innerHTML = nxAlert('Erreur de chargement: ' + e.message, 'critical');
      window.nxToast('Erreur section ' + name + ': ' + e.message, 'danger');
    });
  },

  loadModeBadge: async function() {
    if (this.accessContext && this.accessContext.runtime_mode) {
      this.setRuntimeBadge(this.accessContext.runtime_mode);
    }
    if (this.accessContext && this.accessContext.subscriber_mode) {
      return;
    }
    try {
      const mode = await api('mode');
      this.setRuntimeBadge(mode.mode || 'observer');
    } catch(e) { /* silent */ }
  }
};

window.NexoraConsole = NexoraConsole;

document.addEventListener('DOMContentLoaded', function() {
  void NexoraConsole.init();
});
