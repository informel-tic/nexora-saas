/**
 * Nexora Owner Console — Application Controller
 *
 * The owner console provides full SaaS management with passphrase-based auth.
 * All sections are available — no access restrictions.
 */

import { isAuthenticated, api, apiPost, loadAccessContext, ownerLogout, showPassphrasePrompt } from './api.js';
import { nxAlert, nxLoader } from '/console/components.js?v=20260329';
import * as views from '/console/views.js?v=20260329';

// Toast helper
window.nxToast = function(message, level) {
  const container = document.getElementById('nx-toast-container') || (function() {
    const div = document.createElement('div');
    div.id = 'nx-toast-container';
    div.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:10000;display:flex;flex-direction:column;gap:.5rem;max-width:400px';
    document.body.appendChild(div);
    return div;
  })();
  const toast = document.createElement('div');
  const colors = { success: '#059669', warning: '#d97706', danger: '#dc2626', info: '#7c3aed' };
  const bg = colors[level] || colors.info;
  toast.style.cssText = 'padding:.75rem 1rem;border-radius:8px;color:#fff;font-size:.9rem;box-shadow:0 4px 12px rgba(0,0,0,.15);animation:fade-in .3s ease;background:' + bg;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(function() { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(function() { toast.remove(); }, 300); }, 5000);
};

// Make API helpers globally available for onclick handlers
window.api = api;
window.apiPost = apiPost;

