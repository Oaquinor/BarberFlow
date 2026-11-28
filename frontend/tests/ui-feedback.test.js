"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const frontend = path.join(__dirname, "..");
const source = fs.readFileSync(path.join(frontend, "js", "ui-feedback.js"), "utf8");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.dataset = {};
    this.className = "";
    this.classList = { toggle: (name, enabled) => { this[name] = enabled; } };
    this.hidden = false;
    this.returnValue = "";
    this.open = false;
  }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes.set(name, value); }
  addEventListener(name, callback, options = {}) {
    const current = this.listeners.get(name) || [];
    current.push({ callback, once: options.once === true });
    this.listeners.set(name, current);
  }
  emit(name, event = {}) {
    const current = this.listeners.get(name) || [];
    this.listeners.set(name, current.filter((listener) => !listener.once));
    for (const listener of current) listener.callback(event);
  }
  showModal() { this.open = true; }
  close(value = "") {
    this.returnValue = value;
    this.open = false;
    this.emit("close");
  }
  focus() { this.focused = true; }
}

function createFeedback() {
  const created = [];
  const body = new FakeElement("body");
  const document = {
    body,
    getElementById() { return null; },
    createElement(tag) {
      const element = new FakeElement(tag);
      created.push(element);
      return element;
    },
  };
  const window = {};
  vm.runInNewContext(source, {
    document,
    window,
    setTimeout: () => 1,
    clearTimeout() {},
  });
  return { body, created, window };
}

test("feedback notices use text, accessible roles, and a shared dismissible toast", () => {
  const { body, created, window } = createFeedback();
  const root = body.children[0];
  const toast = root.children[0];
  const [text, dismiss] = toast.children;

  window.showToast("<img src=x>");
  assert.equal(text.textContent, "<img src=x>");
  assert.equal(toast.attributes.get("role"), "alert");
  assert.equal(toast.hidden, false);
  window.showToast("Guardado", "info");
  assert.equal(toast.attributes.get("role"), "status");
  assert.equal(text.textContent, "Guardado");
  dismiss.emit("click");
  assert.equal(toast.hidden, true);
  assert.ok(created.includes(toast));
});

test("confirmation modal resolves acceptance and cancellation and labels destructive actions", async () => {
  const { body, created, window } = createFeedback();
  const dialog = created.find((element) => element.tagName === "DIALOG");
  const root = body.children[0];
  const toast = root.children[0];
  const dismiss = toast.children[1];
  const modal = root.children[1];
  const [title, message, actions] = modal.children;
  const [cancel, accept] = actions.children;

  const accepted = window.showConfirmation("Borrar reserva", {
    title: "Cancelar cita", confirmLabel: "Cancelar cita", danger: true,
  });
  await Promise.resolve();
  assert.equal(dialog.open, true);
  assert.equal(title.textContent, "Cancelar cita");
  assert.equal(message.textContent, "Borrar reserva");
  assert.equal(accept["app-confirm-danger"], true);
  accept.emit("click");
  assert.equal(await accepted, true);

  const rejected = window.showConfirmation("Guardar cambios");
  await Promise.resolve();
  cancel.emit("click");
  assert.equal(await rejected, false);
  assert.equal(dialog.open, false);
  assert.ok(dismiss);
});

test("all interactive portals load shared feedback before code that calls it", () => {
  for (const page of ["index.html", "admin.html", "client.html", "onboarding.html"]) {
    const html = fs.readFileSync(path.join(frontend, page), "utf8");
    assert.match(html, /css\/tailwind\.css/);
    assert.match(html, /js\/ui-feedback\.js/);
    const utilityPosition = html.indexOf("js/ui-feedback.js");
    for (const script of ["js/main.js", "js/admin.js", "js/client.js", "js/onboarding.js"]) {
      const position = html.indexOf(script);
      if (position !== -1) assert.ok(utilityPosition < position, `${page} loads feedback before ${script}`);
    }
  }
});

test("interactive code no longer depends on browser-native alert and confirm dialogs", () => {
  for (const script of ["main.js", "admin.js", "client.js", "onboarding.js"]) {
    const contents = fs.readFileSync(path.join(frontend, "js", script), "utf8");
    assert.doesNotMatch(contents, /\balert\s*\(|\bwindow\.confirm\s*\(/, script);
  }
});
