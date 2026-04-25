const statusBadge = document.getElementById('statusBadge');
const queryForm = document.getElementById('queryForm');
const queryInput = document.getElementById('queryInput');
const demoBtn = document.getElementById('demoBtn');
const summaryTitle = document.getElementById('summaryTitle');
const summaryText = document.getElementById('summaryText');
const angleText = document.getElementById('angleText');
const tasksList = document.getElementById('tasksList');
const risksList = document.getElementById('risksList');
const questionsList = document.getElementById('questionsList');
const sources = document.getElementById('sources');

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

function render(data) {
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

queryForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;
  await callApi(`/api/scout?query=${encodeURIComponent(query)}`);
});

demoBtn.addEventListener('click', async () => {
  await callApi('/api/demo');
});

(async () => {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    setStatus(data.hasOpenAI && data.hasGoogle ? 'Keys loaded' : 'Keys missing', !(data.hasOpenAI && data.hasGoogle));
  } catch {
    setStatus('Backend unavailable', true);
  }
})();
