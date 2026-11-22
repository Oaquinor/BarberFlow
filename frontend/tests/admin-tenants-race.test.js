"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
const start = source.indexOf("async function loadTenants() {");
const end = source.indexOf("function renderToggle", start);
const loader = source.slice(start, end);

function createSelect(value) {
  return {
    options: [{ value: "", textContent: "placeholder" }, { value, textContent: "stale tenant" }],
    _value: value,
    get value() { return this._value; },
    set value(next) { this._value = this.options.some((option) => option.value === next) ? next : ""; },
    replaceChildren(...options) { this.options = options; this._value = options[0]?.value || ""; },
    add(option) { this.options.push(option); },
  };
}

function createHarness() {
  const pending = [];
  const tenantsBody = { innerHTML: "" };
  const tenantsEmpty = { style: { display: "none" } };
  const tenantsCount = { textContent: "" };
  const elements = {
    tenantsBody,
    tenantsEmpty,
    tenantsCount,
    tenantFilter: createSelect("99"),
    subscriptionTenantSelect: createSelect("2"),
    subscriptionPaymentCurrency: { textContent: "" },
    auditTenantFilter: createSelect("99"),
  };
  const sandbox = {
    currentTenants: [],
    tenantsRequestSequence: 0,
    document: { getElementById: (id) => elements[id] },
    Option: class Option { constructor(textContent, value) { this.textContent = textContent; this.value = value; } },
    fetchJson: () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
    escapeHtml: (value) => String(value ?? ""),
    renderTenantPill: (active) => active ? "Activo" : "Inactivo",
    console: { error() {} },
  };
  vm.runInNewContext(loader, sandbox);
  vm.runInNewContext("globalThis.updateCurrency = updateSubscriptionPaymentCurrency;", sandbox);
  return { sandbox, elements, pending };
}

test("latest tenant refresh wins and stale tenant options are removed", async () => {
  const state = createHarness();
  const oldRequest = state.sandbox.loadTenants();
  const latestRequest = state.sandbox.loadTenants();
  const tenant = {
    barbershop_id: 2, barbershop_name: "Nueva barbería", slug: "nueva",
    currency: "DOP", owner_email: "owner@example.com", plan: "free", subscription_status: "active", active: true,
  };

  state.pending[1].resolve({ items: [tenant] });
  await latestRequest;
  state.pending[0].resolve({ items: [{ ...tenant, barbershop_id: 99, barbershop_name: "Respuesta vieja" }] });
  await oldRequest;

  assert.equal(state.sandbox.currentTenants[0].barbershop_name, "Nueva barbería");
  assert.match(state.elements.tenantsBody.innerHTML, /Nueva barbería/);
  assert.doesNotMatch(state.elements.tenantsBody.innerHTML, /Respuesta vieja/);
  assert.deepEqual(Array.from(state.elements.tenantFilter.options, (option) => option.value), ["", "2"]);
  assert.deepEqual(Array.from(state.elements.auditTenantFilter.options, (option) => option.value), ["", "2"]);
  assert.deepEqual(Array.from(state.elements.subscriptionTenantSelect.options, (option) => option.value), ["", "2"]);
  assert.equal(state.elements.subscriptionTenantSelect.value, "2");
  assert.equal(state.elements.subscriptionPaymentCurrency.textContent, "DOP");
  state.elements.subscriptionTenantSelect.value = "";
  state.sandbox.updateCurrency();
  assert.equal(state.elements.subscriptionPaymentCurrency.textContent, "moneda del negocio");
  state.elements.subscriptionTenantSelect.value = "2";
  state.sandbox.updateCurrency();
  assert.equal(state.elements.subscriptionPaymentCurrency.textContent, "DOP");
  assert.equal(state.elements.tenantFilter.value, "");
});
