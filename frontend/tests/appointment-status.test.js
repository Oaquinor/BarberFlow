"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
const start = source.indexOf("function canMarkAppointmentNoShow(");
const end = source.indexOf("\n}", start) + 2;
const helper = source.slice(start, end);

test("no-show action becomes available only after the scheduled service duration", () => {
  const sandbox = {};
  vm.runInNewContext(`${helper}\nthis.canMarkAppointmentNoShow = canMarkAppointmentNoShow;`, sandbox);
  const appointment = {
    status: "confirmed",
    scheduled_time: "2026-11-20T15:00:00Z",
    estimated_duration: 30,
  };
  const deadline = Date.parse(appointment.scheduled_time) + 30 * 60_000;

  assert.equal(sandbox.canMarkAppointmentNoShow(appointment, deadline - 1), false);
  assert.equal(sandbox.canMarkAppointmentNoShow(appointment, deadline), true);
  assert.equal(sandbox.canMarkAppointmentNoShow({ ...appointment, status: "in_progress" }, deadline), false);
  assert.equal(sandbox.canMarkAppointmentNoShow({ ...appointment, scheduled_time: "invalid" }, deadline), false);
  assert.match(source, /appointment\.status === 'pending' \? `<button class="btn-secondary appointment-status-action"[^`]*data-status="confirmed"/s);
  assert.match(source, /canMarkAppointmentNoShow\(appointment\).*data-status="no_show"/s);
  assert.match(source, /class="btn-secondary appointment-payment" type="button" data-appointment-id="\$\{Number\(appointment\.id\)\}"/);
  assert.match(source, /const appointmentId = Number\(paymentBtn\.dataset\.appointmentId\);[\s\S]*collectAppointmentPayment\(appointmentId\);/);
});

function getAppointmentClickHandler() {
  const registration = source.match(
    /document\.getElementById\('appointmentsList'\)\?\.addEventListener\('click', async \(event\) => \{[\s\S]*?\n\}\);/,
  )?.[0];
  assert.ok(registration, "appointment actions must use the external delegated handler");
  let handler;
  const sandbox = {
    document: { getElementById: () => ({ addEventListener(_name, callback) { handler = callback; } }) },
    updateAppointmentStatus(...args) { sandbox.statusUpdate = args; },
    collectAppointmentPayment(...args) { sandbox.payment = args; },
    showConfirmation: async () => true,
  };
  vm.runInNewContext(registration, sandbox);
  return { handler, sandbox };
}

test("delegated appointment actions update status and collect payment", async () => {
  const { handler, sandbox } = getAppointmentClickHandler();
  const statusButton = {
    dataset: { appointmentId: "42", status: "confirmed" },
    closest(selector) { return selector === ".appointment-status-action" ? this : null; },
  };
  await handler({ target: statusButton });
  assert.deepEqual(sandbox.statusUpdate, [42, "confirmed"]);

  const paymentButton = {
    dataset: { appointmentId: "42" },
    closest(selector) { return selector === ".appointment-payment" ? this : null; },
  };
  await handler({ target: paymentButton });
  assert.deepEqual(sandbox.payment, [42]);
});

test("delegated no-show action still requires confirmation", async () => {
  const { handler, sandbox } = getAppointmentClickHandler();
  sandbox.showConfirmation = async () => false;
  const noShowButton = {
    dataset: { appointmentId: "42", status: "no_show" },
    closest(selector) { return selector === ".appointment-status-action" ? this : null; },
  };
  await handler({ target: noShowButton });
  assert.equal(sandbox.statusUpdate, undefined);
});

test("appointment rendering escapes untrusted names and status labels", () => {
  const helpersEnd = source.indexOf("\nfunction applyBranding(");
  const rendererStart = source.indexOf("function renderAppointmentDay(");
  const rendererEnd = source.indexOf("\nfunction businessTodayDate(", rendererStart);
  assert.ok(helpersEnd > 0 && rendererStart > helpersEnd && rendererEnd > rendererStart);

  const elements = {
    appointmentsList: { innerHTML: "", hidden: false },
    appointmentsCalendarViewport: { hidden: false },
    appointmentsAnchorDate: { value: "" },
  };
  const sandbox = {
    currentUser: { role: "barbershop_owner" },
    barbershopProfile: { currency: "DOP", timezone: "America/Santo_Domingo" },
    appointmentWorkspaceMode: "agenda",
    latestAppointmentDay: [],
    document: { getElementById: (id) => elements[id] || null },
    setText() {},
  };
  const renderers = [
    source.slice(source.indexOf("function escapeHtml("), helpersEnd),
    source.slice(rendererStart, rendererEnd),
    "this.renderAppointmentDay = renderAppointmentDay;",
  ].join("\n");
  vm.runInNewContext(renderers, sandbox);

  sandbox.renderAppointmentDay("2026-11-20", [{
    id: 42,
    status: '<img src=x onerror="alert(1)">',
    scheduled_time: "2026-11-20T15:00:00Z",
    estimated_duration: 30,
    client_name: '<svg onload="alert(2)">Cliente',
    service_type: '</p><img src=x onerror="alert(3)">',
    service_price: 1500,
  }]);

  const markup = elements.appointmentsList.innerHTML;
  assert.match(markup, /&lt;svg onload=&quot;alert\(2\)&quot;&gt;Cliente/);
  assert.match(markup, /&lt;\/p&gt;&lt;img src=x onerror=&quot;alert\(3\)&quot;&gt;/);
  assert.match(markup, /&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.doesNotMatch(markup, /<(?:svg|img)\b/i);
});
