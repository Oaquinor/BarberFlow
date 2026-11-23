"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadOwnerClients()");
const end = source.indexOf("\ndocument.getElementById('previousOwnerClients')", start);
assert.ok(start >= 0 && end > start, "could not isolate owner client loading");
const loadOwnerClientsSource = source.slice(start, end);

function createSandbox(ownerFetch) {
  const elements = {
    ownerClientsBody: { innerHTML: "", textContent: "", replaceChildren() { this.innerHTML = ""; } },
    ownerClientsResult: { textContent: "" },
    ownerClientsPage: { textContent: "" },
    previousOwnerClients: { disabled: true },
    nextOwnerClients: { disabled: true },
  };
  const sandbox = {
    API_ROOT: "https://api.example.test",
    currentUser: { role: "barbershop_owner" },
    ownerFetch,
    ownerClientCache: new Map(),
    OWNER_CLIENTS_PAGE_SIZE: 50,
    ownerClientsOffset: 0,
    ownerClientsSearch: "",
    ownerClientsRequestId: 0,
    URLSearchParams,
    barbershopProfile: { timezone: "America/Santo_Domingo", currency: "DOP" },
    document: { getElementById: (id) => elements[id] || null },
    escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, ""),
    fmtMoneyFromCents: (value) => String(value),
    elements,
  };
  vm.runInNewContext(loadOwnerClientsSource, sandbox);
  return sandbox;
}

test("owner client search is encoded in the tenant-scoped paginated request", async () => {
  const calls = [];
  const sandbox = createSandbox(async (url) => {
    calls.push(url);
    return { items: [], total: 0 };
  });
  sandbox.ownerClientsSearch = "Ana & Juan";

  await sandbox.loadOwnerClients();

  assert.equal(calls.length, 1);
  assert.match(calls[0], /\/owner\/clients\?/);
  assert.match(calls[0], /limit=50/);
  assert.match(calls[0], /offset=0/);
  assert.match(calls[0], /search=Ana\+%26\+Juan/);
  assert.equal(sandbox.elements.ownerClientsResult.textContent, "0 cliente(s) coinciden con la búsqueda");
});

test("a stale client search response cannot replace newer results", async () => {
  const pending = [];
  const sandbox = createSandbox((url) => new Promise((resolve) => pending.push({ url, resolve })));
  sandbox.ownerClientsSearch = "old";
  const oldRequest = sandbox.loadOwnerClients();
  sandbox.ownerClientsSearch = "new";
  const newRequest = sandbox.loadOwnerClients();
  const row = {
    id: 7, full_name: "New Result", phone: "8095550101", appointment_count: 0,
    completed_count: 0, last_visit: null, total_paid_cents: 0, is_active: true,
  };

  pending[1].resolve({ items: [row], total: 1 });
  await newRequest;
  pending[0].resolve({ items: [], total: 0 });
  await oldRequest;

  assert.match(sandbox.elements.ownerClientsBody.innerHTML, /New Result/);
  assert.doesNotMatch(sandbox.elements.ownerClientsBody.innerHTML, /Old Result/);
  assert.equal(sandbox.elements.ownerClientsPage.textContent, "Clientes 1–1 de 1");
});
