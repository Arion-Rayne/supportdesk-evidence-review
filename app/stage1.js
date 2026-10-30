const $ = id => document.getElementById(id);
const messages = {
  zh: {
    originalDraft: '原始模型草稿（保留不变）',
    humanEdit: '已保存人工修改 · 不代表审核通过',
    contextRange: '原文上下文行号：',
    title: '输入问题，找到依据，审核回复',
    uiLanguage: '界面语言',
    scope: '本地作品演示 · 仅模拟问题 · 固定官方资料 · 回复须人工审核，不自动发送或修改客户系统。',
    question: '客户的问题',
    retrieval: '检索方式',
    keyword: '关键词基线（免费）',
    vector: '向量检索',
    hybrid: '混合检索',
    search: '检索并保存',
    history: '打开已保存工单',
    reopen: '重新打开这条记录',
    run: '本次运行 / 过往运行',
    generateTitle: '生成回复草稿',
    fixedInput: '同一工单切换模型时，使用首次保存的问题和前三条依据，并补充经核验的同节原文上下文。旧模型输出保持不变；再次生成前请预览输入。',
    model: '模型配置',
    replyLanguage: '回复语言',
    preview: '预览模型输入（免费）',
    generate: '调用模型生成',
    inputPreview: '本次输入预览（不含密钥）',
    reviewTitle: '修改并保存人工审核',
    draft: '回复内容',
    decision: '审核决定',
    decisionDraft: '暂存草稿',
    approved: '人工审核通过',
    needsInfo: '需要补充信息',
    rejected: '拒绝使用',
    notes: '审核备注',
    save: '保存审核记录',
    working: '正在处理…',
    saved: '已从 PostgreSQL 重新读出记录。',
    evidence: '原文依据',
    source: '查看官方来源',
    noEvidence: '没有找到依据，须进一步核查；不生成无依据的回复。',
    manual: '未调用模型。你可以填写人工草稿。',
    modelDraft: '真实模型草稿 · 仍需人工审核',
    disabled: '真实调用关闭或本地未配置该服务商密钥。预览和人工保存仍可使用。',
    enabled: '真实调用已开启。点击生成会发送一次付费请求；无自动重试。',
    reviewSaved: '人工审核已保存并重新读回。原始模型输出保留在运行历史中。',
    vectorReady: '向量索引已就绪；新问题的向量化可能产生一次调用。',
    vectorMissing: '向量索引尚未就绪，请先使用关键词基线。',
    error: '请求未成功，请检查输入和后台服务。'
  },
  en: {
    contextRange: 'Source context lines: ',
    originalDraft: 'Original model draft (unedited)',
    humanEdit: 'Saved review edit · Original model draft retained',
    title: 'Find evidence, review a reply',
    uiLanguage: 'UI language',
    scope: 'Local portfolio demo · Synthetic questions only · Fixed official snapshots · Human review required. No replies are sent and no customer systems are changed.',
    question: 'Customer question',
    retrieval: 'Retrieval method',
    keyword: 'Keyword baseline (free)',
    vector: 'Vector search',
    hybrid: 'Hybrid search',
    search: 'Search and save',
    history: 'Open a saved ticket',
    reopen: 'Reopen this saved record',
    run: 'Current / previous run',
    generateTitle: 'Generate a reply draft',
    fixedInput: 'Switching models reuses the same original question and first three saved excerpts. Preview the input before generating.',
    model: 'Model profile',
    replyLanguage: 'Reply language',
    preview: 'Preview model input (free)',
    generate: 'Generate with model',
    inputPreview: 'Input preview (no credentials)',
    reviewTitle: 'Edit and save a human review',
    draft: 'Reply text',
    decision: 'Review decision',
    decisionDraft: 'Save as draft',
    approved: 'Approved by reviewer',
    needsInfo: 'Needs more information',
    rejected: 'Reject draft',
    notes: 'Review notes',
    save: 'Save review',
    working: 'Working…',
    saved: 'Record reloaded from PostgreSQL.',
    evidence: 'Original evidence',
    source: 'Open official source',
    noEvidence: 'No evidence found. Further investigation is required; an unsupported reply will not be generated.',
    manual: 'No model called. You can write a human draft.',
    modelDraft: 'Real model draft · Human review required',
    disabled: 'Calls are disabled or this provider has no local key. Preview and human review remain available.',
    enabled: 'Real calls enabled. Generate sends one paid request; no automatic retry.',
    reviewSaved: 'Review saved and read back. Original model output remains in run history.',
    vectorReady: 'Vector index ready; embedding a new question may incur one request.',
    vectorMissing: 'Vector index not ready. Use the keyword baseline first.',
    error: 'Request failed. Check the input and local backend.'
  }
};
Object.assign(messages.en, {
  brandSub: 'Review workspace',
  workspaceLabel: 'Workspace',
  navWorkspace: 'Workspace',
  navHistory: 'Saved tickets',
  navDemo: 'Example demo',
  localMode: 'Local workspace',
  sideNote: 'Built for thoughtful review.',
  breadcrumb: 'Workspace',
  breadcrumbReview: 'Evidence review',
  eyebrow: 'Evidence-first support',
  humanControl: 'Human review required',
  stepQuestion: 'Ask',
  stepEvidence: 'Find evidence',
  stepReview: 'Review',
  newQuestion: 'New support question',
  questionSubtitle: 'Start with a question and find the right sources.',
  syntheticLabel: 'SYNTHETIC CASE'
});
Object.assign(messages.zh, {
  brandSub: '审核工作台',
  workspaceLabel: '工作区',
  navWorkspace: '工作台',
  navHistory: '已保存工单',
  navDemo: '查看演示',
  localMode: '本地工作区',
  sideNote: '让每一次审核都有依据。',
  breadcrumb: '工作区',
  breadcrumbReview: '依据审核',
  eyebrow: '以依据为中心的客服工作台',
  humanControl: '需要人工审核',
  stepQuestion: '输入问题',
  stepEvidence: '查找依据',
  stepReview: '人工审核',
  newQuestion: '新建客服问题',
  questionSubtitle: '输入问题，查找相关资料。',
  syntheticLabel: '模拟工单'
});
let language = localStorage.getItem('supportdesk-ui-language') || 'en',
  record = null,
  selectedRun = null,
  profiles = [];
