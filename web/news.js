const articleEl = document.getElementById('newsArticle');
const feedEl = document.getElementById('newsFeedList');

async function fetchJson(url) {
  const response = await fetch(url, { credentials: 'same-origin' });
  if (!response.ok) {
    let detail = '';
    try {
      detail = JSON.stringify(await response.json());
    } catch {
      detail = await response.text();
    }
    throw new Error(`API ${response.status}: ${detail}`);
  }
  return response.json();
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function setText(parent, selector, value) {
  const node = parent.querySelector(selector);
  if (node) node.textContent = value || '';
}

function renderArticle(article) {
  if (!articleEl) return;
  if (!article) {
    articleEl.innerHTML = '<div class="news-empty">No se encontró el artículo.</div>';
    return;
  }
  articleEl.innerHTML = '';

  if (article.image_url) {
    const image = document.createElement('img');
    image.className = 'news-hero-image';
    image.src = article.image_url;
    image.alt = '';
    articleEl.appendChild(image);
  }

  const body = document.createElement('div');
  body.className = 'news-article-body';

  const date = document.createElement('div');
  date.className = 'news-date';
  date.textContent = formatDate(article.created_at);

  const title = document.createElement('h2');
  title.textContent = article.title || 'ANBA News';

  const text = document.createElement('div');
  text.className = 'news-full-text';
  text.textContent = article.body || '';

  body.append(date, title, text);
  articleEl.appendChild(body);
}

function renderFeed(articles, selectedId) {
  if (!feedEl) return;
  if (!articles.length) {
    feedEl.innerHTML = '<div class="news-empty">Todavía no hay artículos.</div>';
    return;
  }
  feedEl.innerHTML = '';
  articles.forEach((article) => {
    const link = document.createElement('a');
    link.href = `/news?article=${encodeURIComponent(article.id)}`;
    link.className = `news-feed-item${Number(article.id) === Number(selectedId) ? ' is-active' : ''}`;
    const title = document.createElement('strong');
    title.textContent = article.title || 'ANBA News';
    const meta = document.createElement('span');
    meta.textContent = formatDate(article.created_at);
    const excerpt = document.createElement('p');
    excerpt.textContent = article.excerpt || '';
    link.append(title, meta, excerpt);
    feedEl.appendChild(link);
  });
}

async function initNews() {
  const params = new URLSearchParams(window.location.search);
  let articleId = Number(params.get('article') || 0);
  const listResult = await fetchJson('/api/news/articles?limit=50');
  const articles = Array.isArray(listResult.articles) ? listResult.articles : [];
  if (!articleId && articles.length) articleId = Number(articles[0].id || 0);
  renderFeed(articles, articleId);
  if (!articleId) {
    renderArticle(null);
    return;
  }
  const articleResult = await fetchJson(`/api/news/articles/${encodeURIComponent(articleId)}`);
  renderArticle(articleResult.article);
}

initNews().catch((err) => {
  if (articleEl) {
    articleEl.innerHTML = '<div class="news-empty">No se pudo cargar la noticia.</div>';
  }
  console.error(err);
});
