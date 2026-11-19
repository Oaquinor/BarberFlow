const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const clientScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'client.js'), 'utf8');

test('public booking loads slots for the selected service duration', () => {
  assert.match(clientScript, /function selectedServiceDuration\(\)/);
  assert.match(clientScript, /url\.searchParams\.set\('duration_minutes', String\(Number\(durationMinutes\)\)\)/);
  assert.match(clientScript, /serviceSelect\.addEventListener\('change', \(\) => loadSlots\(selectedServiceDuration\(\)\)\)/);
});

test('appointment tracking requests replacement slots for each appointment duration', () => {
  assert.match(clientScript, /const duration = Number\(item\.estimated_duration\)/);
  assert.match(clientScript, /slotResults\.set\(duration, fetchSlots\(duration\)\)/);
});
