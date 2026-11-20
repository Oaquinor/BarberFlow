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
    /document\.getElementById\('appointmentsList'\)\?\.addEventListener\('click', \(event\) => \{[\s\S]*?\n\}\);/,
  )?.[0];
  assert.ok(registration, "appointment actions must use the external delegated handler");
  let handler;
  const sandbox = {
    document: { getElementById: () => ({ addEventListener(_name, callback) { handler = callback; } }) },
    updateAppointmentStatus(...args) { sandbox.statusUpdate = args; },
    collectAppointmentPayment(...args) { sandbox.payment = args; },
    window: { confirm: () => true },
  };
  vm.runInNewContext(registration, sandbox);
  return { handler, sandbox };
}

test("delegated appointment actions update status and collect payment", () => {
  const { handler, sandbox } = getAppointmentClickHandler();
  const statusButton = {
    dataset: { appointmentId: "42", status: "confirmed" },
    closest(selector) { return selector === ".appointment-status-action" ? this : null; },
  };
  handler({ target: statusButton });
  assert.deepEqual(sandbox.statusUpdate, [42, "confirmed"]);

  const paymentButton = {
    dataset: { appointmentId: "42" },
    closest(selector) { return selector === ".appointment-payment" ? this : null; },
  };
  handler({ target: paymentButton });
  assert.deepEqual(sandbox.payment, [42]);
});

test("delegated no-show action still requires confirmation", () => {
  const { handler, sandbox } = getAppointmentClickHandler();
  sandbox.window.confirm = () => false;
  const noShowButton = {
    dataset: { appointmentId: "42", status: "no_show" },
    closest(selector) { return selector === ".appointment-status-action" ? this : null; },
  };
  handler({ target: noShowButton });
  assert.equal(sandbox.statusUpdate, undefined);
});
