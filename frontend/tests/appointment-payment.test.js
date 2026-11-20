"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("let pendingAppointmentPaymentId = null;");
const end = source.indexOf("\nlet cashBusinessDate = null;", start);
const checkout = source.slice(start, end);

function createCheckout() {
  const listeners = new Map();
  const elements = Object.fromEntries([
    "appointmentPaymentDialog", "appointmentPaymentForm", "appointmentPaymentResult",
    "appointmentPaymentMethod", "submitAppointmentPayment", "cancelAppointmentPayment",
  ].map((id) => [id, { id, textContent: "", value: "cash", hidden: false, disabled: false }]));
  elements.appointmentPaymentDialog.showModal = () => { elements.appointmentPaymentDialog.open = true; };
  elements.appointmentPaymentDialog.close = () => {
    elements.appointmentPaymentDialog.open = false;
    listeners.get("appointmentPaymentDialog.close")?.();
  };
  elements.appointmentPaymentDialog.addEventListener = (name, handler) => listeners.set(`appointmentPaymentDialog.${name}`, handler);
  elements.cancelAppointmentPayment.addEventListener = (name, handler) => listeners.set(`cancelAppointmentPayment.${name}`, handler);
  elements.appointmentPaymentForm.addEventListener = (name, handler) => listeners.set(`appointmentPaymentForm.${name}`, handler);
  elements.appointmentPaymentForm.reset = () => { elements.appointmentPaymentMethod.value = "cash"; };
  elements.appointmentPaymentMethod.focus = () => { elements.appointmentPaymentMethod.focused = true; };
  elements.appointmentPaymentForm.hidden = false;
  elements.submitAppointmentPayment.disabled = false;
  elements.cancelAppointmentPayment.textContent = "Cancelar";
  const calls = [];
  const sandbox = {
    document: {
      getElementById: (id) => elements[id] || null,
    },
    KingFlowAuth: { fetch: async (...args) => { calls.push(args); return sandbox.response; } },
    API_ROOT: "https://api.kingflow.test",
    fmtMoneyFromCents: (cents) => `DOP ${(cents / 100).toFixed(2)}`,
    loadBarberDashboardData: async () => { sandbox.dashboardRefreshes += 1; },
    loadCashSummary: async () => { sandbox.cashRefreshes += 1; },
    dashboardRefreshes: 0,
    cashRefreshes: 0,
    response: { ok: true, json: async () => ({ total_cents: 1500, currency: "DOP" }) },
    console: { error() {} },
  };
  vm.runInNewContext(`${checkout}\nthis.collectAppointmentPayment = collectAppointmentPayment;`, sandbox);
  return { sandbox, elements, listeners, calls };
}

test("checkout opens an accessible method selector and records one payment", async () => {
  const { sandbox, elements, listeners, calls } = createCheckout();
  sandbox.collectAppointmentPayment(42);

  assert.equal(elements.appointmentPaymentDialog.open, true);
  assert.equal(elements.appointmentPaymentMethod.focused, true);
  elements.appointmentPaymentMethod.value = "transfer";
  await listeners.get("appointmentPaymentForm.submit")({ preventDefault() {} });

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://api.kingflow.test/api/v1/barber/appointments/42/payment");
  assert.deepEqual(JSON.parse(calls[0][1].body), { method: "transfer", tip_cents: 0 });
  assert.equal(elements.appointmentPaymentForm.hidden, true);
  assert.match(elements.appointmentPaymentResult.textContent, /servicio quedó finalizado/);
  assert.equal(sandbox.dashboardRefreshes, 1);
  assert.equal(sandbox.cashRefreshes, 1);
});

test("a rejected checkout remains open and can be retried after correction", async () => {
  const { sandbox, elements, listeners, calls } = createCheckout();
  sandbox.response = { ok: false, json: async () => ({ detail: "La caja ya fue cerrada" }) };
  sandbox.collectAppointmentPayment(9);
  await listeners.get("appointmentPaymentForm.submit")({ preventDefault() {} });

  assert.equal(calls.length, 1);
  assert.equal(elements.appointmentPaymentDialog.open, true);
  assert.equal(elements.appointmentPaymentForm.hidden, false);
  assert.equal(elements.submitAppointmentPayment.disabled, false);
  assert.equal(elements.appointmentPaymentResult.textContent, "La caja ya fue cerrada");
  assert.equal(sandbox.dashboardRefreshes, 0);
});

test("closing checkout clears its appointment and form state", () => {
  const { sandbox, elements } = createCheckout();
  sandbox.collectAppointmentPayment(9);
  elements.appointmentPaymentForm.hidden = true;
  elements.appointmentPaymentDialog.close();

  assert.equal(elements.appointmentPaymentForm.hidden, false);
  assert.equal(elements.appointmentPaymentResult.textContent, "");
  assert.equal(elements.cancelAppointmentPayment.textContent, "Cancelar");
  sandbox.collectAppointmentPayment(0);
  assert.equal(elements.appointmentPaymentDialog.open, false);
});
