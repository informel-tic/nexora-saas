/**
 * Nexora Owner Console — API client
 *
 * Authentication uses a passphrase (not an API token).
 * After successful login the backend returns a session token
 * which is stored in sessionStorage and sent on every request.
 */

export const BASE = '';  // Owner console is served at root of saas.* subdomain

function sessionContext() {
  return {
    sessionToken: (sessionStorage.getItem('nexora_owner_session') || '').trim(),
    tenantId: (sessionStorage.getItem('nexora_owner_tenant') || '').trim(),
  };
}

function buildHeaders() {
  const ctx = sessionContext();
  const headers = { Accept: 'application/json' };
  if (ctx.sessionToken) {
    headers['X-Nexora-Session'] = ctx.sessionToken;
  }
  if (ctx.tenantId) {
    headers['X-Nexora-Tenant-Id'] = ctx.tenantId;
  }
  headers['X-Nexora-Actor-Role'] = 'owner';
  return headers;
}

async function parseErrorDetail(res) {
  try {
    const payload = await res.json();
    if (payload && payload.detail) return String(payload.detail);
  } catch (e) { /* noop */ }
  return '';
}

async function requestWithAuth(url, buildOpts) {
  const res = await fetch(url, buildOpts());
  if (res.status === 401) {
    showPassphrasePrompt('Session expirée. Reconnectez-vous.');
    throw new Error('Authentication required');
  }
  if (res.status === 429) {
    showPassphrasePrompt('Trop de tentatives. Réessayez plus tard.');
    throw new Error('Rate limited');
  }
  if (res.status === 403) {
    const detail = await parseErrorDetail(res);
    throw new Error(detail || res.status + ' ' + res.statusText);
  }
  if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
  return res.json();
}

export async function ownerLogin(passphrase) {
  const res = await fetch(BASE + '/api/auth/owner-login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Nexora-Action': 'owner-login',
      'Origin': window.location.origin,
    },
    credentials: 'same-origin',
    body: JSON.stringify({ passphrase: passphrase }),
  });
  if (!res.ok) {
    const detail = await parseErrorDetail(res);
    throw new Error(detail || 'Authentification échouée');
  }
  const data = await res.json();
  if (data.session_token) {
    sessionStorage.setItem('nexora_owner_session', data.session_token);
    sessionStorage.setItem('nexora_owner_tenant', data.tenant_id || '');
    sessionStorage.setItem('nexora_actor_role', 'owner');
  }
  return data;
}

export async function ownerLogout() {
  const ctx = sessionContext();
  if (ctx.sessionToken) {
    try {
      await fetch(BASE + '/api/auth/owner-logout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Nexora-Action': 'owner-logout',
          'X-Nexora-Session': ctx.sessionToken,
          'Origin': window.location.origin,
        },
        credentials: 'same-origin',
      });
    } catch (e) { /* best-effort */ }
  }
  sessionStorage.removeItem('nexora_owner_session');
  sessionStorage.removeItem('nexora_owner_tenant');
  sessionStorage.removeItem('nexora_actor_role');
}

export async function loadAccessContext() {
  return api('console/access-context');
}

export async function api(path) {
  const url = BASE + '/api/' + path;
  return requestWithAuth(url, function() {
    return { headers: buildHeaders(), credentials: 'same-origin' };
  });
}

export async function apiPost(path, body) {
  const url = BASE + '/api/' + path;
  return requestWithAuth(url, function() {
    const headers = buildHeaders();
    headers['Content-Type'] = 'application/json';
    headers['X-Nexora-Action'] = 'true';
    const opts = { method: 'POST', headers: headers, credentials: 'same-origin' };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return opts;
  });
}

export function isAuthenticated() {
  return !!(sessionStorage.getItem('nexora_owner_session') || '').trim();
}

export function showPassphrasePrompt(msg, onLoginSuccess) {
  const existing = document.getElementById('nx-owner-login-overlay');
  if (existing) existing.remove();

  const div = document.createElement('div');
  div.id = 'nx-owner-login-overlay';
  div.className = 'nx-token-overlay';
  div.setAttribute('role', 'dialog');
  div.setAttribute('aria-modal', 'true');
  div.setAttribute('aria-labelledby', 'owner-login-title');
  div.innerHTML = '<div class="nx-token-dialog">' +
    '<h3 id="owner-login-title" style="color:#7c3aed">🔐 Nexora Owner</h3>' +
    '<p class="nx-helper">' + (msg || 'Entrez votre passphrase propriétaire pour accéder à la console SaaS.') + '</p>' +
    '<form id="nx-owner-login-form">' +
    '<label for="owner-passphrase-input" class="nx-label">Passphrase</label>' +
    '<input id="owner-passphrase-input" class="nx-input nx-w-full nx-mb-md" placeholder="Votre passphrase secrète" type="password" autocomplete="off"/>' +
    '<button class="nx-btn nx-w-full" id="owner-login-btn" type="submit" ' +
    'style="background:linear-gradient(90deg,#7c3aed,#a78bfa)">Connexion Owner</button>' +
    '<p id="owner-login-error" style="color:#dc2626;font-size:0.85rem;margin-top:0.5rem;display:none"></p>' +
    '</form>' +
    '</div>';

  document.body.appendChild(div);
  const input = document.getElementById('owner-passphrase-input');
  const errorEl = document.getElementById('owner-login-error');
  input.focus();

  document.getElementById('nx-owner-login-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    const passphrase = input.value.trim();
    if (!passphrase) return;

    const btn = document.getElementById('owner-login-btn');
    btn.disabled = true;
    btn.textContent = 'Connexion…';
    errorEl.style.display = 'none';

    try {
      await ownerLogin(passphrase);
      div.remove();
      if (onLoginSuccess) {
        onLoginSuccess();
      } else {
        window.location.reload();
      }
    } catch (err) {
      errorEl.textContent = err.message || 'Erreur d\'authentification';
      errorEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Connexion Owner';
    }
  });
}
