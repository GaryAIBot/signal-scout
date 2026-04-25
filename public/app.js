const statusBadge = document.getElementById('statusBadge');
const queryForm = document.getElementById('queryForm');
const queryInput = document.getElementById('queryInput');
const demoBtn = document.getElementById('demoBtn');
const saveBtn = document.getElementById('saveBtn');
const refreshSavedBtn = document.getElementById('refreshSavedBtn');
const summaryTitle = document.getElementById('summaryTitle');
const summaryText = document.getElementById('summaryText');
const angleText = document.getElementById('angleText');
const tasksList = document.getElementById('tasksList');
const risksList = document.getElementById('risksList');
const questionsList = document.getElementById('questionsList');
const sources = document.getElementById('sources');
const savedStatus = document.getElementById('savedStatus');
const savedList = document.getElementById('savedList');

let currentResult = null;

function setStatus(text, bad = false) {
  statusBadge.textContent = text;
  statusBadge.classList.toggle('bad', bad);
}

function renderList(el, items, empty) {
  el.innerHTML = '';
  if (!items || !items.length) {
    const li = document.createElement('li');
    li.textContent = empty;
    li.className = 'muted';
    el.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement('li');
    li.textContent = item;
    el.appendChild(li);
  }
}

function renderSources(items) {
  sources.innerHTML = '';
  if (!items || !items.length) {
    sources.innerHTML = '<p class="muted">No sources yet.</p>';
    return;
  }
  for (const item of items) {
    const a = document.createElement('a');
    a.href = item.url;
    a.target = '_blank';
    a.rel = 'noreferrer';
    a.className = 'source';
    a.innerHTML = `<strong>${item.title || item.url}</strong><span>${item.url}</span>`;
    sources.appendChild(a);
  }
}

function renderSaved(items) {
  savedList.innerHTML = '';
  if (!items || !items.length) {
    savedStatus.textContent = 'No saved scouts yet. Run one, then save it.';
    return;
  }
  savedStatus.textContent = `${items.length} saved scout${items.length === 1 ? '' : 's'} in Neon.`;
  for (const item of items) {
    const card = document.createElement('article');
    card.className = 'saved-card';
    card.innerHTML = `
      <div class="saved-meta">
        <strong>${item.title}</strong>
        <span>${item.createdAt ? new Date(item.createdAt).toLocaleString() : ''}</span>
      </div>
      <p class="muted"><strong>Query:</strong> ${item.query}</p>
      <p>${item.summary}</p>
      <p class="muted"><strong>Angle:</strong> ${item.angle}</p>
    `;
    savedList.appendChild(card);
  }
}

function render(data) {
  currentResult = data;
  summaryTitle.textContent = data.query;
  summaryText.textContent = data.brief?.summary || data.search?.summary || 'No summary returned.';
  angleText.textContent = data.brief?.angle || 'No angle returned.';
  renderList(tasksList, data.brief?.tasks, 'No tasks returned.');
  renderList(risksList, data.brief?.risks, 'No risks returned.');
  renderList(questionsList, data.brief?.questions, 'No questions returned.');
  renderSources(data.search?.sources || []);
}

async function callApi(url) {
  setStatus('Running...');
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Request failed');
    render(data);
    setStatus('Ready');
  } catch (error) {
    setStatus('Failed', true);
    summaryTitle.textContent = 'Request failed';
    summaryText.textContent = error.message;
    angleText.textContent = 'Check env vars and API responses.';
    renderList(tasksList, [], 'No tasks returned.');
    renderList(risksList, [], 'No risks returned.');
    renderList(questionsList, [], 'No questions returned.');
    renderSources([]);
  }
}

async function loadSaved() {
  savedStatus.textContent = 'Loading saved scouts…';
  try {
    const res = await fetch('/api/saved-scouts');
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Failed to load saved scouts');
    renderSaved(data.items || []);
  } catch (error) {
    savedStatus.textContent = error.message;
    savedList.innerHTML = '';
  }
}

async function saveCurrent() {
  if (!currentResult?.brief?.summary || !currentResult?.brief?.angle) {
    savedStatus.textContent = 'Run or load a scout result first.';
    return;
  }
  savedStatus.textContent = 'Saving current result…';
  try {
    const res = await fetch('/api/saved-scouts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: currentResult.query,
        query: currentResult.query,
        summary: currentResult.brief.summary,
        angle: currentResult.brief.angle,
      })
    });
    const data = await res.json();
    if (!res.ok || data.ok === false) throw new Error(data.detail || 'Failed to save result');
    savedStatus.textContent = 'Saved to Neon.';
    await loadSaved();
  } catch (error) {
    savedStatus.textContent = error.message;
  }
}

queryForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;
  await callApi(`/api/scout?query=${encodeURIComponent(query)}`);
});

demoBtn.addEventListener('click', async () => {
  await callApi('/api/demo');
});

saveBtn.addEventListener('click', async () => {
  await saveCurrent();
});

refreshSavedBtn.addEventListener('click', async () => {
  await loadSaved();
});

(async () => {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    const good = data.hasOpenAI && data.hasGoogle && data.hasDatabase;
    setStatus(good ? 'Keys + DB loaded' : 'Setup incomplete', !good);
  } catch {
    setStatus('Backend unavailable', true);
  }
  await loadSaved();
})();
