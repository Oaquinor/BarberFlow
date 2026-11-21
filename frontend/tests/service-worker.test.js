"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const workerSource = fs.readFileSync(path.join(__dirname, "..", "sw.js"), "utf8");
const pwaSource = fs.readFileSync(path.join(__dirname, "..", "js", "pwa.js"), "utf8");
const securitySource = fs.readFileSync(path.join(__dirname, "..", "js", "security.js"), "utf8");

function createWorker(fetchImpl = async () => ({ status: 200 }), cachePut = async () => {}) {
  const listeners = new Map();
  const writes = [];
  const deletedCaches = [];
  const addedAssets = [];
  const caches = {
    async open(name) {
      return {
        async addAll(assets) { addedAssets.push({ name, assets }); },
        async put(request) { writes.push(request.url); return cachePut(request); },
      };
    },
      async keys() { return ["kingflow-pwa-v5", "kingflow-pwa-v6", "kingflow-pwa-v7", "kingflow-pwa-v8", "kingflow-pwa-v9", "kingflow-pwa-v10", "kingflow-pwa-v11", "kingflow-pwa-v12", "kingflow-pwa-v13", "kingflow-pwa-v14", "kingflow-pwa-v15", "kingflow-pwa-v16", "kingflow-pwa-v17", "kingflow-pwa-v18", "kingflow-pwa-v19", "kingflow-pwa-v20", "kingflow-pwa-v21", "kingflow-pwa-v22", "kingflow-pwa-v23", "kingflow-pwa-v24", "kingflow-pwa-v25", "kingflow-pwa-v26", "kingflow-pwa-v27", "kingflow-pwa-v28", "kingflow-pwa-v29", "kingflow-pwa-v30", "other-product-cache", "kingflow-pwa-old"]; },
    async delete(name) { deletedCaches.push(name); return true; },
    async match(request) { return { matched: String(request) }; },
  };
  const self = {
    location: { origin: "https://kingflow.test" },
    clients: { claim: async () => {} },
    addEventListener(name, callback) { listeners.set(name, callback); },
    skipWaiting() {},
  };
  const sandbox = {
    URL,
    Response,
    caches,
    fetch: fetchImpl,
    self,
  };
  vm.runInNewContext(workerSource, sandbox, { filename: "sw.js" });
  return { listeners, writes, deletedCaches, addedAssets };
}

test("pre-caches app shell and removes only KingFlow caches from older versions", async () => {
  const worker = createWorker();
  let installPromise;
  worker.listeners.get("install")({ waitUntil(promise) { installPromise = promise; } });
  await installPromise;
  assert.equal(worker.addedAssets[0].name, "kingflow-pwa-v31");
  assert.ok(worker.addedAssets[0].assets.includes("/js/main.js?v=20261120-csp-events"));
  assert.ok(worker.addedAssets[0].assets.includes("/js/offline.js"));
  assert.ok(worker.addedAssets[0].assets.includes("/js/client.js"));
  assert.ok(worker.addedAssets[0].assets.includes("/css/styles.css"));
  assert.ok(worker.addedAssets[0].assets.includes("/css/auth-pages.css"));
  assert.ok(worker.addedAssets[0].assets.includes("/css/ui-feedback.css"));
  assert.ok(worker.addedAssets[0].assets.includes("/js/ui-feedback.js"));
  for (const asset of worker.addedAssets[0].assets) {
    const relativePath = asset === "/" ? "index.html" : asset.slice(1).split("?", 1)[0];
    assert.ok(fs.existsSync(path.join(__dirname, "..", relativePath)), `${asset} must exist`);
  }

  let activatePromise;
  worker.listeners.get("activate")({ waitUntil(promise) { activatePromise = promise; } });
  await activatePromise;
  assert.deepEqual(worker.deletedCaches, ["kingflow-pwa-v5", "kingflow-pwa-v6", "kingflow-pwa-v7", "kingflow-pwa-v8", "kingflow-pwa-v9", "kingflow-pwa-v10", "kingflow-pwa-v11", "kingflow-pwa-v12", "kingflow-pwa-v13", "kingflow-pwa-v14", "kingflow-pwa-v15", "kingflow-pwa-v16", "kingflow-pwa-v17", "kingflow-pwa-v18", "kingflow-pwa-v19", "kingflow-pwa-v20", "kingflow-pwa-v21", "kingflow-pwa-v22", "kingflow-pwa-v23", "kingflow-pwa-v24", "kingflow-pwa-v25", "kingflow-pwa-v26", "kingflow-pwa-v27", "kingflow-pwa-v28", "kingflow-pwa-v29", "kingflow-pwa-v30", "kingflow-pwa-old"]);
});

