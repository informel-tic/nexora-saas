export const BASE = window.location.pathname.replace(/\/console\/?.*$/, '');

export function initToken() {
  const legacy = localStorage.getItem('nexora_token');
  if (legacy && !sessionStorage.getItem('nexora_token')) {
    sessionStorage.setItem('nexora_token', legacy);
  }
  localStorage.removeItem('nexora_token');
}

export async function api(path) {
  const url = `${BASE}/api/${path}`;
  const token = sessionStorage.getItem('nexora_token') || '';
  const headers = { Accept: 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { headers, credentials: 'same-origin' });
  if (res.status === 401) { showTokenPrompt(); throw new Error('Authentication required'); }
  if (res.status === 429) { showTokenPrompt('Trop de tentatives. Réessayez plus tard.'); throw new Error('Rate limited'); }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function apiPost(path, body) {
  const url = `${BASE}/api/${path}`;
  const token = sessionStorage.getItem('nexora_token') || '';
  const headers = { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Nexora-Action': 'true', 'X-Nexora-Token': token };
  const opts = { method: 'POST', headers };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
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
  div.innerHTML = `<div class="nx-token-dialog">
    <h3 id="token-prompt-title">Authentification requise</h3>
    <p class="nx-helper">${msg || 'Entrez le token API Nexora.'}</p>
    <label for="token-input" class="nx-label">Token API</label>
    <input id="token-input" class="nx-input nx-w-full nx-mb-md" placeholder="Token API" type="password" autocomplete="off"/>
    <button class="nx-btn nx-w-full" id="token-submit-btn">Connexion</button>
  </div>`;
  document.body.appendChild(div);
  const input = document.getElementById('token-input');
  input.focus();
  const submit = function() {
    const val = input.value.trim();
    if (val) {
      sessionStorage.setItem('nexora_token', val);
      div.remove();
      if (onLoginSuccess) onLoginSuccess();
    }
  };
  document.getElementById('token-submit-btn').addEventListener('click', submit);
  input.addEventListener('keydown', function(e) { if (e.key === 'Enter') submit(); });
}
