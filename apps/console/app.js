import { initToken, api, apiPost, loadAccessContext } from './api.js';
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
      document.getElementById('profile-badge').textContent = data.current_mode;
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
    const data = await apiPost('subscriptions/' + encodeURIComponent(subId) + '/suspend', { reason: '', reactivate: true });
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
  provisioning: views.loadProvisioning
};

const ADMIN_ONLY_SECTIONS = new Set([
  'adoption',
  'modes',
  'docker',
  'storage',
  'notifications',
  'hooks',
  'governance',
  'sla-tracking'
]);

/* ── NexoraConsole controller ── */
const NexoraConsole = {
  loaded: new Set(),
  currentSection: null,
  main: null,
  accessContext: null,

  init: async function() {
    this.main = document.getElementById('main-content');
    await this.loadAccessContext();
    this.bindNav();
    this.navigate(this.defaultSection());
    this.loadModeBadge();
  },

  defaultSection: function() {
    if (this.accessContext && this.accessContext.subscriber_mode) {
      return 'fleet';
    }
    return 'dashboard';
  },

  loadAccessContext: async function() {
    try {
      const context = await loadAccessContext();
      this.accessContext = context;
      this.applyAccessContext();
    } catch (e) {
      this.accessContext = null;
    }
  },

  applyAccessContext: function() {
    const badge = document.getElementById('profile-badge');
    const actorRole = (this.accessContext && this.accessContext.actor_role) || '';
    if (badge && actorRole) {
      badge.textContent = actorRole;
    }

    const allowed = new Set((this.accessContext && this.accessContext.allowed_sections) || []);
    const subscriberMode = !!(this.accessContext && this.accessContext.subscriber_mode);

    document.querySelectorAll('#main-nav a[data-section]').forEach(function(link) {
      const section = link.dataset.section;
      if (!subscriberMode) {
        link.style.display = '';
        return;
      }
      const blocked = ADMIN_ONLY_SECTIONS.has(section) || (allowed.size > 0 && !allowed.has(section));
      link.style.display = blocked ? 'none' : '';
    });
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
    if (this.accessContext && this.accessContext.subscriber_mode) {
      return;
    }
    try {
      const mode = await api('mode');
      const badge = document.getElementById('profile-badge');
      badge.textContent = mode.mode || 'observer';
    } catch(e) { /* silent */ }
  }
};

window.NexoraConsole = NexoraConsole;

document.addEventListener('DOMContentLoaded', function() {
  void NexoraConsole.init();
});