test("waits for successful cache writes before completing a fetch event", async () => {
  let finishWrite;
  let fetchFinished = false;
  const cacheWrite = new Promise((resolve) => { finishWrite = resolve; });
  const networkResponse = { status: 200, clone() { return this; } };
  const worker = createWorker(async () => networkResponse, () => cacheWrite);
  let responsePromise;
  worker.listeners.get("fetch")({
    request: {
      method: "GET", url: "https://kingflow.test/index.html", mode: "navigate",
      headers: { has: () => false },
    },
    respondWith(promise) { responsePromise = promise.then((response) => { fetchFinished = true; return response; }); },
  });

  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(fetchFinished, false);
  finishWrite();
  assert.equal((await responsePromise).status, 200);
  assert.equal(fetchFinished, true);
});

test("returns a successful network response when cache persistence fails", async () => {
  const networkResponse = { status: 200, clone() { return this; } };
  const worker = createWorker(async () => networkResponse, async () => { throw new Error("cache full"); });
  let responsePromise;
  worker.listeners.get("fetch")({
    request: {
      method: "GET", url: "https://kingflow.test/index.html", mode: "navigate",
      headers: { has: () => false },
    },
    respondWith(promise) { responsePromise = promise; },
  });

  assert.equal(await responsePromise, networkResponse);
});

test("returns a successful network response when cloning it for cache fails", async () => {
  const networkResponse = { status: 200, clone() { throw new Error("response body is locked"); } };
  const worker = createWorker(async () => networkResponse);
  let responsePromise;
  worker.listeners.get("fetch")({
    request: {
      method: "GET", url: "https://kingflow.test/index.html", mode: "navigate",
      headers: { has: () => false },
    },
    respondWith(promise) { responsePromise = promise; },
  });

  assert.equal(await responsePromise, networkResponse);
});

test("all app entry pages provide the manifest and register the service worker", () => {
  for (const page of ["index.html", "client.html", "admin.html", "signup.html", "reset-password.html", "onboarding.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", page), "utf8");
    assert.match(html, /rel="manifest"/i, `${page} must link the PWA manifest`);
    assert.match(html, /js\/pwa\.js/i, `${page} must register the service worker`);
    assert.match(html, /js\/config\.js/i, `${page} must load runtime API configuration`);
    const authScriptIndex = html.indexOf("js/auth.js");
    if (authScriptIndex >= 0) {
      assert.ok(html.indexOf("js/config.js") < authScriptIndex, `${page} must configure API before auth`);
    }
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "manifest.webmanifest"), "utf8"));
  assert.equal(manifest.start_url, "/index.html");
  assert.ok(manifest.icons.some((icon) => icon.sizes === "192x192"));
  assert.ok(manifest.icons.some((icon) => icon.sizes === "512x512"));
});

test("password recovery strips one-time tokens from history and uses the auth reset API", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "reset-password.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "password-reset.js"), "utf8");
  assert.match(page, /name="referrer" content="no-referrer"/);
  assert.match(fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8"), /href="\/reset-password\.html"/);
  assert.match(script, /history\.replaceState\(null, "", window\.location\.pathname\)/);
  assert.match(script, /auth\/password-reset\/\$\{path\}/);
  assert.match(script, /requestForm\.reset\(\)/);
});

