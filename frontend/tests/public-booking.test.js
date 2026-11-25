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

test('availability lookup distinguishes an empty schedule from a failed request', async () => {
  const start = clientScript.indexOf('async function fetchSlots(');
  const end = clientScript.indexOf('\nasync function loadSlots', start);
  const functionSource = clientScript.slice(start, end);
  const responses = [
    { ok: true, json: async () => [] },
    { ok: false },
  ];
  const sandbox = {
    URL,
    API_BASE: 'https://api.kingflow.test/api/v1',
    shopSlug: 'kingflow-shop',
    fetch: async () => responses.shift(),
  };
  vm.runInNewContext(`${functionSource}\nthis.fetchSlots = fetchSlots;`, sandbox);

  assert.deepEqual(await sandbox.fetchSlots(30), []);
  assert.equal(await sandbox.fetchSlots(30), null);
  sandbox.fetch = async () => { throw new Error('offline'); };
  assert.equal(await sandbox.fetchSlots(30), null);
  assert.match(clientScript, /No se pudo consultar la disponibilidad/);
  const page = fs.readFileSync(path.join(__dirname, '..', 'client.html'), 'utf8');
  assert.match(page, /id="refreshSlotsBtn"/);
  assert.match(clientScript, /getElementById\('refreshSlotsBtn'\).*loadSlots\(selectedServiceDuration\(\)\)/s);
});

test('a slower old availability response cannot replace the selected service slots', async () => {
  const start = clientScript.indexOf('async function loadSlots(');
  const end = clientScript.indexOf('\nfunction renderAvailableSlots', start);
  const source = `let slotsRequestSequence = 0;\n${clientScript.slice(start, end)}`;
  const pending = new Map();
  const sandbox = {
    barberSelect: { value: '', innerHTML: '' },
    scheduledTimeSelect: { innerHTML: '' },
    selectedServiceDuration: () => 30,
    fetchSlots: (duration) => new Promise((resolve) => pending.set(duration, resolve)),
    escapeHtml: (value) => String(value),
    renderAvailableSlots() {},
  };
  vm.runInNewContext(`${source}\nthis.loadSlots = loadSlots;\nthis.getAvailableSlots = () => availableSlots;`, sandbox);

  const oldRequest = sandbox.loadSlots(30);
  const currentRequest = sandbox.loadSlots(60);
  pending.get(60)([{ availability_id: 2, barber_id: 2, barber_name: 'Actual' }]);
  await currentRequest;
  pending.get(30)([{ availability_id: 1, barber_id: 1, barber_name: 'Antiguo' }]);
  await oldRequest;

  assert.equal(sandbox.getAvailableSlots()[0].availability_id, 2);
  assert.match(sandbox.barberSelect.innerHTML, /Actual/);
  assert.doesNotMatch(sandbox.barberSelect.innerHTML, /Antiguo/);
});

test('public booking lets a client choose a barber and submits the selected barber with the slot', () => {
  const page = fs.readFileSync(path.join(__dirname, '..', 'client.html'), 'utf8');
  assert.match(page, /id="barberSelect"/);
  assert.match(clientScript, /barberSelect\?\.addEventListener\('change', renderAvailableSlots\)/);
  assert.match(clientScript, /barber_id: slot\.barber_id/);
  assert.match(clientScript, /value="\$\{Number\(s\.availability_id\)\}"/);
});

test('public experience shows the live catalog and sends consultation preferences with the booking', () => {
  const page = fs.readFileSync(path.join(__dirname, '..', 'client.html'), 'utf8');
  for (const id of ['publicServices', 'publicGallery', 'stylePreference', 'hairLength', 'finishPreference', 'consultationSummary']) {
    assert.match(page, new RegExp(`id="${id}"`));
  }
  assert.match(clientScript, /\['stylePreference', 'hairLength', 'finishPreference', 'clientNotes'\]/);
  assert.match(clientScript, /\['Estilo buscado', document\.getElementById\('stylePreference'\)\?\.value\]/);
  assert.match(clientScript, /notes: preferences\.length \? preferences\.join\('\\n'\)\.slice\(0, 1000\) : null/);
  assert.match(clientScript, /gallery_images/);
  const dashboardScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
  assert.match(dashboardScript, /appointment\.client_notes/);
  assert.match(dashboardScript, /escapeHtml\(appointment\.client_notes\)/);
});

