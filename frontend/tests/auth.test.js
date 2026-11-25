const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(path.join(__dirname, "..", "js", "auth.js"), "utf8");
const dashboardSource = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

test("auth tokens stay in session storage and refresh after an expired access token", async () => {
  const localStorage = createStorage({ token: "legacy-access", refresh_token: "legacy-refresh" });
  const sessionStorage = createStorage();
  const requests = [];
  const sandbox = {
    localStorage,
    sessionStorage,
    Headers,
    Event,
    fetch: async (input, options = {}) => {
      requests.push({ input: String(input), options });
      if (String(input).endsWith("/auth/refresh")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ access_token: "new-access", refresh_token: "new-refresh" }),
        };
      }
      if (requests.filter((request) => !request.input.endsWith("/auth/refresh")).length === 1) {
        return { ok: false, status: 401 };
      }
      return { ok: true, status: 200 };
    },
    window: {
      KINGFLOW_CONFIG: {},
      location: { origin: "https://kingflow.test" },
      dispatchEvent() {},
    },
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  sandbox.window.KingFlowAuth.setTokens("old-access", "old-refresh");

  const response = await sandbox.window.KingFlowAuth.fetch("https://kingflow.test/api/private");

  assert.equal(response.status, 200);
  assert.equal(localStorage.getItem("token"), null);
  assert.equal(localStorage.getItem("refresh_token"), null);
  assert.equal(sessionStorage.getItem("token"), "new-access");
  assert.equal(sessionStorage.getItem("refresh_token"), "new-refresh");
  assert.equal(requests[0].options.headers.get("Authorization"), "Bearer old-access");
  assert.equal(requests[2].options.headers.get("Authorization"), "Bearer new-access");

  await sandbox.window.KingFlowAuth.logout();
  assert.equal(sessionStorage.getItem("token"), null);
  assert.equal(sessionStorage.getItem("refresh_token"), null);
});

test("expired refresh credentials emit the session-expired event", async () => {
  const sessionStorage = createStorage();
  const events = [];
  const sandbox = {
    localStorage: createStorage(),
    sessionStorage,
    Headers,
    Event,
    fetch: async () => ({ ok: false, status: 401 }),
    window: {
      KINGFLOW_CONFIG: {},
      location: { origin: "https://kingflow.test" },
      dispatchEvent(event) { events.push(event.type); },
    },
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  sandbox.window.KingFlowAuth.setTokens("expired-access", "expired-refresh");

  const response = await sandbox.window.KingFlowAuth.fetch("https://kingflow.test/api/private");

  assert.equal(response.status, 401);
  assert.deepEqual(events, ["kingflow:auth-expired"]);
  assert.equal(sessionStorage.getItem("token"), null);
  assert.equal(sessionStorage.getItem("refresh_token"), null);
});

test("temporary refresh server failures preserve the local session", async () => {
  const sessionStorage = createStorage();
  const events = [];
  const sandbox = {
    localStorage: createStorage(),
    sessionStorage,
    Headers,
    Event,
    fetch: async (input) => String(input).endsWith("/auth/refresh")
      ? ({ ok: false, status: 503 })
      : ({ ok: false, status: 401 }),
    window: {
      KINGFLOW_CONFIG: {},
      location: { origin: "https://kingflow.test" },
      dispatchEvent(event) { events.push(event.type); },
    },
  };
  vm.runInNewContext(authSource, sandbox, { filename: "auth.js" });
  sandbox.window.KingFlowAuth.setTokens("access", "refresh");

  const response = await sandbox.window.KingFlowAuth.fetch("https://kingflow.test/api/private");

  assert.equal(response.status, 401);
  assert.equal(sessionStorage.getItem("token"), "access");
  assert.equal(sessionStorage.getItem("refresh_token"), "refresh");
  assert.deepEqual(events, []);
});

test("client role is routed to the customer account instead of the barber dashboard", async () => {
  const start = dashboardSource.indexOf("async function initializeAuthenticatedDashboard(");
  const end = dashboardSource.indexOf("\nasync function restoreAuthenticatedSession()", start);
  assert.ok(start >= 0 && end > start);
  let destination = null;
  const sandbox = {
    window: { location: { replace(value) { destination = value; } } },
    sessionStorage: createStorage(),
  };
  vm.runInNewContext(dashboardSource.slice(start, end), sandbox);
  await sandbox.initializeAuthenticatedDashboard({ role: "client" });
  assert.equal(destination, "/client-account.html");
});