test("owner, barber, and platform admin can change passwords from their authenticated portals", () => {
  for (const page of ["index.html", "admin.html"]) {
    const html = fs.readFileSync(path.join(__dirname, "..", page), "utf8");
    assert.match(html, /id="changePasswordBtn"/);
    assert.match(html, /id="passwordChangeDialog"/);
    assert.match(html, /id="passwordCurrent"/);
    assert.match(html, /id="passwordNew"/);
    assert.match(html, /id="passwordConfirm"/);
    assert.match(html, /id="passwordNew"[^>]*minlength="12"/);
    assert.match(html, /id="passwordConfirm"[^>]*minlength="12"/);
    assert.match(html, /al menos 12 caracteres/);
    assert.ok(html.indexOf("js/auth.js") < html.indexOf("js/account-security.js"));
  }
  const resetPage = fs.readFileSync(path.join(__dirname, "..", "reset-password.html"), "utf8");
  assert.match(resetPage, /id="newPassword"[^>]*minlength="12"/);
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "account-security.js"), "utf8");
  assert.match(script, /api\/v1\/auth\/change-password/);
  assert.match(script, /newPassword !== confirmation/);
  assert.match(script, /KingFlowAuth\.logout\(\)/);
  assert.match(script, /kingflow-password-changed/);
});

test("password change form validates matching passwords, calls the API, and signs out", async () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "account-security.js"), "utf8");
  const listeners = new Map();
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: "",
      disabled: false,
      textContent: "",
      hidden: false,
      listeners: new Map(),
      addEventListener(name, callback) { this.listeners.set(name, callback); },
      focus() { this.focused = true; },
      reset() { this.value = ""; },
    });
    return elements.get(id);
  };
  const dialog = element("passwordChangeDialog");
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => {
    dialog.open = false;
    dialog.listeners.get("close")?.();
  };
  const submitButton = element("passwordSubmit");
  const form = element("passwordChangeForm");
  form.querySelector = () => submitButton;
  const document = {
    getElementById: element,
  };
  const requestCalls = [];
  let logoutCalls = 0;
  let redirect = "";
  const session = new Map();
  const sandbox = {
    document,
    window: {
      KINGFLOW_CONFIG: { apiBaseUrl: "https://api.kingflow.test/" },
      location: { origin: "https://kingflow.test", assign(url) { redirect = url; } },
    },
    KingFlowAuth: {
      async fetch(url, options) {
        requestCalls.push({ url, options });
        return { ok: true, async json() { return { success: true }; } };
      },
      async logout() { logoutCalls += 1; },
    },
    sessionStorage: {
      setItem(key, value) { session.set(key, value); },
    },
  };
  vm.runInNewContext(script, sandbox, { filename: "account-security.js" });

  await element("changePasswordBtn").listeners.get("click")();
  assert.equal(dialog.open, true);
  assert.equal(element("passwordCurrent").focused, true);
  element("passwordCurrent").value = "CurrentPassword123";
  element("passwordNew").value = "NewPassword456";
  element("passwordConfirm").value = "DifferentPassword789";
  await form.listeners.get("submit")({ preventDefault() {} });
  assert.equal(requestCalls.length, 0);
  assert.match(element("passwordChangeResult").textContent, /no coinciden/i);

  element("passwordConfirm").value = "NewPassword456";
  await form.listeners.get("submit")({ preventDefault() {} });
  assert.equal(requestCalls.length, 1);
  assert.equal(requestCalls[0].url, "https://api.kingflow.test/api/v1/auth/change-password");
  assert.deepEqual(JSON.parse(requestCalls[0].options.body), {
    current_password: "CurrentPassword123",
    new_password: "NewPassword456",
  });
  assert.equal(logoutCalls, 1);
  assert.equal(session.get("kingflow-password-changed"), "1");
  assert.equal(redirect, "/index.html");
});

