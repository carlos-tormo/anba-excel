(function initAnbaApi(global) {
  const WRITE_METHODS = new Set(['POST', 'PATCH', 'DELETE']);
  const inFlightRequestKeys = new Set();

  class ApiError extends Error {
    constructor(message, response, data = null) {
      super(message);
      this.name = 'ApiError';
      this.status = response?.status || 0;
      this.data = data;
      this.error = data && typeof data === 'object' ? data.error : '';
      this.validationErrors = data && typeof data === 'object' ? (data.errors || data.fields || null) : null;
      this.conflict = this.status === 409;
      this.unauthorized = this.status === 401;
      this.forbidden = this.status === 403;
    }
  }

  async function retryMessage(response) {
    const data = await response.json().catch(() => ({}));
    const retry = Number(data.retry_after_seconds || 0);
    if (retry > 0) return `Too many attempts. Try again in ${retry}s.`;
    return 'Too many attempts. Try again later.';
  }

  async function responseData(response) {
    return response.clone().json().catch(() => null);
  }

  async function defaultErrorMessage(response, method, options, data = null) {
    if (response.status === 429) return retryMessage(response);
    if (response.status === 401 && typeof options.onUnauthorized === 'function') {
      options.onUnauthorized(response);
      return options.unauthorizedMessage || 'Unauthorized';
    }
    if (response.status === 401 && options.unauthorizedMessage) {
      return typeof options.unauthorizedMessage === 'function'
        ? options.unauthorizedMessage(method, response)
        : options.unauthorizedMessage;
    }
    if (response.status === 403 && options.forbiddenMessage) return options.forbiddenMessage;
    if (response.status === 403 && typeof options.onForbidden === 'function') {
      options.onForbidden(response, data);
    }
    if (response.status === 409 && typeof options.onConflict === 'function') {
      options.onConflict(response, data);
    }
    if (response.status === 409 && options.conflictMessage) return options.conflictMessage;
    if (response.status === 400 && typeof options.onValidationError === 'function') {
      options.onValidationError(response, data);
    }
    if (response.status === 400 && options.validationMessage) return options.validationMessage;
    if (data && typeof data === 'object' && data.error) {
      return String(data.error);
    }
    const text = await response.text();
    return `API ${response.status}: ${text}`;
  }

  function requestKeyFor(path, opts = {}, options = {}) {
    if (options.requestKey) return String(options.requestKey);
    if (!options.dedupe) return '';
    const method = String(opts.method || 'GET').toUpperCase();
    return `${method} ${String(path || '')}`;
  }

  function bodyForJson(payload) {
    return JSON.stringify(payload == null ? {} : payload);
  }

  async function request(path, opts = {}, options = {}) {
    const method = String(opts.method || 'GET').toUpperCase();
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const csrfToken = typeof options.getCsrfToken === 'function' ? options.getCsrfToken() : null;
    if (WRITE_METHODS.has(method) && csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
    const requestKey = requestKeyFor(path, opts, options);
    if (requestKey && inFlightRequestKeys.has(requestKey)) {
      throw new ApiError('Request already in progress.', { status: 409 }, { error: 'duplicate_request' });
    }
    if (requestKey) inFlightRequestKeys.add(requestKey);
    try {
      const response = await fetch(path, {
        ...opts,
        headers,
        signal: opts.signal || options.signal,
      });
      const data = await responseData(response);
      if (!response.ok) {
        throw new ApiError(await defaultErrorMessage(response, method, options, data), response, data);
      }
      if (data && typeof data === 'object' && data.csrf_token && typeof options.setCsrfToken === 'function') {
        options.setCsrfToken(data.csrf_token);
      }
      return data;
    } finally {
      if (requestKey) inFlightRequestKeys.delete(requestKey);
    }
  }

  async function upload(path, formData, opts = {}, options = {}) {
    const method = String(opts.method || 'POST').toUpperCase();
    const headers = { ...(opts.headers || {}) };
    const csrfToken = typeof options.getCsrfToken === 'function' ? options.getCsrfToken() : null;
    if (WRITE_METHODS.has(method) && csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
    const requestKey = requestKeyFor(path, { ...opts, method }, options);
    if (requestKey && inFlightRequestKeys.has(requestKey)) {
      throw new ApiError('Request already in progress.', { status: 409 }, { error: 'duplicate_request' });
    }
    if (requestKey) inFlightRequestKeys.add(requestKey);
    try {
      const response = await fetch(path, {
        ...opts,
        method,
        headers,
        body: formData,
        signal: opts.signal || options.signal,
      });
      const data = await responseData(response);
      if (!response.ok) {
        throw new ApiError(await defaultErrorMessage(response, method, options, data), response, data);
      }
      return data;
    } finally {
      if (requestKey) inFlightRequestKeys.delete(requestKey);
    }
  }

  async function withSubmissionLock(button, task, options = {}) {
    if (button && button.disabled && options.skipIfDisabled !== false) return null;
    const oldText = button?.textContent || '';
    if (button) {
      button.disabled = true;
      if (options.pendingText) button.textContent = options.pendingText;
    }
    try {
      return await task();
    } finally {
      if (button && options.restore !== false) {
        button.disabled = false;
        if (options.pendingText) button.textContent = oldText;
      }
    }
  }

  global.AnbaApi = {
    ApiError,
    bodyForJson,
    request,
    upload,
    withSubmissionLock,
  };
})(window);