test('public gallery ignores missing and cross-origin image URLs', () => {
  const start = clientScript.indexOf('function trustedShopImage(');
  const end = clientScript.indexOf('\n}', start) + 2;
  const sandbox = { URL, API_ROOT: 'https://api.kingflow.test' };
  vm.runInNewContext(`${clientScript.slice(start, end)}\nthis.trustedShopImage = trustedShopImage;`, sandbox);
  assert.equal(sandbox.trustedShopImage(undefined), '');
  assert.equal(sandbox.trustedShopImage(null), '');
  assert.equal(sandbox.trustedShopImage(''), '');
  assert.equal(sandbox.trustedShopImage('https://untrusted.example/photo.png'), '');
  assert.equal(sandbox.trustedShopImage('/uploads/barbershops/1/photo.png'), 'https://api.kingflow.test/uploads/barbershops/1/photo.png');
});

test('public hero uses the tenant cover or an image from its own gallery', () => {
  const start = clientScript.indexOf('function trustedShopImage(');
  const end = clientScript.indexOf('\nfunction renderServiceCards', start);
  const helperSource = clientScript.slice(start, end);
  const sandbox = { URL, API_ROOT: 'https://api.kingflow.test' };
  vm.runInNewContext(`${helperSource}\nthis.shopCoverImage = shopCoverImage;`, sandbox);
  assert.equal(sandbox.shopCoverImage({
    cover_image_url: '/uploads/tenant-cover.jpg',
    gallery_images: ['/uploads/work-1.jpg'],
  }), 'https://api.kingflow.test/uploads/tenant-cover.jpg');
  assert.equal(sandbox.shopCoverImage({
    cover_image_url: 'https://untrusted.example/cover.jpg',
    gallery_images: ['javascript:alert(1)', '/uploads/work-1.jpg'],
  }), 'https://api.kingflow.test/uploads/work-1.jpg');
  assert.equal(sandbox.shopCoverImage({ gallery_images: [] }), '');
});

test('shop profile loading exposes a retry control after server and network failures', async () => {
  const start = clientScript.indexOf('async function loadShop()');
  const end = clientScript.indexOf('\nfunction selectedServiceDuration', start);
  const functionSource = clientScript.slice(start, end);
  const retryButton = { hidden: true, disabled: false };
  const shopNameEl = { textContent: '' };
  const sandbox = {
    shopSlug: 'kingflow-shop',
    shopNameEl,
    document: { getElementById: () => retryButton },
    fetch: async () => { throw new Error('offline'); },
  };
  vm.runInNewContext(`${functionSource}\nthis.loadShop = loadShop;`, sandbox);

  await sandbox.loadShop();

  assert.match(shopNameEl.textContent, /Comprueba tu conexión/);
  assert.equal(retryButton.hidden, false);
  assert.equal(retryButton.disabled, false);
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

test('public support requests recover from network failures without encouraging duplicate tickets', async () => {
  const start = clientScript.indexOf('async function sendSupport()');
  const end = clientScript.indexOf('\nbookBtn.addEventListener', start);
  const functionSource = clientScript.slice(start, end);
  const nodes = {
    supportName: { value: 'Cliente' },
    supportEmail: { value: 'client@example.com' },
    supportPhone: { value: '8095550101' },
    supportMessage: { value: 'Necesito ayuda' },
    supportResult: { textContent: '' },
    supportBtn: { disabled: false },
  };
  const sandbox = {
    document: { getElementById: (id) => nodes[id] },
    fetch: async () => { throw new Error('offline'); },
    API_BASE: 'https://api.kingflow.test/api/v1',
    shopSlug: 'kingflow-shop',
  };
  vm.runInNewContext(`const supportBtn = document.getElementById('supportBtn');\n${functionSource}\nthis.sendSupport = sendSupport;`, sandbox);

  await sandbox.sendSupport();

  assert.match(nodes.supportResult.textContent, /consulta con soporte antes de enviar otra solicitud/);
  assert.equal(nodes.supportBtn.disabled, false);
});

test('onboarding shows logo upload success and errors and waits for an active upload', () => {
  assert.match(onboardingPage, /id="logoUploadStatus" role="status" aria-live="polite"/);
  assert.match(onboardingScript, /logoUploadPending = true/);
  assert.match(onboardingScript, /logoUploadPending = false/);
  assert.match(onboardingScript, /status\.textContent = 'Logo subido correctamente\.'/);
  assert.match(onboardingScript, /No se pudo subir el logo/);
  assert.match(onboardingScript, /Espera a que termine la subida del logo antes de continuar/);
});
