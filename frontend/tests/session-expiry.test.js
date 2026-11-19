const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'main.js'), 'utf8');
const start = source.indexOf('function resetSessionInterface(');
const end = source.indexOf('\nwindow.addEventListener(\'kingflow:auth-expired\'', start);
const resetSource = source.slice(start, end);

test('expired sessions hide private dashboard data and return to login', () => {
  const removed = [];
  const clearedIntervals = [];
  const nodes = new Map();
  const nodeFor = (id) => {
    if (!nodes.has(id)) {
      nodes.set(id, {
        style: {}, hidden: false, value: '', textContent: '', open: false,
        close() { this.open = false; },
      });
    }
    return nodes.get(id);
  };
  const sandbox = {
    document: { getElementById: nodeFor },
    localStorage: { removeItem: (key) => removed.push(key) },
    clearInterval: (id) => clearedIntervals.push(id),
  };
  vm.runInNewContext(
    `let notificationRefreshTimer = 10; let serviceTimerInterval = 20; let accessToken = 'secret'; let currentUser = { id: 1 };\n${resetSource}`,
    sandbox,
  );
  nodeFor('dashboardSection').style.display = 'block';
  nodeFor('loginSection').style.display = 'none';
  nodeFor('userInfo').style.display = 'flex';
  nodeFor('loginEmail').value = 'owner@example.com';
  nodeFor('loginPassword').value = 'private-password';
  nodeFor('passwordChangeDialog').open = true;

  sandbox.resetSessionInterface('Tu sesión expiró. Inicia sesión nuevamente para continuar.');

  assert.equal(nodeFor('dashboardSection').style.display, 'none');
  assert.equal(nodeFor('loginSection').style.display, 'flex');
  assert.equal(nodeFor('userInfo').style.display, 'none');
  assert.equal(nodeFor('loginEmail').value, '');
  assert.equal(nodeFor('loginPassword').value, '');
  assert.equal(nodeFor('passwordChangeDialog').open, false);
  assert.equal(nodeFor('sessionExpiredNotice').hidden, false);
  assert.match(nodeFor('sessionExpiredNotice').textContent, /sesión expiró/i);
  assert.deepEqual(removed, ['userEmail']);
  assert.deepEqual(clearedIntervals, [10, 20]);
  assert.equal(vm.runInContext('accessToken', sandbox), null);
  assert.equal(vm.runInContext('currentUser', sandbox), null);
  assert.match(source, /window\.addEventListener\('kingflow:auth-expired', \(\) => \{\s*resetSessionInterface\(/);
});