if (!messages[language]) language = 'en';
const t = key => messages[language][key] || key;

function text(parent, value, tag = 'p') {
  const node = document.createElement(tag);
  node.textContent = value;
  parent.append(node);
  return node;
}

function localizeReason(reason) {
  if (language !== 'zh') return reason || '';
  return ({
    'Keyword matches identify candidate evidence; they do not establish the root cause.': '关键词命中只表示候选依据；不能证明实际故障根因。',
    'No keyword evidence was found in the selected sources.': '限定资料中未找到关键词依据。',
    'Vector similarity identifies candidate evidence; it does not establish the root cause.': '向量相似度只表示候选相关性，不能证明实际故障根因。'
  })[reason] || reason || '';
}

function translate() {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(n => n.textContent = t(n.dataset.i18n));
  $('ui-language').value = language;
  updateModel();
  if (record) {
    const edits = [$('draft').value, $('decision').value, $('notes').value];
    renderRun();
    [$('draft').value, $('decision').value, $('notes').value] = edits;
  }
}
async function request(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    if (e instanceof TypeError) throw new Error(language === 'zh' ? '无法连接本地后台。请运行项目里的 START_SUPPORTDESK.cmd；启动成功后刷新页面。尚未保存的修改请先复制保留。' : 'Cannot reach the local backend. Run START_SUPPORTDESK.cmd in the project, then refresh. Copy any unsaved edits first.');
    throw e;
  }
  const data = await response.json();
  if (!response.ok) {
    const message = language === 'zh' && data.code === 'missing_token_condition' ? '草稿遗漏了用户令牌条件或没有引用该依据，请人工检查。' : (typeof data.detail === 'string' ? data.detail : t('error'));
    throw new Error(message);
  }
  return data;
}
async function operation(button, fn) {
  button.disabled = true;
  $('error').textContent = '';
  $('status').textContent = t('working');
  try {
    await fn();
    $('status').textContent = t('saved');
  } catch (e) {
    $('status').textContent = '';
    $('error').textContent = e.message;
  } finally {
    button.disabled = false;
    updateModel();
  }
}

