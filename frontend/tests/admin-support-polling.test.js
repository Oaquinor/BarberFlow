"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
const start = source.indexOf("async function refreshOpenSupportTicketCount");
const end = source.indexOf("async function loadSupportTickets", start);
assert.ok(start >= 0 && end > start, "could not isolate support ticket alert polling");

function createPollingHarness(filter = "open") {
  const counter = { textContent: "" };
  const statusFilter = { value: filter };
  const tickets = [
    { total: 0, items: [] },
    { total: 1, items: [{ id: 12 }] },
    { total: 1, items: [{ id: 12 }] },
  ];
  const messages = [];
  const sandbox = {
    listRefreshes: 0,
    document: {
      visibilityState: "visible",
      getElementById(id) {
        return { supportOpenCount: counter, supportTicketFilter: statusFilter }[id] || null;
      },
    },
    fetchJson: async () => tickets.shift(),
    showToast: (message) => messages.push(message),
  };
  vm.runInNewContext(`
    const document = globalThis.document;
    const fetchJson = globalThis.fetchJson;
    const showToast = globalThis.showToast;
    let latestOpenSupportTicketId = null;
    let supportAlertsInitialized = false;
    let supportAlertsRefreshing = false;
    let supportTicketsOffset = 50;
    const SUPPORT_TICKETS_PAGE_SIZE = 50;
    async function loadSupportTickets() { globalThis.listRefreshes += 1; }
    ${source.slice(start, end)}
    globalThis.refresh = refreshOpenSupportTicketCount;
    globalThis.offset = () => supportTicketsOffset;
  `, sandbox);
  return { sandbox, counter, messages };
}

test("new open support ticket updates the admin counter, alerts, and refreshes open list", async () => {
  const harness = createPollingHarness("open");
  await harness.sandbox.refresh();
  assert.equal(harness.counter.textContent, "Solicitudes abiertas: 0");

  await harness.sandbox.refresh(true);

  assert.equal(harness.counter.textContent, "Solicitudes abiertas: 1");
  assert.deepEqual(harness.messages, ["Llegó una nueva solicitud a la bandeja de soporte."]);
  assert.equal(harness.sandbox.offset(), 0);
  assert.equal(harness.sandbox.listRefreshes, 1);

  await harness.sandbox.refresh(true);
  assert.equal(harness.messages.length, 1);
  assert.equal(harness.sandbox.listRefreshes, 1);
});

test("new open support ticket alerts without replacing a different status filter", async () => {
  const harness = createPollingHarness("resolved");
  await harness.sandbox.refresh();
  await harness.sandbox.refresh(true);

  assert.equal(harness.sandbox.offset(), 50);
  assert.equal(harness.sandbox.listRefreshes, 0);
  assert.equal(harness.messages.length, 1);
});
