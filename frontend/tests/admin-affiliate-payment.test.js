"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
const start = source.indexOf("document.getElementById('affiliateCommissionsBody')?.addEventListener('click'");
const end = source.indexOf("document.getElementById('loadAffiliateCommissionsBtn')", start);
const paymentHandler = source.slice(start, end);

function createHandler({ fetchJson = async () => ({}) } = {}) {
  const calls = [];
  const result = { textContent: "" };
  const method = { value: "bank_transfer" };
  const reference = { value: "  ref-123  " };
  const row = { querySelector: (selector) => selector.includes("method") ? method : reference };
  const button = {
    dataset: { action: "pay", id: "31" },
    disabled: false,
    closest: (selector) => selector === "tr" ? row : null,
  };
  let listener;
  const sandbox = {
    document: {
      getElementById: () => result,
    },
    fetchJson: async (...args) => { calls.push(args); return fetchJson(...args); },
    loadAffiliateCommissions: async () => { sandbox.commissionRefreshes += 1; },
    loadAffiliates: async () => { sandbox.affiliateRefreshes += 1; },
    commissionRefreshes: 0,
    affiliateRefreshes: 0,
    window: { prompt() { throw new Error("Native prompt must not be used"); } },
  };
  sandbox.document.getElementById = (id) => id === "affiliateCommissionsBody" ? { addEventListener: (_, handler) => { listener = handler; } }
    : id === "affiliateCommissionResult" ? result : null;
  vm.runInNewContext(paymentHandler, sandbox);
  return { calls, result, button, method, reference, sandbox, click: () => listener({ target: { closest: () => button } }) };
}

test("affiliate commission payout uses row controls and records the selected method and reference", async () => {
  const state = createHandler();
  await state.click();

  assert.equal(state.calls.length, 1);
  assert.equal(state.calls[0][0], "/api/v1/admin/commissions/31/pay");
  assert.deepEqual(JSON.parse(state.calls[0][1].body), {
    payment_method: "bank_transfer",
    payment_reference: "ref-123",
  });
  assert.equal(state.sandbox.commissionRefreshes, 1);
  assert.equal(state.sandbox.affiliateRefreshes, 1);
});

test("failed affiliate payout keeps the row action available and reports the error", async () => {
  const state = createHandler({ fetchJson: async () => { throw new Error("No se pudo guardar"); } });
  await state.click();

  assert.equal(state.button.disabled, false);
  assert.equal(state.result.textContent, "No se pudo guardar");
  assert.equal(state.sandbox.commissionRefreshes, 0);
});

test("affiliate payment options match the backend payment contract", () => {
  assert.match(source, /commission-payment-method[\s\S]*bank_transfer[\s\S]*cash[\s\S]*card[\s\S]*other/);
  assert.doesNotMatch(source, /window\.prompt\(/);
});

test("subscription period end includes the selected UTC calendar day", async () => {
  const start = source.indexOf("async function saveSubscription() {");
  const end = source.indexOf("document.getElementById('subscriptionPaymentForm')", start);
  const handler = source.slice(start, end);
  const values = {
    subscriptionTenantSelect: { value: "42" },
    subscriptionResult: { textContent: "" },
    subPlan: { value: "basic" },
    subStatus: { value: "active" },
    subAutoRenew: { value: "false" },
    subPeriodEnd: { value: "2026-11-20" },
  };
  const calls = [];
  const sandbox = {
    document: { getElementById: id => values[id] || null },
    fetchJson: async (...args) => {
      calls.push(args);
      return { plan: "basic", status: "active", current_period_end: "2026-11-20T23:59:59Z" };
    },
    loadTenants: async () => {},
  };
  vm.runInNewContext(`${handler}\nsaveSubscription();`, sandbox);
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/v1/admin/tenants/42/subscription");
  assert.equal(JSON.parse(calls[0][1].body).current_period_end, "2026-11-20T23:59:59Z");
});
