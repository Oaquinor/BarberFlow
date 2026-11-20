const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const clientScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'client.js'), 'utf8');
const onboardingScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'onboarding.js'), 'utf8');
const onboardingPage = fs.readFileSync(path.join(__dirname, '..', 'onboarding.html'), 'utf8');

test('public booking loads slots for the selected service duration', () => {
  assert.match(clientScript, /function selectedServiceDuration\(\)/);
  assert.match(clientScript, /url\.searchParams\.set\('duration_minutes', String\(Number\(durationMinutes\)\)\)/);
  assert.match(clientScript, /serviceSelect\.addEventListener\('change', \(\) => loadSlots\(selectedServiceDuration\(\)\)\)/);
});

test('public booking lets a client choose a barber and submits the selected barber with the slot', () => {
  const page = fs.readFileSync(path.join(__dirname, '..', 'client.html'), 'utf8');
  assert.match(page, /id="barberSelect"/);
  assert.match(clientScript, /barberSelect\?\.addEventListener\('change', renderAvailableSlots\)/);
  assert.match(clientScript, /barber_id: slot\.barber_id/);
  assert.match(clientScript, /value="\$\{Number\(s\.availability_id\)\}"/);
});

test('booking only exposes tracking links for the app or configured API origin', () => {
  const start = clientScript.indexOf('function trustedTrackingUrl(');
  const end = clientScript.indexOf('\n}', start) + 2;
  const helper = clientScript.slice(start, end);
  const sandbox = {
    URL,
    Set,
    API_ROOT: 'https://api.kingflow.test',
    shopSlug: 'kingflow-shop',
    window: { location: { origin: 'https://app.kingflow.test' } },
  };
  vm.runInNewContext(`${helper}\nthis.trustedTrackingUrl = trustedTrackingUrl;`, sandbox);

  assert.equal(
    sandbox.trustedTrackingUrl('/client.html?shop=kingflow-shop&track_token=opaque').origin,
    'https://app.kingflow.test',
  );
  assert.equal(
    sandbox.trustedTrackingUrl('http://localhost:8000/client.html?shop=kingflow-shop&track_token=opaque'),
    null,
  );
  assert.equal(
    sandbox.trustedTrackingUrl('https://api.kingflow.test/client.html?shop=kingflow-shop&track_token=opaque').origin,
    'https://api.kingflow.test',
  );
  assert.equal(sandbox.trustedTrackingUrl('https://attacker.test/client.html?shop=kingflow-shop&track_token=opaque'), null);
  assert.equal(sandbox.trustedTrackingUrl('https://app.kingflow.test/client.html?shop=other-shop&track_token=opaque'), null);
  assert.equal(sandbox.trustedTrackingUrl('javascript:alert(1)'), null);
  assert.equal(sandbox.trustedTrackingUrl('https://app.kingflow.test/client.html?shop=kingflow-shop#external'), null);
});

test('appointment tracking requests replacement slots for each appointment duration', () => {
  assert.match(clientScript, /const duration = Number\(item\.estimated_duration\)/);
  assert.match(clientScript, /slotResults\.set\(duration, fetchSlots\(duration\)\)/);
});

test('appointment tracking handles network failures and allows another attempt', async () => {
  const start = clientScript.indexOf('async function trackAppointments()');
  const end = clientScript.indexOf('\ntrackList.addEventListener', start);
  const functionSource = clientScript.slice(start, end);
  const nodes = {
    trackToken: { value: 'private-token' },
    trackList: { textContent: '', innerHTML: '' },
    trackBtn: { disabled: false },
  };
  const sandbox = {
    document: { getElementById: (id) => nodes[id] },
    fetch: async () => { throw new Error('offline'); },
    API_BASE: 'https://api.kingflow.test/api/v1',
    shopSlug: 'kingflow-shop',
  };
  vm.runInNewContext(`const trackBtn = document.getElementById('trackBtn');\nconst trackList = document.getElementById('trackList');\n${functionSource}\nthis.trackAppointments = trackAppointments;`, sandbox);

  await sandbox.trackAppointments();

  assert.match(nodes.trackList.textContent, /Comprueba tu conexión/);
  assert.equal(nodes.trackBtn.disabled, false);
});

test('appointment tracking escapes untrusted customer, service, barber, and status values', async () => {
  const nodes = new Map();
  const nodeFor = (id) => {
    if (!nodes.has(id)) nodes.set(id, { value: '', textContent: '', innerHTML: '', addEventListener() {} });
    return nodes.get(id);
  };
  nodeFor('trackToken').value = 'private-tracking-token';
  const payload = {
    items: [{
      appointment_id: 7,
      client_name: '<img src=x onerror=alert(1)>',
      service_type: '<svg onload=alert(2)>',
      barber_name: '<script>alert(3)</script>',
      status: '<iframe srcdoc=alert(4)>',
      scheduled_time: '2026-11-19T15:00:00Z',
      estimated_duration: 30,
    }],
  };
  const sandbox = {
    URL,
    URLSearchParams,
    Date,
    Intl,
    document: { getElementById: nodeFor },
    window: { location: { origin: 'https://kingflow.test', search: '?shop=valid-shop' }, addEventListener() {}, alert() {} },
    fetch: async () => ({ ok: true, status: 200, json: async () => payload }),
  };

  vm.runInNewContext(clientScript, sandbox, { filename: 'client.js' });
  await sandbox.trackAppointments();

  const rendered = nodeFor('trackList').innerHTML;
  assert.doesNotMatch(rendered, /onerror=alert\(1\)/);
  assert.match(rendered, /&lt;svg onload=alert\(2\)&gt;/);
  assert.match(rendered, /&lt;script&gt;alert\(3\)&lt;\/script&gt;/);
  assert.match(rendered, /&lt;iframe srcdoc=alert\(4\)&gt;/);
  assert.doesNotMatch(rendered, /<\/?(?:img|svg|script|iframe)\b/i);
});

test('booking prevents duplicate submissions and explains an uncertain network result', () => {
  assert.match(clientScript, /bookBtn\.disabled = true/);
  assert.match(clientScript, /finally \{\s*bookBtn\.disabled = false/);
  assert.match(clientScript, /Revisa tus citas con el código de seguimiento antes de volver a reservar/);
});

test('reschedule and cancellation recover from network failures without hiding uncertainty', () => {
  assert.match(clientScript, /No pudimos confirmar el cambio\. Actualiza el seguimiento antes de intentarlo otra vez/);
  assert.match(clientScript, /No pudimos confirmar la cancelación\. Actualiza el seguimiento antes de intentarlo otra vez/);
});

test('onboarding shows logo upload success and errors and waits for an active upload', () => {
  assert.match(onboardingPage, /id="logoUploadStatus" role="status" aria-live="polite"/);
  assert.match(onboardingScript, /logoUploadPending = true/);
  assert.match(onboardingScript, /logoUploadPending = false/);
  assert.match(onboardingScript, /status\.textContent = 'Logo subido correctamente\.'/);
  assert.match(onboardingScript, /No se pudo subir el logo/);
  assert.match(onboardingScript, /Espera a que termine la subida del logo antes de continuar/);
});
