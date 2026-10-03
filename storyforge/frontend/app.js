// StoryForge frontend — no build step, no framework, just fetch + DOM.

const desk = document.getElementById('desk');
let currentProject = null;
let imagePollTimer = null;

// -------------------------------------------------------------------
// API helpers
// -------------------------------------------------------------------
async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) { /* ignore */ }
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  const contentType = resp.headers.get('content-type') || '';
  return contentType.includes('application/json') ? resp.json() : resp.text();
}

// -------------------------------------------------------------------
// Health check + sidebar shelf
// -------------------------------------------------------------------
async function refreshHealth() {
  try {
    const h = await api('/api/health');
    setStatus('llm', h.llm.ok, h.llm.message);
    setStatus('image', h.image.ok, h.image.message);
  } catch (e) {
    setStatus('llm', false, 'Health check failed.');
    setStatus('image', false, 'Health check failed.');
  }
}

function setStatus(kind, ok, message) {
  document.getElementById(`dot-${kind}`).className = 'dot ' + (ok ? 'ok' : 'bad');
  document.getElementById(`text-${kind}`).textContent = message;
  document.getElementById(`text-${kind}`).title = message;
}

async function refreshShelf(activeId) {
  const list = document.getElementById('shelf-list');
  const empty = document.getElementById('shelf-empty');
  const projects = await api('/api/projects');
  list.innerHTML = '';
  empty.classList.toggle('hidden', projects.length > 0);

  for (const p of projects) {
    const li = document.createElement('li');
    li.className = 'shelf-item' + (p.id === activeId ? ' active' : '');
    li.innerHTML = `${escapeHtml(p.title || 'Untitled')}<span class="shelf-item-sub">${p.num_scenes} scenes · ${escapeHtml(p.art_style || '')}</span>`;
    li.addEventListener('click', () => openProject(p.id));
    list.appendChild(li);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

// -------------------------------------------------------------------
// View: new story
// -------------------------------------------------------------------
function showNewStoryView() {
  stopImagePolling();
  currentProject = null;
  const tpl = document.getElementById('tpl-view-new');
  desk.innerHTML = '';
  desk.appendChild(tpl.content.cloneNode(true));
  refreshShelf(null);

  const form = document.getElementById('form-new-story');
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    const params = {
      idea: fd.get('idea').trim(),
      genre: fd.get('genre'),
      target_age: fd.get('target_age'),
      art_style: fd.get('art_style'),
      num_scenes: parseInt(fd.get('num_scenes'), 10) || 6,
    };

    const btn = document.getElementById('btn-generate-story');
    const progress = document.getElementById('story-progress');
    const errorBlock = document.getElementById('story-error');
    btn.disabled = true;
    progress.classList.remove('hidden');
    errorBlock.classList.add('hidden');

    try {
      const project = await api('/api/projects', { method: 'POST', body: JSON.stringify(params) });
      await openProject(project.id);
    } catch (e) {
      errorBlock.textContent = e.message || 'Something went wrong generating the story.';
      errorBlock.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      progress.classList.add('hidden');
    }
  });
}

// -------------------------------------------------------------------
// View: storybook
// -------------------------------------------------------------------
async function openProject(projectId) {
  stopImagePolling();
  const project = await api(`/api/projects/${projectId}`);
  currentProject = project;
  renderBookView(project);
  refreshShelf(projectId);

  const anyPending = project.scenes.some((s) => s.image_status === 'running');
  if (anyPending) startImagePolling(projectId);
}

function renderBookView(project) {
  const tpl = document.getElementById('tpl-view-book');
  desk.innerHTML = '';
  desk.appendChild(tpl.content.cloneNode(true));

  document.getElementById('book-genre').textContent =
    `${project.params.genre} · ${project.params.target_age} · ${project.params.art_style}`;
  document.getElementById('book-title').textContent = project.title;
  document.getElementById('book-synopsis').textContent = project.synopsis;
  document.getElementById('btn-download').href = `/api/projects/${project.id}/storybook/download`;

  const cast = document.getElementById('book-cast');
  cast.innerHTML = '';
  for (const c of project.characters) {
    const chip = document.createElement('span');
    chip.className = 'cast-chip';
    chip.innerHTML = `<b>${escapeHtml(c.name)}</b>${c.role ? ' · ' + escapeHtml(c.role) : ''}`;
    chip.title = c.visual_tags || c.description || '';
    cast.appendChild(chip);
  }

  const pagesEl = document.getElementById('book-pages');
  pagesEl.innerHTML = '';
  const scenes = [...project.scenes].sort((a, b) => a.index - b.index);
  for (const scene of scenes) {
    pagesEl.appendChild(renderScenePage(project, scene, scenes.length));
  }

  // bust the browser image cache after a regeneration so repainted scenes
  // don't show the old picture
  pagesEl.dataset.cacheBust = Date.now().toString();

  document.getElementById('btn-illustrate-all').addEventListener('click', () => illustrateAll(project.id));
}

