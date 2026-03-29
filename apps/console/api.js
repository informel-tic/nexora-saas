export const BASE = window.location.pathname.replace(/\/console\/?.*$/, '');

export function initToken() {
  const legacy = localStorage.getItem('nexora_token');
  if (legacy && !sessionStorage.getItem('nexora_token')) {
    sessionStorage.setItem('nexora_token', legacy);
  }
  localStorage.removeItem('nexora_token');
}

function authContext() {
  return {
    token: (sessionStorage.getItem('nexora_token') || '').trim(),
    tenantId: (sessionStorage.getItem('nexora_tenant_id') || '').trim(),
    actorRole: (sessionStorage.getItem('nexora_actor_role') || '').trim(),
    tenantClaim: (sessionStorage.getItem('nexora_tenant_claim') || '').trim()
  };
}

function buildHeaders() {
  const ctx = authContext();
  const headers = { Accept: 'application/json' };
  if (ctx.token) {
    headers.Authorization = `Bearer ${ctx.token}`;
    headers['X-Nexora-Token'] = ctx.token;
  }
  if (ctx.tenantId) headers['X-Nexora-Tenant-Id'] = ctx.tenantId;
  if (ctx.actorRole) headers['X-Nexora-Actor-Role'] = ctx.actorRole;
  if (ctx.tenantClaim) headers['X-Nexora-Tenant-Claim'] = ctx.tenantClaim;
  return headers;
}

async function parseErrorDetail(res) {
  try {
    const payload = await res.json();
    if (payload && payload.detail) return String(payload.detail);
  } catch (e) { /* noop */ }
  return '';
}

async function requestWithAuth(url, buildOpts, allowClaimRetry) {
  const res = await fetch(url, buildOpts());
  if (res.status === 401) { showTokenPrompt(); throw new Error('Authentication required'); }
  if (res.status === 429) { showTokenPrompt('Trop de tentatives. Reessayez plus tard.'); throw new Error('Rate limited'); }
  if (res.status === 403) {
    const detail = await parseErrorDetail(res);
    if (allowClaimRetry && detail.indexOf('X-Nexora-Tenant-Claim') >= 0) {
      await refreshTenantClaim();
      return requestWithAuth(url, buildOpts, false);
    }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function refreshTenantClaim() {
  const ctx = authContext();
  if (!ctx.token || !ctx.tenantId) {
    sessionStorage.removeItem('nexora_tenant_claim');
    return null;
  }

  const url = `${BASE}/api/auth/tenant-claim?tenant_id=${encodeURIComponent(ctx.tenantId)}`;
  const headers = {
    Accept: 'application/json',
    Authorization: `Bearer ${ctx.token}`,
    'X-Nexora-Token': ctx.token,
    'X-Nexora-Tenant-Id': ctx.tenantId
  };
  if (ctx.actorRole) headers['X-Nexora-Actor-Role'] = ctx.actorRole;

  const res = await fetch(url, { headers, credentials: 'same-origin' });
  if (!res.ok) {
    sessionStorage.removeItem('nexora_tenant_claim');
    return null;
  }
  const payload = await res.json();
  if (payload && payload.claim) {
    sessionStorage.setItem('nexora_tenant_claim', payload.claim);
    return payload.claim;
  }
  return null;
}

export async function loadAccessContext() {
  return api('console/access-context');
}

export async function api(path, init) {
  const url = `${BASE}/api/${path}`;
  return requestWithAuth(url, function() {
    const method = init && init.method ? String(init.method).toUpperCase() : 'GET';
    const headers = Object.assign({}, buildHeaders(), init && init.headers ? init.headers : {});
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' && !headers['X-Nexora-Action']) {
      headers['X-Nexora-Action'] = 'true';
    }
    const opts = { method: method, headers: headers, credentials: 'same-origin' };
    if (init && init.body !== undefined) {
      if (typeof init.body === 'string') {
        opts.body = init.body;
      } else {
        if (!headers['Content-Type']) headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(init.body);
      }
    }
    return opts;
  }, true);
}

export async function apiPost(path, body) {
  const url = `${BASE}/api/${path}`;
  return requestWithAuth(url, function() {
    const ctx = authContext();
    const headers = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Nexora-Action': 'true'
    };
    if (ctx.token) {
      headers.Authorization = `Bearer ${ctx.token}`;
      headers['X-Nexora-Token'] = ctx.token;
    }
    if (ctx.tenantId) headers['X-Nexora-Tenant-Id'] = ctx.tenantId;
    if (ctx.actorRole) headers['X-Nexora-Actor-Role'] = ctx.actorRole;
    if (ctx.tenantClaim) headers['X-Nexora-Tenant-Claim'] = ctx.tenantClaim;
    const opts = { method: 'POST', headers, credentials: 'same-origin' };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return opts;
  }, true);
}

export function showTokenPrompt(msg, onLoginSuccess) {
  const existing = document.getElementById('nx-token-overlay');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.id = 'nx-token-overlay';
  div.className = 'nx-token-overlay';
  div.setAttribute('role', 'dialog');
  div.setAttribute('aria-modal', 'true');
  div.setAttribute('aria-labelledby', 'token-prompt-title');
  const savedTenant = (sessionStorage.getItem('nexora_tenant_id') || '').trim();
  const savedRole = (sessionStorage.getItem('nexora_actor_role') || '').trim() || 'admin';
  div.innerHTML = `<div class="nx-token-dialog">
    <h3 id="token-prompt-title">Authentification requise</h3>
    <p class="nx-helper">${msg || 'Entrez vos paramètres de session SaaS (token, tenant, rôle).'} </p>
    <form id="nx-token-form">
    <label for="token-input" class="nx-label">Token API</label>
    <input id="token-input" class="nx-input nx-w-full nx-mb-md" placeholder="Token API" type="password" autocomplete="off"/>
    <label for="tenant-input" class="nx-label">Tenant ID (subscriber)</label>
    <input id="tenant-input" class="nx-input nx-w-full nx-mb-md" placeholder="tenant-a" value="${savedTenant}" autocomplete="off"/>
    <label for="role-input" class="nx-label">Profil d'accès</label>
    <select id="role-input" class="nx-input nx-w-full nx-mb-md" aria-label="Profil d'accès">
      <option value="admin">admin</option>
      <option value="operator">operator</option>
      <option value="architect">architect</option>
      <option value="subscriber">subscriber</option>
    </select>
    <button class="nx-btn nx-w-full" id="token-submit-btn" type="submit">Connexion</button>
    </form>
  </div>`;
  document.body.appendChild(div);
  const input = document.getElementById('token-input');
  const tenantInput = document.getElementById('tenant-input');
  const roleInput = document.getElementById('role-input');
  roleInput.value = savedRole;
  input.focus();

  const submit = async function() {
    const val = input.value.trim();
    const tenant = tenantInput.value.trim();
    const role = roleInput.value.trim();
    if (!val) return;

    sessionStorage.setItem('nexora_token', val);
    if (tenant) sessionStorage.setItem('nexora_tenant_id', tenant);
    else sessionStorage.removeItem('nexora_tenant_id');
    if (role) sessionStorage.setItem('nexora_actor_role', role);
    else sessionStorage.removeItem('nexora_actor_role');

    try { await refreshTenantClaim(); } catch (e) { /* noop */ }

    div.remove();
    if (onLoginSuccess) {
      onLoginSuccess();
    } else {
      // Auto-reload current section after login
      window.location.reload();
    }
  };
  document.getElementById('nx-token-form').addEventListener('submit', function(e) {
    e.preventDefault();
    void submit();
  });
}
