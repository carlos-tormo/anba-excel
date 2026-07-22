async function api(path, opts = {}) {
  const method = String(opts.method || 'GET').toUpperCase();
  return window.AnbaApi.request(path, opts, {
    dedupe: method !== 'GET',
    unauthorizedMessage: method === 'POST' ? 'Invalid admin credentials.' : null,
  });
}

function getErrorMessageFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('error');
  if (!code) return '';

  const map = {
    google_not_configured: 'Google login is not configured yet.',
    google_auth_denied: 'Google login was denied.',
    google_state_invalid: 'Google login state check failed. Try again.',
    google_token_failed: 'Google token exchange failed.',
    google_exchange_failed: 'Could not reach Google auth services.',
    google_profile_invalid: 'Google profile did not include a valid email.',
  };

  return map[code] || 'Authentication failed.';
}

function authLandingPath(status) {
  if (status.role === 'admin') return '/admin';
  if (status.role === 'gm' && status.team_code) return `/?team=${encodeURIComponent(status.team_code)}`;
  return '/';
}

function waitingListTokenFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const token = String(params.get('waiting_list_token') || '').trim();
  return /^[A-Za-z0-9_-]{20,160}$/.test(token) ? token : '';
}

async function init() {
  const status = await api('/api/auth/status');
  if (status.authenticated) {
    window.location.href = authLandingPath(status);
    return;
  }

  const form = document.getElementById('loginForm');
  const errorEl = document.getElementById('loginError');
  const googleHelp = document.getElementById('googleHelp');
  const googleBtn = document.getElementById('googleLoginBtn');
  const waitingListToken = waitingListTokenFromQuery();
  if (waitingListToken && googleBtn) {
    googleBtn.href = `/api/auth/google/start?waiting_list_token=${encodeURIComponent(waitingListToken)}`;
  }

  if (!status.google_enabled) {
    googleHelp.hidden = false;
    if (googleBtn) {
      googleBtn.setAttribute('aria-disabled', 'true');
      googleBtn.href = '#';
    }
  }

  const queryErr = getErrorMessageFromQuery();
  if (queryErr) {
    errorEl.textContent = queryErr;
    errorEl.hidden = false;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.hidden = true;

    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;

    try {
      await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      window.location.href = '/admin';
    } catch (err) {
      errorEl.textContent = err.message || 'Login failed.';
      errorEl.hidden = false;
    }
  });
}

init().catch(() => {
  const errorEl = document.getElementById('loginError');
  errorEl.textContent = 'Unable to connect to server.';
  errorEl.hidden = false;
});