function renderScenePage(project, scene, total) {
  const tpl = document.getElementById('tpl-scene-page');
  const node = tpl.content.cloneNode(true);
  const article = node.querySelector('.page');
  article.dataset.sceneId = scene.id;

  node.querySelector('.page-num').textContent = `Scene ${scene.index + 1} of ${total}`;
  node.querySelector('.page-mood').textContent = scene.mood || '';
  node.querySelector('.page-title').textContent = scene.title;
  node.querySelector('.page-text').textContent = scene.text;

  applySceneArtState(node, scene, project.id);

  node.querySelector('.btn-illustrate').addEventListener('click', () => illustrateScene(project.id, scene.id));
  node.querySelector('.btn-redo-image').addEventListener('click', () => illustrateScene(project.id, scene.id));

  const editBlock = node.querySelector('.page-edit');
  node.querySelector('.btn-edit-text').addEventListener('click', () => editBlock.classList.toggle('hidden'));
  node.querySelector('.btn-edit-cancel').addEventListener('click', () => editBlock.classList.add('hidden'));
  node.querySelector('.btn-edit-submit').addEventListener('click', async (ev) => {
    const button = ev.currentTarget;
    const direction = node.querySelector('.edit-direction').value.trim();
    button.disabled = true;
    button.textContent = 'Rewriting…';
    try {
      const updated = await api(
        `/api/projects/${project.id}/scenes/${scene.id}/regenerate-text`,
        { method: 'POST', body: JSON.stringify({ direction }) }
      );
      currentProject = updated;
      renderBookView(updated);
    } catch (e) {
      alert('Could not rewrite this scene: ' + e.message);
    } finally {
      button.disabled = false;
      button.textContent = 'Rewrite scene';
    }
  });

  return node;
}

function applySceneArtState(node, scene, projectId) {
  const img = node.querySelector('.page-img');
  const empty = node.querySelector('.page-art-empty');
  const loading = node.querySelector('.page-art-loading');
  const errorEl = node.querySelector('.page-art-error');
  img.classList.add('hidden');
  empty.classList.add('hidden');
  loading.classList.add('hidden');
  errorEl.classList.add('hidden');

  if (scene.image_status === 'running') {
    loading.classList.remove('hidden');
  } else if (scene.image_status === 'done' && scene.image_path) {
    const filename = scene.image_path.split('/').pop();
    img.src = `/api/projects/${projectId}/images/${filename}?t=${Date.now()}`;
    img.alt = scene.title || '';
    img.classList.remove('hidden');
  } else if (scene.image_status === 'error') {
    errorEl.textContent = scene.image_error || 'Illustration failed. Try again.';
    errorEl.classList.remove('hidden');
  } else {
    empty.classList.remove('hidden');
  }
}

// -------------------------------------------------------------------
// Image generation actions
// -------------------------------------------------------------------
async function illustrateScene(projectId, sceneId) {
  const article = document.querySelector(`.page[data-scene-id="${sceneId}"]`);
  if (article) {
    article.querySelector('.page-art-empty').classList.add('hidden');
    article.querySelector('.page-art-error').classList.add('hidden');
    article.querySelector('.page-img').classList.add('hidden');
    article.querySelector('.page-art-loading').classList.remove('hidden');
  }
  try {
    const updated = await api(`/api/projects/${projectId}/scenes/${sceneId}/regenerate-image`, { method: 'POST', body: JSON.stringify({}) });
    currentProject = updated;
    renderBookView(updated);
  } catch (e) {
    if (article) {
      article.querySelector('.page-art-loading').classList.add('hidden');
      const errorEl = article.querySelector('.page-art-error');
      errorEl.textContent = e.message;
      errorEl.classList.remove('hidden');
    }
  }
}

async function illustrateAll(projectId) {
  await api(`/api/projects/${projectId}/images`, { method: 'POST' });
  document.getElementById('image-progress').classList.remove('hidden');
  startImagePolling(projectId);
}

function startImagePolling(projectId) {
  stopImagePolling();
  imagePollTimer = setInterval(async () => {
    try {
      const progress = await api(`/api/projects/${projectId}/images/progress`);
      const bar = document.getElementById('image-progress-fill');
      const text = document.getElementById('image-progress-text');
      const block = document.getElementById('image-progress');
      if (block) {
        block.classList.remove('hidden');
        const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0;
        if (bar) bar.style.width = pct + '%';
        if (text) text.textContent = progress.message || '';
      }
      if (progress.state === 'done' || progress.state === 'done_with_errors' || progress.state === 'idle') {
        if (progress.total > 0) {
          const updated = await api(`/api/projects/${projectId}`);
          currentProject = updated;
          renderBookView(updated);
        }
        stopImagePolling();
      }
    } catch (e) {
      stopImagePolling();
    }
  }, 1500);
}

function stopImagePolling() {
  if (imagePollTimer) {
    clearInterval(imagePollTimer);
    imagePollTimer = null;
  }
}

// -------------------------------------------------------------------
// Boot
// -------------------------------------------------------------------
document.getElementById('btn-new-story').addEventListener('click', showNewStoryView);
refreshHealth();
setInterval(refreshHealth, 20000);
showNewStoryView();
