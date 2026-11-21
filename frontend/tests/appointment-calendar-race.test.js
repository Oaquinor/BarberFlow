"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("async function loadAppointmentsForDate(");
const end = source.indexOf("\nfunction changeAppointmentsDate(", start);
const functionSource = source.slice(start, end);

function createCalendarLoader() {
  const pending = [];
  const rendered = [];
  const errors = [];
  const sandbox = {
    accessToken: "test-token",
    API_ROOT: "https://api.kingflow.test",
    selectedAppointmentsDate: null,
    selectedAppointmentsView: "day",
    appointmentsRequestSequence: 0,
    KingFlowAuth: {
      fetch(url) {
        return new Promise((resolve) => pending.push({ url, resolve }));
      },
    },
    renderAppointmentDay(date, appointments) { rendered.push({ date, appointments }); },
    renderAppointmentCalendar(data) { rendered.push(data); },
    setText(id, text) { errors.push({ id, text }); },
    document: {
      getElementById(id) {
        return id === "appointmentsAnchorDate" ? { value: "" } : null;
      },
    },
  };
  vm.runInNewContext(`${functionSource}\nthis.loadAppointmentsForDate = loadAppointmentsForDate;`, sandbox);
  return { sandbox, pending, rendered, errors };
}

function okResponse(data) {
  return { ok: true, async json() { return data; } };
}

test("a slower previous day response cannot replace the selected agenda", async () => {
  const loader = createCalendarLoader();
  const older = loader.sandbox.loadAppointmentsForDate("2026-11-20");
  const newer = loader.sandbox.loadAppointmentsForDate("2026-11-21");
  assert.match(loader.pending[0].url, /target_date=2026-11-20/);
  assert.match(loader.pending[1].url, /target_date=2026-11-21/);
  loader.errors.length = 0;

  loader.pending[1].resolve(okResponse({ business_date: "2026-11-21", appointments: ["new"] }));
  await newer;
  loader.pending[0].resolve(okResponse({ business_date: "2026-11-20", appointments: ["old"] }));
  await older;

  assert.deepEqual(loader.rendered, [{ date: "2026-11-21", appointments: ["new"] }]);
  assert.deepEqual(loader.errors, []);
});

test("a stale agenda request failure does not replace the current view with an error", async () => {
  const loader = createCalendarLoader();
  const older = loader.sandbox.loadAppointmentsForDate("2026-11-20");
  const newer = loader.sandbox.loadAppointmentsForDate("2026-11-21");
  loader.errors.length = 0;

  loader.pending[1].resolve(okResponse({ business_date: "2026-11-21", appointments: [] }));
  await newer;
  loader.pending[0].resolve({ ok: false, async json() { return { detail: "old failure" }; } });
  await older;

  assert.deepEqual(loader.errors, []);
  assert.deepEqual(loader.rendered, [{ date: "2026-11-21", appointments: [] }]);
});

test("a stale dashboard response cannot overwrite current appointment statistics", async () => {
  const pending = [];
  const updates = [];
  const sandbox = {
    accessToken: "test-token",
    API_ROOT: "https://api.kingflow.test",
    dashboardRequestSequence: 0,
    KingFlowAuth: { fetch: () => new Promise((resolve) => pending.push(resolve)) },
    setText: (...args) => updates.push(args),
    console: { error() {} },
  };
  const start = source.indexOf("async function loadBarberDashboardData()");
  const end = source.indexOf("\nasync function ownerFetch(", start);
  vm.runInNewContext(`${source.slice(start, end)}\nthis.loadBarberDashboardData = loadBarberDashboardData;`, sandbox);

  const staleRequest = sandbox.loadBarberDashboardData();
  sandbox.loadBarberDashboardData();
  pending[0]({ ok: true, async json() { return { summary: { total: 1 } }; } });
  await staleRequest;

  assert.deepEqual(updates, []);
});

test("a stale cash summary cannot overwrite the latest reconciliation", async () => {
  const pending = [];
  const updates = [];
  const sandbox = {
    accessToken: "test-token",
    API_ROOT: "https://api.kingflow.test",
    cashSummaryRequestSequence: 0,
    KingFlowAuth: { fetch: () => new Promise((resolve) => pending.push(resolve)) },
    setText: (...args) => updates.push(args),
    console: { error() {} },
  };
  const start = source.indexOf("async function loadCashSummary()");
  const end = source.indexOf("\ndocument.getElementById('cashCloseForm')", start);
  vm.runInNewContext(`${source.slice(start, end)}\nthis.loadCashSummary = loadCashSummary;`, sandbox);

  const staleRequest = sandbox.loadCashSummary();
  sandbox.loadCashSummary();
  pending[0]({ ok: true, async json() { return { total_cents: 12500 }; } });
  await staleRequest;

  assert.deepEqual(updates, []);
});
