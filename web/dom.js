(function initAnbaDom(global) {
  const SAFE_URL_PROTOCOLS = new Set(['http:', 'https:']);

  function clear(node) {
    if (node) node.replaceChildren();
  }

  function text(tagName, value, className = '') {
    const node = document.createElement(tagName);
    if (className) node.className = className;
    node.textContent = value || '';
    return node;
  }

  function appendText(parent, value) {
    if (!parent) return null;
    const node = document.createTextNode(value == null ? '' : String(value));
    parent.appendChild(node);
    return node;
  }

  function appendElement(parent, tagName, options = {}) {
    if (!parent) return null;
    const node = document.createElement(String(tagName || 'div'));
    const {
      text: textValue,
      className,
      attrs,
      dataset,
      children,
    } = options || {};
    if (className) node.className = String(className);
    if (attrs && typeof attrs === 'object') {
      Object.entries(attrs).forEach(([key, value]) => {
        if (value === null || value === undefined || value === false) return;
        if ((key === 'href' || key === 'src') && !safeUrl(value)) return;
        node.setAttribute(key, value === true ? '' : String(value));
      });
    }
    if (dataset && typeof dataset === 'object') {
      Object.entries(dataset).forEach(([key, value]) => {
        if (value !== null && value !== undefined) node.dataset[key] = String(value);
      });
    }
    if (textValue !== undefined) node.textContent = textValue == null ? '' : String(textValue);
    if (Array.isArray(children)) {
      children.forEach((child) => {
        if (child instanceof Node) node.appendChild(child);
      });
    }
    parent.appendChild(node);
    return node;
  }

  function emptyMessage(message, className = 'news-empty') {
    return text('div', message, className);
  }

  function safeUrl(value, options = {}) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const allowRelative = options.allowRelative !== false;
    const allowedProtocols = new Set(options.protocols || SAFE_URL_PROTOCOLS);
    try {
      const parsed = new URL(raw, global.location?.origin || 'https://anba.local');
      const isRelative = !/^[a-z][a-z0-9+.-]*:/i.test(raw);
      if (isRelative && allowRelative) return `${parsed.pathname}${parsed.search}${parsed.hash}`;
      return allowedProtocols.has(parsed.protocol) ? parsed.href : '';
    } catch {
      return '';
    }
  }

  function setSafeImageSource(image, value, fallback = '') {
    if (!image) return false;
    const safe = safeUrl(value, { allowRelative: true });
    if (safe) {
      image.src = safe;
      return true;
    }
    if (fallback) image.src = safeUrl(fallback, { allowRelative: true }) || '';
    return false;
  }

  function setUnsafeHtml(parent, html) {
    if (parent) parent.innerHTML = String(html || '');
  }

  function appendUnsafeHtml(parent, position, html) {
    if (parent) parent.insertAdjacentHTML(position, String(html || ''));
  }

  global.AnbaDom = {
    appendElement,
    appendText,
    appendUnsafeHtml,
    clear,
    emptyMessage,
    safeUrl,
    setSafeImageSource,
    setUnsafeHtml,
    text,
  };
})(window);
