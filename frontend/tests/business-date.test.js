const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');

test('barber calendar defaults use the shop date when UTC is already on the next day', () => {
  const start = source.indexOf('function businessTodayDate()');
  const end = source.indexOf('\n}', start) + 2;
  const helper = source.slice(start, end);
  const instant = Date.parse('2026-11-20T02:30:00Z');
  class FrozenDate extends Date {
    constructor(...args) { super(...(args.length ? args : [instant])); }
    static now() { return instant; }
  }
  const sandbox = {
    Date: FrozenDate,
    Intl,
    barbershopProfile: { timezone: 'America/Santo_Domingo' },
  };

  vm.runInNewContext(`${helper}\nthis.businessTodayDate = businessTodayDate;`, sandbox);

  assert.equal(new Date(instant).toISOString().slice(0, 10), '2026-11-20');
  assert.equal(sandbox.businessTodayDate(), '2026-11-19');
  assert.match(source, /slotDate\.value = businessTodayDate\(\)/);
  assert.match(source, /data\.business_date \|\| businessTodayDate\(\)/);
});
