const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = source.indexOf('function updateActiveServiceTimer(');
const end = source.indexOf('\nfunction setTrend(', start);
const timerSource = source.slice(start, end);

test('active service timer renders elapsed time and updates estimated progress', () => {
  let now = Date.parse('2026-11-19T15:01:30Z');
  const intervals = new Map();
  const nodes = new Map();
  const nodeFor = (id) => {
    if (!nodes.has(id)) nodes.set(id, { textContent: '', style: {} });
    return nodes.get(id);
  };
  class TestDate extends Date {
    static now() { return now; }
  }
  const sandbox = {
    Date: TestDate,
    document: { getElementById: nodeFor },
    setText: (id, value) => { nodeFor(id).textContent = value; },
    setInterval: (callback) => { intervals.set(1, callback); return 1; },
    clearInterval: (id) => intervals.delete(id),
  };

  vm.runInNewContext(`let serviceTimerInterval = null;\n${timerSource}`, sandbox);
  sandbox.updateActiveServiceTimer('2026-11-19T15:00:00Z', 3, {
    scheduled_time: '2026-11-19T15:16:30Z',
  });
  assert.equal(nodeFor('elapsedTime').textContent, '00:01:30');
  assert.equal(nodeFor('activeServiceProgress').textContent, '50%');
  assert.equal(nodeFor('activeServiceProgressBar').style.width, '50%');
  assert.match(nodeFor('activeServiceAlert').textContent, /Próxima cita en 15 minutos/);

  now += 90_000;
  intervals.get(1)();
  assert.equal(nodeFor('elapsedTime').textContent, '00:03:00');
  assert.equal(nodeFor('activeServiceProgress').textContent, '100%');
  assert.match(nodeFor('activeServiceAlert').textContent, /0 minutos restantes/);

  now += 1_000;
  intervals.get(1)();
  assert.equal(nodeFor('elapsedTime').textContent, '00:03:01');
  assert.match(nodeFor('activeServiceAlert').textContent, /superó su duración estimada/);
  assert.match(nodeFor('activeServiceAlert').textContent, /Próxima cita en 14 minutos/);

  sandbox.updateActiveServiceTimer(null);
  assert.equal(nodeFor('elapsedTime').textContent, '00:00:00');
  assert.equal(intervals.size, 0);
});

test('dashboard clears the previous next appointment when there are no upcoming bookings', () => {
  const renderSource = source.match(/function renderNextAppointment\(next\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(renderSource, 'next appointment renderer must exist');
  const nodes = new Map();
  const nodeFor = (id) => {
    if (!nodes.has(id)) nodes.set(id, { textContent: 'stale appointment' });
    return nodes.get(id);
  };
  const sandbox = {
    document: { getElementById: nodeFor },
    setText: (id, value) => { nodeFor(id).textContent = value; },
    fmtHour: (value) => value,
  };

  vm.runInNewContext(`${renderSource}\nthis.renderNextAppointment = renderNextAppointment;`, sandbox);
  sandbox.renderNextAppointment(null);

  assert.equal(nodeFor('nextAppointmentTime').textContent, '--:--');
  assert.equal(nodeFor('nextAppointmentEta').textContent, 'Sin próxima cita');
  assert.equal(nodeFor('nextAppointmentClient').textContent, 'Agenda del día');
  assert.equal(nodeFor('nextAppointmentService').textContent, 'No tienes citas próximas');
  assert.equal(nodeFor('nextAppointmentDuration').textContent, '-- min estimados');
});
