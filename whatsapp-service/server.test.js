const test = require('node:test');
const assert = require('node:assert/strict');

process.env.WHATSAPP_API_TOKEN = 'test-only-whatsapp-secret';
const { formatPhoneNumber, requireApiToken, validateMessage } = require('./server');

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
