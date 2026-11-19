const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { once } = require('node:events');

process.env.WHATSAPP_API_TOKEN = 'test-only-whatsapp-secret';
const { app, formatPhoneNumber, requireApiToken, validateMessage } = require('./server');

let httpServer;
let baseUrl;

before(async () => {
  httpServer = app.listen(0, '127.0.0.1');
  await once(httpServer, 'listening');
  baseUrl = `http://127.0.0.1:${httpServer.address().port}`;
});

after(() => new Promise((resolve, reject) => {
  httpServer.close((error) => error ? reject(error) : resolve());
}));

test('returns JSON 413 for oversized request bodies', async () => {
  const response = await fetch(`${baseUrl}/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: 'x'.repeat(20_000) }),
  });
  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), { success: false, error: 'Request body too large' });
});

test('returns a generic JSON error for malformed request bodies', async () => {
  const response = await fetch(`${baseUrl}/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{invalid',
  });
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { success: false, error: 'Invalid request body' });
});

test('normalizes a ten digit Dominican number to an international WhatsApp JID', () => {
  assert.equal(formatPhoneNumber('809-555-1234'), '18095551234@s.whatsapp.net');
});

test('preserves an explicit NANP country code', () => {
  assert.equal(formatPhoneNumber('+1 (809) 555-1234'), '18095551234@s.whatsapp.net');
});

test('rejects malformed or short phone numbers', () => {
  assert.equal(formatPhoneNumber('call 8095551234'), null);
  assert.equal(formatPhoneNumber('123'), null);
});

test('rejects empty, non-text, and oversized messages', () => {
  assert.equal(validateMessage('   ').valid, false);
  assert.equal(validateMessage({ text: 'no' }).valid, false);
  assert.equal(validateMessage('x'.repeat(4097)).valid, false);
  assert.equal(validateMessage('Cita confirmada').valid, true);
});

test('rejects WhatsApp API calls without the bearer token', () => {
  let statusCode;
  let body;
  let nextCalled = false;
  const response = {
    status(code) { statusCode = code; return this; },
    json(value) { body = value; return this; },
  };
  requireApiToken({ get: () => '' }, response, () => { nextCalled = true; });
  assert.equal(statusCode, 401);
  assert.equal(body.error, 'Unauthorized');
  assert.equal(nextCalled, false);
});

test('accepts WhatsApp API calls with the configured bearer token', () => {
  let nextCalled = false;
  requireApiToken(
    { get: () => 'Bearer test-only-whatsapp-secret' },
    {},
    () => { nextCalled = true; },
  );
  assert.equal(nextCalled, true);
});
