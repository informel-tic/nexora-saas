/**
 * Nexora Owner Console — Application Controller
 *
 * The owner console provides full SaaS management with passphrase-based auth.
 * All sections are available — no access restrictions.
 */

import { isAuthenticated, api, apiPost, loadAccessContext, ownerLogout, showPassphrasePrompt } from './api.js';
import { nxAlert, nxLoader } from '../console/components.js';
import * as views from '../console/views.js';

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
    await apiPost('subscriptions/' + encodeURIComponent(subId) + '/suspend', { reason: '', reactivate: true });
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

/* ── Owner-specific section: Tenants management ── */
async function loadTenants(sec) {
  try {
    const data = await api('tenants');
    const tenants = data.tenants || [];
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
  catalog: views.loadCatalog,
  'ynh-catalog': views.loadCatalog,
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
