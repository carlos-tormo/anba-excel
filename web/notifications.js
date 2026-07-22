(function initAnbaNotifications(global) {
  function renderGmNotifications({ panel, notifications, markRead, safeCssToken }) {
    if (!panel) return;
    const rows = Array.isArray(notifications) ? notifications : [];
    panel.classList.toggle('section-hidden', !rows.length);
    global.AnbaDom.clear(panel);
    if (!rows.length) return;

    const head = document.createElement('div');
    head.className = 'gm-notifications-head';
    head.append(
      global.AnbaDom.text('strong', 'Notificaciones'),
      global.AnbaDom.text('span', `${rows.length} pendiente${rows.length === 1 ? '' : 's'}`),
    );

    const list = document.createElement('div');
    list.className = 'gm-notifications-list';
    rows.forEach((notification) => {
      const card = document.createElement('article');
      const kind = safeCssToken(notification?.kind || 'info', 'info');
      card.className = `gm-notification-card gm-notification-card--${kind}`;

      const copy = document.createElement('div');
      copy.className = 'gm-notification-copy';
      copy.appendChild(global.AnbaDom.text('strong', String(notification?.title || 'Notificación')));
      const body = String(notification?.body || '').trim();
      if (body) copy.appendChild(global.AnbaDom.text('p', body));

      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Cerrar';
      button.addEventListener('click', async () => {
        const id = Number(notification?.id);
        if (!Number.isFinite(id)) return;
        button.disabled = true;
        try {
          await markRead(id);
        } catch (err) {
          console.error(err);
          button.disabled = false;
        }
      });

      card.append(copy, button);
      list.appendChild(card);
    });

    panel.append(head, list);
  }

  function restartPolling(currentTimer, { canView, load, onError, intervalMs = 45000 }) {
    if (currentTimer) clearInterval(currentTimer);
    if (!canView()) return null;
    return setInterval(() => {
      if (document.hidden) return;
      load().catch(onError);
    }, intervalMs);
  }

  global.AnbaNotifications = {
    renderGmNotifications,
    restartPolling,
  };
})(window);
