"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadOwnerClientHistory()");
const end = source.indexOf("\ndocument.getElementById('previousOwnerClientHistory')", start);
assert.ok(start >= 0 && end > start, "could not isolate client history loading");
const historySource = source.slice(start, end);

function createSandbox(ownerFetch) {
  const elements = {
    ownerClientHistoryDialog: { open: true },
    ownerClientHistoryItems: { innerHTML: "", textContent: "", replaceChildren() { this.innerHTML = ""; } },
    ownerClientHistoryResult: { textContent: "" },
    ownerClientHistoryPage: { textContent: "" },
    previousOwnerClientHistory: { disabled: true },
    nextOwnerClientHistory: { disabled: true },
  };
  const sandbox = {
    currentUser: { role: "barbershop_owner" },
    ownerClientHistoryClientId: 42,
    ownerClientHistoryOffset: 0,
    ownerClientHistoryRequestId: 0,
    OWNER_CLIENT_HISTORY_PAGE_SIZE: 20,
    URLSearchParams,
    ownerFetch,
    document: { getElementById: (id) => elements[id] || null },
    barbershopProfile: { timezone: "America/Santo_Domingo", currency: "DOP" },
    fmtMoneyFromCents: (value) => `DOP ${Number(value) / 100}`,
    escapeHtml: (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]),
    elements,
  };
  vm.runInNewContext(historySource, sandbox);
  return sandbox;
}

test("owner client history requests only the selected client within the owner API", async () => {
  const calls = [];
  const sandbox = createSandbox(async (url) => {
    calls.push(url);
    return { items: [], total: 0 };
  });

  await sandbox.loadOwnerClientHistory();

  assert.deepEqual(calls, ["/owner/clients/42/appointments?limit=20&offset=0"]);
  assert.equal(sandbox.elements.ownerClientHistoryPage.textContent, "0 citas");
});

test("client history displays stored payments and escapes untrusted service names", async () => {
  const sandbox = createSandbox(async () => ({
    total: 1,
    items: [{
      id: 9,
      scheduled_time: "2026-11-20T13:00:00Z",
      status: "completed",
      service_type: "<img src=x onerror=alert(1)>",
      estimated_duration: 30,
      actual_duration: 28,
      service_price_cents: 2500,
      barber_name: "Ana Barber",
      payment: {
        amount_cents: 2500, tip_cents: 500, currency: "DOP",
        method: "cash", received_at: "2026-11-20T13:30:00Z",
      },
    }],
  }));

  await sandbox.loadOwnerClientHistory();

  const rendered = sandbox.elements.ownerClientHistoryItems.innerHTML;
  assert.match(rendered, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(rendered, /<img src=x/);
  assert.match(rendered, /Barbero: Ana Barber/);
  assert.match(rendered, /DOP 30/);
  assert.equal(sandbox.elements.ownerClientHistoryPage.textContent, "Citas 1–1 de 1");
});
