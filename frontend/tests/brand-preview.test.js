const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = source.indexOf('function setupBrandPreview() {');
const end = source.indexOf('\nasync function loadOwnerClients()', start);
const previewSource = source.slice(start, end);

function makeNode(value = '') {
  return {
    value,
    textContent: '',
    dataset: {},
    style: { setProperty(name, nextValue) { this[name] = nextValue; } },
    listeners: {},
    attributes: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
    setAttribute(name, nextValue) { this.attributes[name] = nextValue; },
    removeAttribute(name) { delete this.attributes[name]; },
  };
}

test('public brand preview uses actual business details and catalog service', () => {
  const nodes = new Map([
    ['businessSettingsPrimary', makeNode('#b98752')],
    ['businessSettingsSecondary', makeNode('#5a4635')],
    ['businessSettingsTheme', makeNode('light')],
    ['businessSettingsName', makeNode('KingFlow de prueba')],
    ['businessSettingsDescription', makeNode('Cortes con intención.')],
    ['brandPreview', makeNode()],
    ['brandPreviewMark', makeNode()],
    ['brandPreviewLogo', makeNode()],
    ['brandPreviewCover', makeNode()],
    ['brandPreviewName', makeNode()],
    ['brandPreviewDescription', makeNode()],
    ['brandPreviewService', makeNode()],
    ['brandPreviewServiceMeta', makeNode()],
    ['brandContrastNote', makeNode()],
  ]);
  const presets = [
    { ...makeNode(), dataset: { primary: '#9aa276', secondary: '#47513a' } },
  ];
  const sandbox = {
    API_ROOT: 'http://localhost:8000',
    URL,
    window: { location: { origin: 'http://localhost:8000' } },
    document: {
      getElementById: (id) => nodes.get(id) || null,
      querySelectorAll: (selector) => selector === '.brand-presets button' ? presets : [],
    },
  };
  vm.runInNewContext(`let serviceCache = [{ name: 'Corte ejecutivo', price_cents: 1200, duration_minutes: 40 }];
    let barbershopProfile = { logo_url: '/uploads/logo.png', cover_image_url: '/uploads/cover.png' };
    function fmtMoneyFromCents(value) { return '$' + (value / 100).toFixed(2); }
    ${previewSource}
    setupBrandPreview();`, sandbox);

  assert.equal(nodes.get('brandPreviewName').textContent, 'KingFlow de prueba');
  assert.equal(nodes.get('brandPreviewDescription').textContent, 'Cortes con intención.');
  assert.equal(nodes.get('brandPreviewService').textContent, 'Corte ejecutivo');
  assert.equal(nodes.get('brandPreviewServiceMeta').textContent, '$12.00 · 40 min');
  assert.equal(nodes.get('brandPreviewMark').hidden, true);
  assert.equal(nodes.get('brandPreviewLogo').src, 'http://localhost:8000/uploads/logo.png');
  assert.equal(nodes.get('brandPreviewCover').src, 'http://localhost:8000/uploads/cover.png');
  assert.equal(nodes.get('brandContrastNote').dataset.level, 'good');
  assert.equal(presets[0].attributes['aria-pressed'], 'false');

  presets[0].listeners.click();

  assert.equal(nodes.get('businessSettingsPrimary').value, '#9aa276');
  assert.equal(nodes.get('businessSettingsSecondary').value, '#47513a');
  assert.equal(presets[0].attributes['aria-pressed'], 'true');
  assert.equal(nodes.get('brandPreview').dataset.theme, 'light');
  assert.equal(nodes.get('brandContrastNote').dataset.level, 'good');
});

test('recommended brand palettes have unique valid color pairs and accessible state', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  const block = html.match(/<div class="brand-presets[^"]*"[\s\S]*?<\/div>/)?.[0] || '';
  const pairs = [...block.matchAll(/data-primary="(#[\da-f]{6})" data-secondary="(#[\da-f]{6})" aria-pressed="false"/gi)]
    .map((match) => `${match[1].toLowerCase()}:${match[2].toLowerCase()}`);

  assert.equal(pairs.length, 4);
  assert.equal(new Set(pairs).size, pairs.length);
});
