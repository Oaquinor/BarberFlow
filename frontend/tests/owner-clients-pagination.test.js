"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("document.getElementById('previousOwnerClients')?.addEventListener");
const end = source.indexOf("async function loadOwnerSubscription", start);
assert.ok(start >= 0 && end > start, "could not isolate owner client pagination controls");

test("owner client pagination requests the next and previous tenant pages", async () => {
  const previous = { disabled: true, listener: null, addEventListener(_event, listener) { this.listener = listener; } };
  const next = { disabled: false, listener: null, addEventListener(_event, listener) { this.listener = listener; } };
  const offsets = [];
  const sandbox = {
    document: { getElementById: (id) => ({ previousOwnerClients: previous, nextOwnerClients: next })[id] || null },
    loadOwnerClients: async () => { offsets.push(sandbox.offset()); },
  };
  vm.runInNewContext(`
    let ownerClientsOffset = 0;
    const OWNER_CLIENTS_PAGE_SIZE = 50;
    const document = globalThis.document;
    const loadOwnerClients = globalThis.loadOwnerClients;
    ${source.slice(start, end)}
    globalThis.offset = () => ownerClientsOffset;
  `, sandbox);

  await next.listener();
  assert.deepEqual(offsets, [50]);
  assert.equal(sandbox.offset(), 50);

  previous.disabled = false;
  await previous.listener();
  assert.deepEqual(offsets, [50, 0]);
  assert.equal(sandbox.offset(), 0);

  next.disabled = true;
  await next.listener();
  assert.deepEqual(offsets, [50, 0]);
});
