const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const mainScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = mainScript.indexOf('async function loadOwnerWaitlist()');
const end = mainScript.indexOf('\ndocument.getElementById(\'refreshOwnerWaitlist\')', start);
const loaderSource = mainScript.slice(start, end);

function renderOwnerWaitlist({ rows, status = '', userRole = 'barbershop_owner' }) {
  const nodes = {
    ownerWaitlistBody: { innerHTML: '', replaceChildren() { this.innerHTML = ''; } },
    ownerWaitlistResult: { textContent: '' },
    ownerWaitlistStatus: { value: status },
  };
  const requests = [];
  const sandbox = {
    URLSearchParams,
    Date,
    currentUser: { role: userRole },
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
    document: { getElementById: (id) => nodes[id] || null },
    escapeHtml: (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]),
    ownerFetch: async (url) => {
      requests.push(url);
      return { items: rows, total: rows.length };
    },
  };
  vm.runInNewContext(`${loaderSource}\nthis.load = loadOwnerWaitlist;`, sandbox);
  return sandbox.load().then(() => ({ nodes, requests }));
}

test('owner waitlist renders escaped tenant data and safe WhatsApp links', async () => {
  const { nodes, requests } = await renderOwnerWaitlist({ status: 'new', rows: [{
    id: 17,
    client_name: '<script>alert(1)</script>',
    phone: '+1 (809) 555-4141',
    service_name: 'Corte <clásico>',
    barber_name: null,
    preferred_date_start: null,
    preferred_date_end: null,
    notes: '<img src=x onerror=alert(2)>',
    status: 'new',
    created_at: '2026-11-25T12:00:00Z',
  }] });

  assert.deepEqual(requests, ['/owner/waitlist?limit=100&status=new']);
  assert.match(nodes.ownerWaitlistBody.innerHTML, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(nodes.ownerWaitlistBody.innerHTML, /&lt;img src=x onerror=alert\(2\)&gt;/);
  assert.doesNotMatch(nodes.ownerWaitlistBody.innerHTML, /<script>|<img/);
  assert.match(nodes.ownerWaitlistBody.innerHTML, /href="https:\/\/wa\.me\/18095554141\?text=/);
  assert.match(nodes.ownerWaitlistBody.innerHTML, /Buscar horarios/);
  assert.match(nodes.ownerWaitlistBody.innerHTML, /Marcar contactado/);
  assert.equal(nodes.ownerWaitlistResult.textContent, '1 solicitud(es) · 1 en este filtro');
});

test('owner can offer a matching open slot through WhatsApp with a preselected booking link', async () => {
  const start = mainScript.indexOf("document.getElementById('ownerWaitlistBody')?.addEventListener");
  const end = mainScript.indexOf('\nlet ownerInventoryProducts = [];', start);
  const listenerSource = mainScript.slice(start, end);
  let clickHandler;
  const result = { textContent: '', innerHTML: '' };
  const button = {
    dataset: { id: '17' },
    disabled: false,
    closest(selector) { return selector === '.owner-waitlist-matches' ? this : selector === 'tr' ? row : null; },
  };
  const row = { querySelector: () => ({ getAttribute: () => 'tel:18095554141' }) };
  const calls = [];
  const sandbox = {
    Date,
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
    escapeHtml: (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    })[char]),
    document: {
      getElementById: (id) => id === 'ownerWaitlistBody' ? { addEventListener(_type, handler) { clickHandler = handler; } }
        : id === 'ownerWaitlistMatches17' ? result : null,
    },
    ownerFetch: async (url) => {
      calls.push(url);
      return {
        service_name: 'Corte clásico',
        items: [{
          slot_start: '2026-12-01T21:00:00Z', barber_name: 'Barbero Uno',
          booking_url: 'https://kingflow.test/client.html?shop=local&service_id=4&barber_id=8',
        }],
      };
    },
    showConfirmation: async () => true,
  };

  vm.runInNewContext(listenerSource, sandbox);
  await clickHandler({ target: { closest: (selector) => selector === '.owner-waitlist-matches' ? button : null } });

  assert.deepEqual(calls, ['/owner/waitlist/17/matches']);
  assert.match(result.innerHTML, /El turno no queda reservado/);
  assert.match(result.innerHTML, /Ofrecer horario por WhatsApp/);
  assert.match(result.innerHTML, /service_id%3D4%26barber_id%3D8/);
  assert.equal(button.disabled, false);
});

test('waitlist requests are not fetched for other dashboard roles', async () => {
  const { nodes, requests } = await renderOwnerWaitlist({ userRole: 'barber', rows: [] });
  assert.deepEqual(requests, []);
  assert.equal(nodes.ownerWaitlistResult.textContent, '');
});