test("native install prompt remains available when a page has no custom install control", () => {
  for (const hasInstallControl of [false, true]) {
    const listeners = new Map();
    const installButton = hasInstallControl ? { style: {}, addEventListener() {} } : null;
    const sandbox = {
      document: {
        getElementById(id) { return id === "installAppBtn" ? installButton : null; },
      },
      window: {
        addEventListener(name, callback) { listeners.set(name, callback); },
      },
      navigator: {},
    };
    vm.runInNewContext(pwaSource, sandbox, { filename: "pwa.js" });

    let prevented = false;
    listeners.get("beforeinstallprompt")({ preventDefault() { prevented = true; } });
    assert.equal(prevented, hasInstallControl);
  }
});

test("WhatsApp sharing accepts only the HTTPS wa.me origin", () => {
  const sandbox = { URL, window: {} };
  vm.runInNewContext(securitySource, sandbox, { filename: "security.js" });
  const safeUrl = sandbox.window.KingFlowSecurity.trustedWhatsAppShareUrl;
  assert.equal(safeUrl("https://wa.me/?text=KingFlow"), "https://wa.me/?text=KingFlow");
  assert.equal(safeUrl("javascript:alert(1)"), null);
  assert.equal(safeUrl("https://wa.me.example.test/?text=bad"), null);
  assert.equal(safeUrl("https://evil.example/?text=bad"), null);
  assert.equal(safeUrl("https://attacker@wa.me/?text=bad"), null);
  const pageSource = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const mainSource = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.ok(pageSource.indexOf("js/security.js") < pageSource.indexOf("js/main.js"));
  assert.match(mainSource, /window\.open\(shareUrl, '_blank', 'noopener,noreferrer'\)/);
});

test("runtime API configuration targets the local backend only on the split dev server", () => {
  const configSource = fs.readFileSync(path.join(__dirname, "..", "js", "config.js"), "utf8");
  const localWindow = { location: { port: "3000", hostname: "localhost", protocol: "http:", origin: "http://localhost:3000" } };
  vm.runInNewContext(configSource, { window: localWindow });
  assert.equal(localWindow.KINGFLOW_CONFIG.apiBaseUrl, "http://localhost:8000");

  const productionWindow = { location: { port: "", hostname: "kingflow.example", protocol: "https:", origin: "https://kingflow.example" } };
  vm.runInNewContext(configSource, { window: productionWindow });
  assert.equal(productionWindow.KINGFLOW_CONFIG.apiBaseUrl, "https://kingflow.example");
});

test("admin user table headers align with rendered data labels", () => {
  const adminPage = fs.readFileSync(path.join(__dirname, "..", "admin.html"), "utf8");
  const adminScript = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
  const userTable = adminPage.match(/<div id="usersTableWrap">([\s\S]*?)<\/div>/)?.[1];
  assert.ok(userTable, "admin user table must exist");
  const columns = ["Usuario", "Rol", "Barbería", "Estado", "Acceso", "Soporte por correo", "Branding automático"];
  const headers = [...userTable.matchAll(/<th>([^<]+)<\/th>/g)].map((match) => match[1]);
  assert.deepEqual(headers, columns);
  for (const column of columns) {
    assert.ok(adminScript.includes(`data-label="${column}"`), `rendered rows must label ${column}`);
  }
  assert.match(adminPage, /id="userSearch"[^>]*type="search"/);
  assert.match(adminPage, /id="previousUsersBtn"/);
  assert.match(adminPage, /id="nextUsersBtn"/);
  assert.match(adminScript, /new URLSearchParams\(\{ limit: String\(USERS_PAGE_SIZE\), offset: String\(usersOffset\) \}\)/);
  assert.match(adminScript, /params\.set\('search', search\)/);
  assert.match(adminScript, /usersRequestSequence/);
  assert.match(adminScript, /data\.total/);
});