function updateModel() {
  const profile = profiles.find(p => p.profile === $('model').value);
  $('generate').disabled = !record || !profile?.key_configured || !profile?.calls_enabled;
  $('model-status').textContent = profile?.calls_enabled && profile?.key_configured ? t('enabled') : t('disabled');
}
async function loadHistory() {
  const tickets = await request('/tickets');
  $('history').replaceChildren();
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = '—';
  $('history').append(blank);
  for (const ticket of tickets) {
    const option = document.createElement('option');
    option.value = ticket.id;
    option.textContent = ticket.question + ' · ' + new Date(ticket.created_at).toLocaleString();
    $('history').append(option);
  }
  if (record) $('history').value = record.ticket.id;
}

function renderRun() {
  const run = record.runs.find(r => r.id === $('runs').value) || record.runs.at(-1);
  selectedRun = run;
  if (!run) return;
  const result = run.result;
  $('run-note').textContent = localizeReason(result.review_reason);
  $('evidence').replaceChildren();
  if (!result.citations?.length) text($('evidence'), t('noEvidence'));
  (result.citations || []).forEach((c, i) => {
    const card = document.createElement('article');
    text(card, t('evidence') + ' ' + (i + 1) + ' · ' + c.title, 'h2');
    text(card, c.context?.text || c.text, 'pre');
    if (c.context) text(card, t('contextRange') + c.context.line_start + '–' + c.context.line_end);
    text(card, c.local_file + ' · ' + c.line_start + '–' + c.line_end);
    const a = document.createElement('a');
    const url = new URL(c.url);
    if (url.protocol === 'https:' && url.hostname === 'supabase.com') {
      a.href = url.href;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = t('source');
      card.append(a);
    }
    $('evidence').append(card);
  });
  const reviews = record.reviews.filter(r => r.run_id === run.id),
    latest = reviews.at(-1);
  // A saved edit is separate from the original model output and from approval.
  $('draft-origin').textContent = latest ? (language === 'zh' ? '已保存修订内容 · 审核状态：' : 'Saved revision · Review status: ') + t({
    draft: 'decisionDraft',
    approved: 'approved',
    needs_information: 'needsInfo',
    rejected: 'rejected'
  } [latest.decision]) : (result.model_called ? t('modelDraft') + ' · ' + result.model_name : t('manual'));
  $('original-model-panel').hidden = !(latest && result.model_called && result.draft);
  $('original-model-draft').textContent = result.model_called ? (result.draft || '') : '';
  if (latest) $('run-note').textContent = localizeReason(result.review_reason) + ' ' + (language === 'zh' ? '上方依据属于所选运行；修订时补充的资料请见审核备注。' : 'Evidence above belongs to the selected run. See review notes for sources added during revision.');
  $('draft').value = latest ? latest.draft : (result.draft || '');
  $('decision').value = latest?.decision || 'draft';
  $('notes').value = latest?.notes || '';
  $('review-status').textContent = latest ? '✓ ' + new Date(latest.created_at).toLocaleString() + ' · ' + reviews.length + ' review(s)' : '';
  $('missing').textContent = (result.missing_information || []).join(' / ');
  $('usage').textContent = result.model_called ? JSON.stringify({
    model: result.model_name,
    usage: result.usage,
    latency_ms: result.latency_ms,
    output_language: result.output_language
  }, null, 2) : '';
}
async function openTicket(id, runId) {
  record = await request('/tickets/' + encodeURIComponent(id));
  $('workspace').hidden = false;
  $('question').value = record.ticket.question;
  $('ticket-meta').textContent = 'Ticket: ' + record.ticket.id;
  $('reopen').href = '/?ticket=' + encodeURIComponent(id);
  $('runs').replaceChildren();
  record.runs.forEach((r, i) => {
    const option = document.createElement('option');
    option.value = r.id;
    option.textContent = (i + 1) + ' · ' + r.method + ' · ' + (r.model_name || 'no model') + ' · ' + new Date(r.created_at).toLocaleString();
    $('runs').append(option);
  });
  $('runs').value = runId || record.runs.at(-1)?.id;
  renderRun();
  updateModel();
  window.history.replaceState(null, '', '/?ticket=' + encodeURIComponent(id));
  await loadHistory();
}

