"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");

function sourceFor(name, nextName) {
  const start = source.indexOf(`async function ${name}()`);
  const asyncEnd = source.indexOf(`\nasync function ${nextName}()`, start);
  const syncEnd = source.indexOf(`\nfunction ${nextName}(`, start);
  const end = asyncEnd < 0 ? syncEnd : syncEnd < 0 ? asyncEnd : Math.min(asyncEnd, syncEnd);
  assert.ok(start >= 0 && end > start, `could not isolate ${name}`);
  return source.slice(start, end);
}

test("notification badge refresh reads the count-only tenant endpoint", async () => {
  const calls = [];
  const count = { textContent: "0" };
  const sandbox = {
    API_ROOT: "https://api.example.test",
    currentUser: { id: 7 },
    document: { getElementById: (id) => (id === "notificationUnreadCount" ? count : null) },
    KingFlowAuth: {
      fetch: async (url) => {
        calls.push(url);
        return { ok: true, json: async () => ({ unread_count: 4 }) };
      },
    },
  };
  vm.runInNewContext(sourceFor("loadNotificationUnreadCount", "refreshNotificationInbox"), sandbox);

  await sandbox.loadNotificationUnreadCount();

  assert.deepEqual(calls, ["https://api.example.test/api/v1/notifications/unread-count"]);
  assert.equal(count.textContent, "4");
});

test("periodic notification refresh loads the full inbox only while it is open", async () => {
  const panel = { hidden: true };
  const sandbox = {
    document: { getElementById: (id) => (id === "inAppNotificationInbox" ? panel : null) },
  };
  vm.runInNewContext(`
    let fullLoads = 0;
    let countLoads = 0;
    async function loadNotificationInbox() { fullLoads += 1; }
    async function loadNotificationUnreadCount() { countLoads += 1; }
    ${sourceFor("refreshNotificationInbox", "resetSessionInterface")}
    globalThis.metrics = () => ({ fullLoads, countLoads });
  `, sandbox);

  await sandbox.refreshNotificationInbox();
  assert.equal(sandbox.metrics().fullLoads, 0);
  assert.equal(sandbox.metrics().countLoads, 1);

  panel.hidden = false;
  await sandbox.refreshNotificationInbox();
  assert.equal(sandbox.metrics().fullLoads, 1);
  assert.equal(sandbox.metrics().countLoads, 1);
});