test("admin audit and affiliate tables label all cells for mobile layouts", () => {
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
  const labels = [
    "Fecha", "Barbería", "Usuario", "Acción", "Elemento", "Datos",
    "Afiliado", "Código", "Estado", "Referidos", "Comisiones por moneda", "Acciones",
    "Importe", "Periodo", "Referencia de pago",
  ];
  for (const label of labels) {
    assert.ok(script.includes(`data-label="${label}"`), `${label} must label its mobile table cell`);
  }
});

test("barber portal exposes the absence form connected to the MySQL-backed API", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.match(page, /id="barberAbsenceForm"/);
  assert.match(page, /id="barberAvailabilityTools" hidden/);
  assert.match(script, /absenceForm\.onsubmit = createBarberAbsence/);
  assert.match(script, /\/api\/v1\/barber\/absences/);
  assert.match(script, /\/api\/v1\/barber\/absences\/\$\{Number\(button\.dataset\.id\)\}/);
});

test("owner financial report form is connected to tenant-scoped real-payment analytics", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.match(page, /id="ownerFinancialReport" hidden/);
  assert.match(page, /id="financialReportStart" type="date"/);
  assert.match(page, /id="financialReportEnd" type="date"/);
  assert.ok(script.includes('/api/v1/analytics/financial-report'));
  assert.match(script, /financialReportForm.*addEventListener\('submit'/s);
});

test("platform registration settings are administered and enforced by signup flow", () => {
  const adminPage = fs.readFileSync(path.join(__dirname, "..", "admin.html"), "utf8");
  const adminScript = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
  const signupScript = fs.readFileSync(path.join(__dirname, "..", "js", "signup.js"), "utf8");
  assert.match(adminPage, /id="platformSettingsForm"/);
  assert.match(adminPage, /id="registrationsEnabled"/);
  assert.match(adminPage, /id="freePeriodDays"/);
  assert.ok(adminScript.includes("/api/v1/admin/settings"));
  assert.ok(signupScript.includes("/api/v1/saas/registration-status"));
  assert.ok(signupScript.includes("/api/v1/saas/register"));
  const signupPage = fs.readFileSync(path.join(__dirname, "..", "signup.html"), "utf8");
  assert.match(signupPage, /id="registrationOffer"/);
  assert.match(signupScript, /status\.free_period_days/);
  assert.match(signupScript, /days === 1 \? "día" : "días"/);
  assert.doesNotMatch(signupPage, /plan gratuito por 30 días/);
});

test("owner client actions are wired to scoped edit and status endpoints", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.match(page, /id="ownerClientCreateForm"/);
  assert.match(script, /ownerFetch\('\/owner\/clients'/);
  assert.match(page, /id="ownerClientEditForm"/);
  assert.match(page, /id="ownerClientFirstName"/);
  assert.match(script, /\/owner\/clients\/\$\{clientId\}/);
  assert.match(script, /\/owner\/clients\/\$\{Number\(statusButton\.dataset\.id\)\}\/status/);
  assert.match(script, /su historial de citas y cobros se conserva/);
});

test("owner can edit a barber profile through the tenant-scoped API", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.match(page, /id="ownerBarberEditForm"/);
  assert.match(script, /ownerFetch\(`\/owner\/barbers\/\$\{barberId\}`/);
  assert.match(script, /barber\.first_name/);
  assert.match(script, /barber\.last_name/);
});

test("platform support inbox uses authenticated ticket and status APIs", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "admin.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
  assert.match(page, /id="supportTicketsBody"/);
  assert.ok(script.includes("/api/v1/admin/support/tickets?"));
  assert.match(script, /escapeHtml\(ticket\.message\)/);
  assert.match(script, /offset: String\(supportTicketsOffset\)/);
  assert.match(script, /admin\/support\/tickets\/\$\{ticketId\}\/status/);
});