function choices() {
  return {
    profile: $('model').value,
    language: $('reply-language').value
  };
}

function post(body) {
  return {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  };
}
$('question-form').addEventListener('submit', event => {
  event.preventDefault();
  operation($('submit'), async () => {
    const data = await request('/tickets', post({
      question: $('question').value,
      synthetic: true,
      retrieval: $('retrieval').value
    }));
    $('preview-panel').hidden = true;
    await openTicket(data.ticket_id, data.run_id);
  });
});
$('preview').addEventListener('click', () => operation($('preview'), async () => {
  if (!record) return;
  const query = new URLSearchParams(choices());
  const plan = await request('/tickets/' + record.ticket.id + '/model-input?' + query);
  $('input-preview').textContent = JSON.stringify(plan, null, 2);
  $('preview-panel').hidden = false;
  $('preview-panel').open = true;
}));
$('generate').addEventListener('click', () => operation($('generate'), async () => {
  if (!record) return;
  const data = await request('/tickets/' + record.ticket.id + '/generate', post(choices()));
  if (!data.model_called) {
    $('error').textContent = t('noEvidence');
    return;
  }
  await openTicket(record.ticket.id, data.run_id);
}));
$('review-form').addEventListener('submit', event => {
  event.preventDefault();
  operation($('save-review'), async () => {
    const saved = await request('/tickets/' + record.ticket.id + '/reviews', post({
      run_id: selectedRun.id,
      draft: $('draft').value,
      decision: $('decision').value,
      notes: $('notes').value
    }));
    await openTicket(record.ticket.id, selectedRun.id);
    const read = record.reviews.find(r => r.id === saved.id);
    if (!read || read.draft !== saved.draft) throw new Error(t('error'));
    $('review-status').textContent = t('reviewSaved');
  });
});
$('runs').addEventListener('change', renderRun);
$('history').addEventListener('change', () => {
  if ($('history').value) operation($('submit'), () => openTicket($('history').value));
});
$('model').addEventListener('change', updateModel);
$('ui-language').addEventListener('change', () => {
  language = $('ui-language').value;
  localStorage.setItem('supportdesk-ui-language', language);
  translate();
});
async function init() {
  translate();
  try {
    profiles = await request('/models');
    profiles.forEach(p => {
      const option = document.createElement('option');
      option.value = p.profile;
      option.textContent = p.model + ' · ' + p.provider;
      $('model').append(option);
    });
    const vector = await request('/vector/status');
    $('vector-status').textContent = t(vector.ready ? 'vectorReady' : 'vectorMissing');
    for (const option of $('retrieval').options) {
      if (option.value !== 'keyword') option.disabled = !vector.ready;
    }
    updateModel();
    await loadHistory();
    const id = new URLSearchParams(location.search).get('ticket');
    if (id) await openTicket(id);
  } catch (e) {
    $('error').textContent = e.message;
  }
}
init();
