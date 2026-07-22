const articleEl = document.getElementById('newsArticle');
const feedEl = document.getElementById('newsFeedList');

async function fetchJson(url) {
  return window.AnbaApi.request(url, { credentials: 'same-origin' });
}

function renderArticle(article) {
  if (!articleEl) return;
  if (!article) {
    window.AnbaDom.clear(articleEl);
    articleEl.appendChild(window.AnbaDom.emptyMessage('No se encontró el artículo.'));
    return;
  }
  window.AnbaDom.clear(articleEl);

  if (article.image_url) {
    const image = document.createElement('img');
    image.className = 'news-hero-image';
    image.alt = '';
    if (window.AnbaDom.setSafeImageSource(image, article.image_url)) {
      articleEl.appendChild(image);
    }
  }

  const body = document.createElement('div');
  body.className = 'news-article-body';

  const date = window.AnbaDom.text('div', window.AnbaFormatting.dateTimeEs(article.created_at), 'news-date');

  const title = window.AnbaDom.text('h2', article.title || 'ANBA News');

  const text = window.AnbaDom.text('div', article.body || '', 'news-full-text');

  body.append(date, title, text);
  articleEl.appendChild(body);
}

function renderFeed(articles, selectedId) {
  if (!feedEl) return;
  if (!articles.length) {
    window.AnbaDom.clear(feedEl);
    feedEl.appendChild(window.AnbaDom.emptyMessage('Todavía no hay artículos.'));
    return;
  }
  window.AnbaDom.clear(feedEl);
  articles.forEach((article) => {
    const link = document.createElement('a');
    link.href = window.AnbaDom.safeUrl(`/news?article=${encodeURIComponent(article.id)}`) || '/news';
    link.className = `news-feed-item${Number(article.id) === Number(selectedId) ? ' is-active' : ''}`;
    const title = window.AnbaDom.text('strong', article.title || 'ANBA News');
    const meta = window.AnbaDom.text('span', window.AnbaFormatting.dateTimeEs(article.created_at));
    const excerpt = window.AnbaDom.text('p', article.excerpt || '');
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
    window.AnbaDom.clear(articleEl);
    articleEl.appendChild(window.AnbaDom.emptyMessage('No se pudo cargar la noticia.'));
  }
  console.error(err);
});
