const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = script.indexOf('function renderBarberLiveState(');
const end = script.indexOf('\nasync function ownerFetch(', start);
const source = script.slice(start, end);

function createSandbox({ initialState = 'available', putResponse = { state: 'on_break' } } = {}) {
  const nodes = Object.fromEntries([
    'barberLivePresence', 'barberLivePresenceDescription', 'barberStartBreak',
    'barberResumeAvailability', 'barberLivePresenceResult', 'finishServiceButton',
    'barberBreakDuration',
  ].map(id => [id, { hidden: id === 'barberResumeAvailability' || id === 'barberLivePresence', disabled: false, textContent: '', dataset: {}, addEventListener() {} }]));
  const requests = [];
  const sandbox = {
    API_ROOT: 'https://api.kingflow.test',
    currentUser: { role: 'barber' },
    barberLiveState: 'available',
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
    document: { getElementById: id => nodes[id] || null },
    KingFlowAuth: { fetch: async (url, options = {}) => {
      requests.push({ url, options });
      const state = options.method === 'PUT' ? putResponse : { state: initialState };
      return { ok: options.method !== 'PUT' || !putResponse.detail, json: async () => state };
    } },
  };
  vm.runInNewContext(`${source}\nthis.render = renderBarberLiveState; this.load = loadBarberLiveStatus; this.set = setBarberLiveStatus;`, sandbox);
  return { sandbox, nodes, requests };
}

test('barber can pause and resume presence through the authenticated API', async () => {
  const { sandbox, nodes, requests } = createSandbox();
  await sandbox.load();
  assert.equal(nodes.barberLivePresence.hidden, false);
  assert.match(nodes.barberLivePresenceDescription.textContent, /disponible/);
  await sandbox.set('on_break');
  assert.equal(nodes.barberLivePresence.dataset.state, 'on_break');
  assert.equal(nodes.barberStartBreak.hidden, true);
  assert.equal(nodes.barberResumeAvailability.hidden, false);
  assert.equal(nodes.barberLivePresenceResult.textContent, 'Descanso iniciado.');
  assert.deepEqual(requests[1].options.body, JSON.stringify({ state: 'on_break', break_duration_minutes: 15 }));
});

test('barber identity check avoids availability requests for owners', async () => {
  const { sandbox, nodes, requests } = createSandbox();
  sandbox.currentUser.role = 'barbershop_owner';
  await sandbox.load();
  assert.equal(requests.length, 0);
  assert.equal(nodes.barberLivePresence.hidden, true);
});
