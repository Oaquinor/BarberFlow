const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const mainScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = mainScript.indexOf('async function loadOwnerLiveChair()');
const end = mainScript.indexOf("\ndocument.getElementById('refreshOwnerLiveChair')", start);
const loaderSource = mainScript.slice(start, end);

function liveChairSandbox({ payload, userRole = 'barbershop_owner' }) {
  const nodes = {
    ownerLiveChair: { hidden: false },
    ownerLiveChairGrid: { innerHTML: '' },
    ownerLiveChairResult: { textContent: '' },
    refreshOwnerLiveChair: { disabled: false },
  };
  const requests = [];
  const sandbox = {
    API_ROOT: 'https://api.kingflow.test',
    currentUser: { role: userRole },
    liveChairRequestInFlight: false,
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
    Date,
    document: { getElementById: (id) => nodes[id] || null },
    escapeHtml: (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]),
    KingFlowAuth: { fetch: async (url) => {
      requests.push(url);
      if (payload instanceof Error) throw payload;
      return { ok: true, json: async () => payload };
    } },
  };
  vm.runInNewContext(`${loaderSource}\nthis.load = loadOwnerLiveChair;`, sandbox);
  return { sandbox, nodes, requests };
}

test('owner Live Chair shows appointment-derived states and keeps client identity private', async () => {
  const { sandbox, nodes, requests } = liveChairSandbox({ payload: {
    updated_at: '2026-11-25T16:00:00Z',
    items: [{
      barber_name: 'Barbero Uno', state: 'delayed', checked_in_count: 2,
      estimated_wait_minutes: 18,
      active_service: { service_type: '<script>alert(1)</script>', elapsed_minutes: 41, progress_percent: 100 },
      next_appointment: { scheduled_time: '2026-11-25T18:00:00Z', service_type: 'Barba clásica' },
    }],
  } });

  await sandbox.load();

  assert.deepEqual(requests, ['https://api.kingflow.test/api/v1/owner/live-chair']);
  assert.match(nodes.ownerLiveChairGrid.innerHTML, /Servicio con retraso/);
  assert.match(nodes.ownerLiveChairGrid.innerHTML, /2 cliente\(s\) confirmaron llegada/);
  assert.match(nodes.ownerLiveChairGrid.innerHTML, /~18 min/);
  assert.match(nodes.ownerLiveChairGrid.innerHTML, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(nodes.ownerLiveChairGrid.innerHTML, /<script>/);
  assert.match(nodes.ownerLiveChairResult.textContent, /actualizado a las/);
  assert.equal(nodes.refreshOwnerLiveChair.disabled, false);
});

test('Live Chair remains private to owners and recovers from service errors', async () => {
  const unauthorized = liveChairSandbox({ payload: { items: [] }, userRole: 'barber' });
  await unauthorized.sandbox.load();
  assert.deepEqual(unauthorized.requests, []);

  const failed = liveChairSandbox({ payload: new Error('offline') });
  await failed.sandbox.load();
  assert.equal(failed.nodes.ownerLiveChairResult.textContent, 'offline');
  assert.equal(failed.nodes.refreshOwnerLiveChair.disabled, false);
});
