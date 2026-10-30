// Execute the UI's own language-switching code with a minimal DOM fixture.
// This is a programmatic check, not a visual browser test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('app/stage1.html', 'utf8');
const script = fs.readFileSync('app/stage1.js', 'utf8');
assert.ok(html.includes('href="/assets/stage1.css"'));
assert.ok(html.includes('src="/assets/stage1.js"'));
const listeners = {};
const elements = new Map();
function element(id = '') {
  if (!elements.has(id)) elements.set(id, {
    id, value: '', textContent: '', disabled: false, hidden: false, open: false,
    addEventListener(event, handler) { listeners[id + ':' + event] = handler; },
    append() {}, replaceChildren() {},
  });
  return elements.get(id);
}
const translated = [...html.matchAll(/data-i18n="([^"]+)"/g)].map(match => ({
  dataset: { i18n: match[1] }, textContent: '',
}));
const storage = new Map();
const document = {
  documentElement: { lang: '' },
  getElementById: element,
  createElement: () => element('created-' + Math.random()),
  querySelectorAll: () => translated,
};
const response = value => ({ ok: true, json: async () => value });
const fetch = async url => response(url === '/models' ? [] : url === '/vector/status' ? { ready: false } : []);
const context = { document, localStorage: { getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, value) }, fetch, URL, URLSearchParams,
  window: { location: { search: '' }, history: { replaceState() {} } }, console };
vm.runInNewContext(script, context);
const label = key => translated.find(n => n.dataset.i18n === key).textContent;
assert.equal(document.documentElement.lang, 'en');
assert.equal(label('title'), 'Find evidence, review a reply');
assert.equal(label('search'), 'Search and save');
element('ui-language').value = 'zh';
listeners['ui-language:change']();
assert.equal(document.documentElement.lang, 'zh-CN');
assert.equal(label('search'), '检索并保存');
assert.equal(context.localizeReason('No keyword evidence was found in the selected sources.'), '限定资料中未找到关键词依据。');
element('ui-language').value = 'en';
listeners['ui-language:change']();
assert.equal(document.documentElement.lang, 'en');
assert.equal(label('search'), 'Search and save');
assert.equal(storage.get('supportdesk-ui-language'), 'en');
console.log('English default and Chinese/English switching passed.');
