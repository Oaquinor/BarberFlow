"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "..");
const html = ["index.html", "admin.html"]
  .map((file) => fs.readFileSync(path.join(root, file), "utf8"))
  .join("\n");
const script = fs.readFileSync(path.join(root, "js", "mfa-settings.js"), "utf8");
const loginScript = fs.readFileSync(path.join(root, "js", "main.js"), "utf8");

test("privileged portals load account MFA management and accessible login challenge", () => {
  assert.equal((html.match(/src="js\/mfa-settings\.js"/g) || []).length, 2);
  assert.match(html, /id="loginMfaGroup"/);
  assert.match(html, /id="loginMfaCode"[^>]*autocomplete="one-time-code"/);
  assert.match(loginScript, /if \(data\.mfa_required\)/);
  assert.match(loginScript, /payload\.otp_code = mfaInput\.value\.trim\(\)/);
  assert.match(loginScript, /KingFlowMfaSettings\?\.mount\(\)/);
  assert.match(loginScript, /KingFlowMfaSettings\?\.unmount\(\)/);
  assert.match(html, /href="\/css\/tailwind\.css\?/);
});

test("MFA settings use the protected API and never persist recovery codes in markup storage", () => {
  for (const endpoint of ["status", "setup", "enable", "disable", "recovery-codes"]) {
    assert.ok(script.includes(`api("${endpoint}"`), `Missing MFA action ${endpoint}`);
  }
  assert.match(script, /textContent = codes\.join/);
  assert.match(script, /dialog\.showModal\(\)/);
  assert.doesNotMatch(script, /\b(prompt|alert)\s*\(/);
});
