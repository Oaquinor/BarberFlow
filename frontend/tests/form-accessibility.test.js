"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontend = path.join(__dirname, "..");
const formControls = {
  "index.html": [
    "loginEmail", "loginPassword", "slotDate", "slotStart", "slotEnd", "slotMinutes",
    "shareLinkInput", "walkInClientName", "walkInClientPhone", "walkInServiceSelect",
    "walkInBarberSelect", "serviceSearch",
  ],
  "client.html": [
    "clientName", "clientPhone", "serviceSelect", "scheduledTime", "clientNotes",
    "trackToken", "supportName", "supportEmail", "supportPhone", "supportMessage",
  ],
  "admin.html": [
    "subscriptionTenantSelect", "subPlan", "subStatus", "subPeriodEnd", "subAutoRenew",
    "tenantFilter", "auditTenantFilter", "affiliateFirstName", "affiliateLastName",
    "affiliateEmail", "affiliatePhone", "affiliateCommissionSelect",
  ],
  "onboarding.html": [
    "barbershopName", "logoFile", "primaryColor", "secondaryColor", "teamSize",
    "avgDuration", "openingTime", "closingTime",
  ],
};

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

test("interactive form controls have an accessible name", () => {
  for (const [file, ids] of Object.entries(formControls)) {
    const html = fs.readFileSync(path.join(frontend, file), "utf8");
    for (const id of ids) {
      const idPattern = escapeRegExp(id);
      const tag = html.match(new RegExp(`<(?:(?:input)|select|textarea)\\b[^>]*\\bid=["']${idPattern}["'][^>]*>`, "i"));
      assert.ok(tag, `${file} must contain control ${id}`);

      const hasAriaName = /\baria-label(?:ledby)?\s*=/.test(tag[0]);
      const hasAssociatedLabel = new RegExp(`<label\\b[^>]*\\bfor=["']${idPattern}["']`, "i").test(html);
      assert.ok(hasAriaName || hasAssociatedLabel, `${file}#${id} must have an accessible label`);
    }
  }

  const onboarding = fs.readFileSync(path.join(frontend, "onboarding.html"), "utf8");
  const onboardingScript = fs.readFileSync(path.join(frontend, "js", "onboarding.js"), "utf8");
  assert.match(onboarding, /id="uploadArea"[^>]*role="button"[^>]*tabindex="0"/);
  assert.match(onboardingScript, /event\.key === 'Enter' \|\| event\.key === ' '/);
  assert.match(onboarding, /id="logoPreview"[^>]*alt="Vista previa del logo de la barbería"/);
});

test("logo upload control opens from Enter and Space", () => {
  const onboardingScript = fs.readFileSync(path.join(frontend, "js", "onboarding.js"), "utf8");
  const start = onboardingScript.indexOf("uploadArea.addEventListener('keydown'");
  const end = onboardingScript.indexOf("\n});", start) + 4;
  assert.ok(start >= 0 && end > start, "logo upload keyboard handler must exist");

  let handler;
  let clicks = 0;
  const sandbox = {
    uploadArea: { addEventListener(type, callback) { if (type === "keydown") handler = callback; } },
    document: { getElementById(id) { return id === "logoFile" ? { click() { clicks += 1; } } : null; } },
  };
  require("node:vm").runInNewContext(onboardingScript.slice(start, end), sandbox);

  for (const key of ["Enter", " "]) {
    let prevented = false;
    handler({ key, preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
  }
  assert.equal(clicks, 2);
});
