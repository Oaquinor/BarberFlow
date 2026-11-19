const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const clientScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'client.js'), 'utf8');
const onboardingScript = fs.readFileSync(path.join(__dirname, '..', 'js', 'onboarding.js'), 'utf8');
const onboardingPage = fs.readFileSync(path.join(__dirname, '..', 'onboarding.html'), 'utf8');

test('public booking loads slots for the selected service duration', () => {
  assert.match(clientScript, /function selectedServiceDuration\(\)/);
  assert.match(clientScript, /url\.searchParams\.set\('duration_minutes', String\(Number\(durationMinutes\)\)\)/);
  assert.match(clientScript, /serviceSelect\.addEventListener\('change', \(\) => loadSlots\(selectedServiceDuration\(\)\)\)/);
});

test('appointment tracking requests replacement slots for each appointment duration', () => {
  assert.match(clientScript, /const duration = Number\(item\.estimated_duration\)/);
  assert.match(clientScript, /slotResults\.set\(duration, fetchSlots\(duration\)\)/);
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