test("support forms confirm the saved ticket even when email notice is unavailable", () => {
  const clientScript = fs.readFileSync(path.join(__dirname, "..", "js", "client.js"), "utf8");
  const mainScript = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  assert.match(clientScript, /Solicitud #\$\{Number\(data\.ticket_id\)\} recibida y guardada/);
  assert.match(mainScript, /Solicitud #\$\{Number\(data\.ticket_id\)\} recibida y guardada/);
});

test("owner subscription panel reads period status and plan usage from the API", () => {
  const page = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");
  const adminPage = fs.readFileSync(path.join(__dirname, "..", "admin.html"), "utf8");
  const adminScript = fs.readFileSync(path.join(__dirname, "..", "js", "admin.js"), "utf8");
  assert.match(page, /id="ownerSubscriptionSummary"/);
  assert.ok(script.includes("ownerFetch('/billing/subscription')"));
  assert.match(script, /loadOwnerSubscription/);
  assert.match(script, /Renovación manual: cada periodo requiere que un administrador registre el pago recibido/);
  assert.match(script, /El sistema no procesa ni programa cargos automáticos\./);
  assert.doesNotMatch(script, /data\.auto_renew/);
  assert.match(adminPage, /Este indicador es administrativo; no procesa ni programa cargos/);
  assert.match(adminScript, /El cobro se registra manualmente/);
});

test("does not persist navigations whose query carries a tracking token", async () => {
  let requestedUrl;
  const worker = createWorker(async (request) => {
    requestedUrl = request.url;
    return { status: 200 };
  });
  let responsePromise;
  worker.listeners.get("fetch")({
    request: {
      method: "GET",
      url: "https://kingflow.test/client.html?shop=barberia&track_token=private-token",
      mode: "navigate",
      headers: { has: () => false },
    },
    respondWith(promise) { responsePromise = promise; },
  });

  const response = await responsePromise;
  assert.equal(response.status, 200);
  assert.match(requestedUrl, /track_token=private-token/);
  assert.deepEqual(worker.writes, []);
});

test("leaves authenticated requests to the network without caching them", () => {
  const worker = createWorker();
  let intercepted = false;
  worker.listeners.get("fetch")({
    request: {
      method: "GET",
      url: "https://kingflow.test/admin.html",
      mode: "navigate",
      headers: { has: (name) => name.toLowerCase() === "authorization" },
    },
    respondWith() { intercepted = true; },
  });
  assert.equal(intercepted, false);
  assert.deepEqual(worker.writes, []);
});

test("does not persist navigations with query parameters that may carry secrets", async () => {
  for (const queryKey of ["token", "code", "reset_token", "access_token", "refresh-token", "verification_code", "auth", "email", "otp", "opaque_credential"]) {
    const worker = createWorker(async () => ({ status: 200 }));
    let responsePromise;
    worker.listeners.get("fetch")({
      request: {
        method: "GET",
        url: `https://kingflow.test/reset-password.html?${queryKey}=one-time-secret`,
        mode: "navigate",
        headers: { has: () => false },
      },
      respondWith(promise) { responsePromise = promise; },
    });

    const response = await responsePromise;
    assert.equal(response.status, 200);
    assert.deepEqual(worker.writes, []);
  }
});

test("does not persist query URLs with mixed-case parameter names", async () => {
  const worker = createWorker(async () => ({ status: 200 }));
  let responsePromise;
  worker.listeners.get("fetch")({
    request: {
      method: "GET",
      url: "https://kingflow.test/reset-password.html?Reset_Token=one-time-secret",
      mode: "navigate",
      headers: { has: () => false },
    },
    respondWith(promise) { responsePromise = promise; },
  });

  assert.equal((await responsePromise).status, 200);
  assert.deepEqual(worker.writes, []);
});

test("leaves API requests to the browser network without caching them", () => {
  const worker = createWorker();
  let intercepted = false;
  worker.listeners.get("fetch")({
    request: {
      method: "GET",
      url: "https://kingflow.test/api/v1/public/shop",
      mode: "cors",
      headers: { has: () => false },
    },
    respondWith() { intercepted = true; },
  });
  assert.equal(intercepted, false);
});
