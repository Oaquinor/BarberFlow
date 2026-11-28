const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
test('all pages use compiled Tailwind with no legacy stylesheets or embedded styles', () => {
  assert.deepEqual(fs.readdirSync(path.join(root, 'css')).filter(name => name.endsWith('.css')), ['tailwind.css']);
  assert.match(fs.readFileSync(path.join(root, 'styles/tailwind.css'), 'utf8'), /@import "tailwindcss"/);
  assert.match(fs.readFileSync(path.join(root, 'css/tailwind.css'), 'utf8'), /box-sizing:border-box/);
  for (const file of fs.readdirSync(root).filter(name => name.endsWith('.html'))) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    assert.doesNotMatch(html, /<style\b/i, file);
    const sheets = [...html.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"/g)].map(match => match[1]);
    assert.equal(sheets.length, 1, file);
    assert.match(sheets[0], /^\/css\/tailwind\.css\?/, file);
    assert.doesNotMatch(html, /style="[^"]*(?:position\s*:\s*absolute|float\s*:|margin[^:]*:\s*-)/i, file);
  }
});