// Re-export action handlers used by views with onclick
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
    result.innerHTML = nxAlert('Mode recommandé: <strong>' + data.recommended_mode + '</strong>', data.safe_to_install ? 'success' : 'warning') + '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
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
      setTimeout(function() { OwnerConsole.navigate('modes'); }, 800);
    } else {
      result.innerHTML = nxAlert(data.error || 'Erreur', 'critical');
    }
  } catch (e) { result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.createOrg = async function() {
  const name = prompt('Nom de l\'organisation :');
  if (!name) return;
  const email = prompt('Email de contact :');
  if (!email) return;
  try {
    const data = await apiPost('organizations', { name: name, contact_email: email, billing_address: '' });
    if (data && data.org_id) {
      window.nxToast('Organisation créée : ' + data.org_id, 'success');
      OwnerConsole.navigate('subscription');
    } else { alert('Erreur : ' + JSON.stringify(data)); }
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.createSubscription = async function() {
  const orgId = prompt('ID de l\'organisation :');
  if (!orgId) return;
  const tier = prompt('Tier (free / pro / enterprise) :', 'free');
  if (!tier) return;
  const label = prompt('Label tenant :', '');
  try {
    const data = await apiPost('subscriptions', { org_id: orgId, plan_tier: tier, tenant_label: label || '' });
    if (data && data.subscription_id) {
      window.nxToast('Souscription créée : ' + data.subscription_id, 'success');
      OwnerConsole.navigate('subscription');
    } else { alert('Erreur : ' + JSON.stringify(data)); }
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.suspendSubscription = async function(subId) {
  if (!confirm('Suspendre la souscription ' + subId + ' ?')) return;
  const reason = prompt('Raison :', 'impayé');
  try {
    await apiPost('subscriptions/' + encodeURIComponent(subId) + '/suspend', { reason: reason || 'manual' });
    window.nxToast('Souscription suspendue', 'success');
    OwnerConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.cancelSubscription = async function(subId) {
  if (!confirm('Résilier la souscription ' + subId + ' ?')) return;
  try {
    await apiPost('subscriptions/' + encodeURIComponent(subId) + '/cancel', {});
    window.nxToast('Souscription résiliée', 'success');
    OwnerConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.reactivateSubscription = async function(subId) {
  if (!confirm('Réactiver la souscription ' + subId + ' ?')) return;
  try {
    await apiPost('subscriptions/' + encodeURIComponent(subId) + '/reactivate', {});
    window.nxToast('Souscription réactivée', 'success');
    OwnerConsole.navigate('subscription');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.provisionNode = async function(nodeId) {
  const url = prompt('URL du nœud :');
  if (!url) return;
  const secret = prompt('HMAC secret (min 32 car) :');
  if (!secret || secret.length < 32) { alert('Secret HMAC trop court'); return; }
  try {
    const data = await apiPost('provisioning/provision', {
      node_id: nodeId, node_url: url, hmac_secret: secret, api_token: '', tenant_id: sessionStorage.getItem('nexora_owner_tenant') || ''
    });
    window.nxToast('Provisioning effectué pour ' + nodeId, 'success');
    OwnerConsole.navigate('provisioning');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.deprovisionNode = async function(nodeId) {
  if (!confirm('Déprovisionner ' + nodeId + ' ?')) return;
  const url = prompt('URL du nœud :');
  if (!url) return;
  try {
    await apiPost('provisioning/deprovision', { node_id: nodeId, node_url: url, hmac_secret: '' });
    window.nxToast('Déprovisionnement effectué', 'success');
    OwnerConsole.navigate('provisioning');
  } catch (e) { alert('Erreur : ' + e.message); }
};

window.enrollNode = async function() {
  const hostname = prompt('Hostname du nœud à enrôler :');
  if (!hostname) return;
  try {
    const data = await apiPost('fleet/enroll/request', { hostname: hostname, requested_by: 'owner-console' });
    if (data && data.token) {
      alert('Token d\'enrollment : ' + data.token + '\nCopiez-le sur le nœud cible.');
    }
    window.nxToast('Enrollment initié pour ' + hostname, 'success');
    OwnerConsole.navigate('fleet');
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
    await api('blueprints/' + encodeURIComponent(slug) + '/parameters');
    const modal = document.getElementById('blueprint-deploy-modal');
    const titleEl = document.getElementById('blueprint-modal-title');
    if (titleEl) titleEl.textContent = 'Déployer — ' + slug;
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
      slug: slug, domain: domain, parameters: { domain: domain, admin_email: email }, dry_run: dryRun,
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
  var q = (document.getElementById('docker-hub-query') || {}).value || '';
  var results = document.getElementById('docker-hub-results');
  if (!q.trim()) return;
  if (results) results.innerHTML = nxLoader('Recherche sur Docker Hub…');
  try {
    var data = await api('docker/hub/search?q=' + encodeURIComponent(q) + '&limit=12');
    if (!data || !data.length) { if (results) results.innerHTML = nxAlert('Aucun résultat pour "' + q + '"', 'info'); return; }
    if (results) results.innerHTML = '<div class="nx-grid nx-grid-3">' + data.map(function(r) {
      var name = r.name || r.slug || r.repo_name || '?';
      var stars = r.star_count || r.star || 0;
      var desc = (r.short_description || r.description || '').slice(0, 100);
      return '<div class="nx-card"><strong>' + name + '</strong><p style="font-size:var(--text-xs);color:var(--muted)">' + desc + '</p><p style="font-size:var(--text-xs)">⭐ ' + stars + '</p>' +
        '<button class="nx-btn nx-btn-xs mt" onclick="window.dockerQuickDeploy(\'' + name + '\')">🚀 Déployer</button></div>';
    }).join('') + '</div>';
  } catch (e) { if (results) results.innerHTML = nxAlert('Erreur Hub: ' + e.message, 'warning'); }
};

window.dockerQuickDeploy = function(image) {
  var imgInput = document.getElementById('docker-deploy-image');
  var nameInput = document.getElementById('docker-deploy-name');
  if (imgInput) imgInput.value = image + ':latest';
  if (nameInput) nameInput.value = image.replace(/[^a-z0-9-]/gi, '-').toLowerCase();
  if (imgInput) imgInput.scrollIntoView({ behavior: 'smooth' });
};

window.dockerDeploy = async function() {
  var image = (document.getElementById('docker-deploy-image') || {}).value || '';
  var name = (document.getElementById('docker-deploy-name') || {}).value || '';
  var portsRaw = (document.getElementById('docker-deploy-ports') || {}).value || '';
  var result = document.getElementById('docker-deploy-result');
  if (!image || !name) { alert('Image et nom requis'); return; }
  if (result) result.innerHTML = nxLoader('Déploiement…');
  var ports = portsRaw ? portsRaw.split(',').map(function(p) { return p.trim(); }).filter(Boolean) : [];
  try {
    var data = await apiPost('docker/deploy', { image: image, name: name, ports: ports, env: {}, volumes: [], restart: 'unless-stopped', network: '', labels: {} });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Conteneur lancé: ' + name : '✗ Erreur: ' + (data.error || data.stderr || ''), ok ? 'success' : 'critical');
    if (ok) window.nxToast('Conteneur ' + name + ' démarré', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.dockerTemplateDeploy = async function(templateName) {
  var result = document.getElementById('docker-deploy-result');
  if (!confirm('Déployer le template "' + templateName + '" ?')) return;
  if (result) result.innerHTML = nxLoader('Déploiement du template…');
  try {
    var data = await apiPost('docker/templates/deploy', { template_name: templateName, overrides: {} });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Template déployé: ' + templateName : '✗ ' + (data.error || ''), ok ? 'success' : 'critical');
    if (ok) window.nxToast('Template ' + templateName + ' déployé', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.dockerContainerAction = async function(name, action) {
  var result = document.getElementById('docker-containers-action-result');
  if (action === 'remove' && !confirm('Supprimer le conteneur "' + name + '" ?')) return;
  if (result) result.innerHTML = nxLoader(action + ' ' + name + '…');
  try {
    var data;
    if (action === 'remove') {
      data = await api('docker/containers/' + encodeURIComponent(name) + '/remove', { method: 'DELETE' });
    } else {
      data = await apiPost('docker/containers/' + encodeURIComponent(name) + '/' + action, {});
    }
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert((ok ? '✓ ' : '✗ ') + name + ' ' + action, ok ? 'success' : 'warning');
    window.nxToast(name + ' ' + action, ok ? 'success' : 'warning');
    if (ok && action !== 'remove') setTimeout(function() { OwnerConsole.navigate('docker'); }, 1500);
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.dockerContainerLogs = async function(name) {
  var panel = document.getElementById('docker-logs-panel');
  var title = document.getElementById('docker-logs-title');
  var content = document.getElementById('docker-logs-content');
  if (!panel) return;
  if (title) title.textContent = 'Logs — ' + name;
  if (content) content.textContent = 'Chargement…';
  panel.style.display = '';
  try {
    var data = await api('docker/containers/' + encodeURIComponent(name) + '/logs?lines=200');
    var logs = Array.isArray(data.logs) ? data.logs.join('\n') : String(data.logs || data._error || 'Aucun log');
    if (content) content.textContent = logs;
  } catch (e) { if (content) content.textContent = 'Erreur: ' + e.message; }
};

window.dockerComposeApply = async function() {
  var content = (document.getElementById('docker-compose-content') || {}).value || '';
  var result = document.getElementById('docker-compose-result');
  if (!content.trim()) { alert('Contenu YAML requis'); return; }
  if (result) result.innerHTML = nxLoader('Application du compose…');
  try {
    var data = await apiPost('docker/compose/apply', { content: content, path: '', project_name: '' });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Compose appliqué' : '✗ ' + (data.error || data.stderr || ''), ok ? 'success' : 'critical')
      + (data.output ? '<pre style="font-size:var(--text-xs);max-height:200px;overflow:auto">' + data.output + '</pre>' : '');
    if (ok) window.nxToast('Compose déployé', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.dockerComposeDown = async function() {
  if (!confirm('Arrêter les services compose en cours ?')) return;
  var result = document.getElementById('docker-compose-result');
  if (result) result.innerHTML = nxLoader('Arrêt…');
  try {
    var data = await apiPost('docker/compose/down', { path: '', remove_volumes: false });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Compose arrêté' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) window.nxToast('Compose arrêté', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

// ── YunoHost catalog handlers ─────────────────────────────────────────────

window.catalogSearch = async function() {
  var q = (document.getElementById('catalog-query') || {}).value || '';
  var results = document.getElementById('catalog-results');
  if (results) results.innerHTML = nxLoader('Recherche dans le catalogue YunoHost…');
  try {
    var data = await api('ynh/catalog?q=' + encodeURIComponent(q));
    if (!data || !data.length) { if (results) results.innerHTML = nxAlert('Aucune application trouvée.', 'info'); return; }
    if (results) results.innerHTML = '<div class="nx-grid nx-grid-3">' + data.slice(0, 30).map(function(a) {
      var id = a.id || a.app_id || '?';
      var name = a.name || a.label || id;
      var desc = (a.description || '').slice(0, 120);
      return '<div class="nx-card"><strong>' + name + '</strong><code style="font-size:var(--text-xs);display:block">' + id + '</code>' +
        '<p style="font-size:var(--text-xs);color:var(--muted)">' + desc + '</p>' +
        '<button class="nx-btn nx-btn-xs mt" onclick="window.catalogShowInstall(\'' + id + '\')">📥 Installer</button></div>';
    }).join('') + '</div>';
  } catch (e) { if (results) results.innerHTML = nxAlert('Erreur catalogue: ' + e.message, 'warning'); }
};

window.catalogShowInstall = function(appId) {
  var modal = document.getElementById('catalog-install-modal');
  var titleEl = document.getElementById('catalog-install-title');
  var appIdInput = document.getElementById('catalog-install-appid');
  if (titleEl) titleEl.textContent = 'Installer — ' + appId;
  if (appIdInput) appIdInput.value = appId;
  if (modal) modal.style.display = '';
  if (modal) modal.scrollIntoView({ behavior: 'smooth' });
};

window.catalogInstallConfirm = async function() {
  var appId = (document.getElementById('catalog-install-appid') || {}).value || '';
  var domain = (document.getElementById('catalog-install-domain') || {}).value || '';
  var path = (document.getElementById('catalog-install-path') || {}).value || '/';
  var label = (document.getElementById('catalog-install-label') || {}).value || '';
  var result = document.getElementById('catalog-install-result');
  if (!appId || !domain) { alert('App ID et domaine requis'); return; }
  if (result) result.innerHTML = nxLoader('Installation de ' + appId + '…');
  try {
    var data = await apiPost('ynh/apps/install', { app_id: appId, domain: domain, path: path, label: label, args: {} });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' installé sur ' + domain : '✗ ' + (data.error || ''), ok ? 'success' : 'critical');
    if (ok) { window.nxToast(appId + ' installé', 'success'); window.ynhAppsRefresh(); }
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.ynhAppsRefresh = async function() {
  var list = document.getElementById('ynh-apps-list');
  if (!list) return;
  list.innerHTML = nxLoader('Chargement…');
  try {
    var data = await api('ynh/apps');
    var apps = data.apps || (Array.isArray(data) ? data : []);
    if (!apps.length) { list.innerHTML = nxAlert('Aucune application installée', 'info'); return; }
    list.innerHTML = '<div style="overflow-x:auto"><table class="nx-table"><thead><tr><th>App</th><th>Version</th><th>Domaine</th><th>Actions</th></tr></thead><tbody>' +
      apps.map(function(a) {
        var id = a.id || '?';
        return '<tr><td><strong>' + (a.label || a.name || id) + '</strong><br/><code style="font-size:var(--text-xs)">' + id + '</code></td>' +
          '<td>' + (a.version || '—') + '</td>' +
          '<td><code style="font-size:var(--text-xs)">' + (a.domain || '—') + '</code></td>' +
          '<td><button class="nx-btn nx-btn-xs" onclick="window.ynhUpgradeApp(\'' + id + '\')">⬆ Upgrade</button> ' +
          '<button class="nx-btn nx-btn-xs nx-btn-outline" onclick="window.ynhRemoveApp(\'' + id + '\')" style="color:var(--red)">🗑 Supprimer</button></td></tr>';
      }).join('') + '</tbody></table></div>';
  } catch (e) { list.innerHTML = nxAlert('Erreur: ' + e.message, 'warning'); }
};

window.ynhUpgradeApp = async function(appId) {
  if (!confirm('Mettre à jour ' + appId + ' ?')) return;
  var result = document.getElementById('catalog-action-result');
  if (result) result.innerHTML = nxLoader('Mise à jour de ' + appId + '…');
  try {
    var data = await apiPost('ynh/apps/' + encodeURIComponent(appId) + '/upgrade', {});
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' mis à jour' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) window.nxToast(appId + ' mis à jour', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.ynhRemoveApp = async function(appId) {
  if (!confirm('Supprimer définitivement ' + appId + ' ?')) return;
  var result = document.getElementById('catalog-action-result');
  if (result) result.innerHTML = nxLoader('Suppression de ' + appId + '…');
  try {
    var data = await apiPost('ynh/apps/remove', { app_id: appId, purge: false });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ ' + appId + ' supprimé' : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast(appId + ' supprimé', 'success'); window.ynhAppsRefresh(); }
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

// ── Failover handlers ─────────────────────────────────────────────────────

window.failoverConfigure = async function() {
  var appId = (document.getElementById('fo-app-id') || {}).value || '';
  var domain = (document.getElementById('fo-domain') || {}).value || '';
  var primaryHost = (document.getElementById('fo-primary-host') || {}).value || '';
  var secondaryHost = (document.getElementById('fo-secondary-host') || {}).value || '';
  var strategy = (document.getElementById('fo-strategy') || {}).value || 'combined';
  var result = document.getElementById('failover-action-result');
  if (!appId || !domain || !primaryHost || !secondaryHost) { alert('Tous les champs sont requis'); return; }
  if (result) result.innerHTML = nxLoader('Configuration…');
  try {
    var data = await apiPost('failover/configure', {
      app_id: appId, domain: domain, primary_host: primaryHost, secondary_host: secondaryHost, health_strategy: strategy
    });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Paire configurée pour ' + appId : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast('Failover configuré pour ' + appId, 'success'); setTimeout(function() { OwnerConsole.navigate('failover'); }, 1000); }
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.failoverExecute = async function(appId, targetNode) {
  var label = targetNode === 'secondary' ? 'Basculer vers secondaire' : 'Failback vers primaire';
  if (!confirm(label + ' pour ' + appId + ' ?')) return;
  var result = document.getElementById('failover-action-result');
  if (result) result.innerHTML = nxLoader('Exécution du failover…');
  try {
    var data = await apiPost('failover/execute', { app_id: appId, target_node: targetNode, reason: 'manual' });
    var ok = data && data.success !== false;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Failover exécuté: ' + appId + ' → ' + targetNode : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast('Failover: ' + appId + ' → ' + targetNode, 'success'); setTimeout(function() { OwnerConsole.navigate('failover'); }, 1500); }
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

// ── Migration handlers ────────────────────────────────────────────────────

window.migrationCreate = async function() {
  var appId = (document.getElementById('mig-app-id') || {}).value || '';
  var sourceNode = (document.getElementById('mig-source-node') || {}).value || 'local';
  var targetNode = (document.getElementById('mig-target-node') || {}).value || '';
  var sshHost = (document.getElementById('mig-target-ssh') || {}).value || '';
  var result = document.getElementById('migration-action-result');
  if (!appId || !targetNode) { alert('App et nœud cible requis'); return; }
  if (result) result.innerHTML = nxLoader('Création du job de migration…');
  try {
    var data = await apiPost('fleet/apps/migrate', {
      app_id: appId, source_node_id: sourceNode, target_node_id: targetNode, target_ssh_host: sshHost, options: {},
    });
    var ok = data && data.job_id;
    if (result) result.innerHTML = nxAlert(ok ? '✓ Job créé: ' + data.job_id : '✗ ' + (data.error || ''), ok ? 'success' : 'warning');
    if (ok) { window.nxToast('Migration créée: ' + data.job_id, 'success'); setTimeout(function() { OwnerConsole.navigate('migration'); }, 800); }
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.migrationExecute = async function(jobId) {
  if (!confirm('Exécuter la migration ' + jobId + ' ?')) return;
  var result = document.getElementById('migration-action-result');
  if (result) result.innerHTML = nxLoader('Migration en cours…');
  try {
    var data = await apiPost('fleet/apps/migration/' + encodeURIComponent(jobId) + '/execute', {});
    var ok = data && data.status === 'completed';
    if (result) result.innerHTML = nxAlert(ok ? '✓ Migration terminée' : '⚠ ' + (data.error || 'Statut: ' + data.status), ok ? 'success' : 'warning')
      + (data.steps ? '<pre style="font-size:var(--text-xs)">' + JSON.stringify(data.steps, null, 2) + '</pre>' : '');
    if (ok) window.nxToast('Migration ' + jobId + ' terminée', 'success');
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

window.migrationStatus = async function(jobId) {
  var result = document.getElementById('migration-action-result');
  if (result) result.innerHTML = nxLoader('Chargement…');
  try {
    var data = await api('fleet/apps/migration/' + encodeURIComponent(jobId) + '/status');
    if (result) result.innerHTML = '<pre style="font-size:var(--text-xs)">' + JSON.stringify(data, null, 2) + '</pre>';
  } catch (e) { if (result) result.innerHTML = nxAlert('Erreur: ' + e.message, 'critical'); }
};

/* ── Owner-specific section: Tenants management ── */
async function loadTenants(sec) {
  try {
    const data = await api('tenants');
    const tenants = Array.isArray(data) ? data : (data.tenants || []);
    let html = '<div class="nx-card-header"><h2>Gestion des Tenants</h2></div>';
    html += '<p>Vue propriétaire de tous les tenants enregistrés sur la plateforme.</p>';
    if (tenants.length === 0) {
      html += nxAlert('Aucun tenant enregistré.', 'info');
    } else {
      html += '<table class="nx-table"><thead><tr><th>Tenant ID</th><th>Org</th><th>Tier</th><th>Status</th><th>Label</th></tr></thead><tbody>';
      for (const t of tenants) {
        html += '<tr><td><strong>' + (t.tenant_id || '-') + '</strong></td>' +
          '<td>' + (t.org_id || '-') + '</td>' +
          '<td>' + (t.tier || '-') + '</td>' +
          '<td>' + (t.status || '-') + '</td>' +
          '<td>' + (t.label || '-') + '</td></tr>';
      }
      html += '</tbody></table>';
    }
    sec.innerHTML = html;
  } catch (e) {
    sec.innerHTML = nxAlert('Erreur chargement tenants: ' + e.message, 'critical');
  }
}

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
  tenants: loadTenants,
  catalog: views.loadYnhCatalog,
  'ynh-catalog': views.loadYnhCatalog,
  failover: views.loadFailover,
  migration: views.loadMigration,
};

/* ── OwnerConsole controller ── */
const OwnerConsole = {
  loaded: new Set(),
  currentSection: null,
  main: null,
  accessContext: null,

  init: async function() {
    this.main = document.getElementById('main-content');

    // Bind logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', async function() {
        await ownerLogout();
        window.location.reload();
      });
    }

    if (!isAuthenticated()) {
      if (this.main) {
        this.main.innerHTML = nxAlert('Authentification propriétaire requise.', 'warning');
      }
      showPassphrasePrompt(null, function() {
        void OwnerConsole.init();
      });
      return;
    }

    await this.loadAccessContext();
    if (!this.accessContext) return;

    this.bindNav();
    this.navigate('dashboard');
    this.loadModeBadge();
  },

  loadAccessContext: async function() {
    try {
      const context = await loadAccessContext();
      this.accessContext = context;
      if (context && context.actor_role) {
        sessionStorage.setItem('nexora_actor_role', context.actor_role);
      }
      this.applyAccessContext();
    } catch (e) {
      this.accessContext = null;
      showPassphrasePrompt('Session invalide. Reconnectez-vous.', function() {
        void OwnerConsole.init();
      });
    }
  },

  applyAccessContext: function() {
    const badge = document.getElementById('profile-badge');
    if (badge) badge.textContent = 'owner';
    this.setRuntimeBadge((this.accessContext && this.accessContext.runtime_mode) || 'operator');
    // Owner sees everything — show all nav items
    document.querySelectorAll('#main-nav a[data-section]').forEach(function(link) {
      link.style.display = '';
    });
  },

  setRuntimeBadge: function(mode) {
    const runtimeBadge = document.getElementById('runtime-mode-badge');
    if (runtimeBadge) runtimeBadge.textContent = 'mode: ' + (mode || 'operator');
  },

  bindNav: function() {
    const self = this;
    document.querySelectorAll('#main-nav a[data-section]').forEach(function(link) {
      link.addEventListener('click', function(e) {
        e.preventDefault();
        self.navigate(link.dataset.section);
      });
      link.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); self.navigate(link.dataset.section); }
      });
    });
  },

  navigate: function(name) {
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
    this.main.innerHTML = '<div class="section active" id="sec-' + name + '">' + nxLoader() + '</div>';
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
    try {
      const mode = await api('mode');
      this.setRuntimeBadge(mode.mode || 'operator');
    } catch(e) { /* silent */ }
  }
};

window.OwnerConsole = OwnerConsole;
// Also expose as NexoraConsole for view compatibility
window.NexoraConsole = OwnerConsole;

document.addEventListener('DOMContentLoaded', function() {
  void OwnerConsole.init();
});
