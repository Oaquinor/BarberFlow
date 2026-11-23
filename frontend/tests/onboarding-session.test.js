"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "js", "onboarding.js"), "utf8");
const listener = source.match(/window\.addEventListener\('kingflow:auth-expired',[\s\S]*?\n\}\);/);

test("expired onboarding sessions return to the login portal", () => {
  assert.ok(listener, "onboarding must handle the shared auth-expired event");
  const redirects = [];
  const sandbox = {
    window: {
      location: { replace: (url) => redirects.push(url) },
      addEventListener(name, callback) {
        assert.equal(name, "kingflow:auth-expired");
        callback();
      },
    },
  };

  vm.runInNewContext(listener[0], sandbox);

  assert.deepEqual(redirects, ["/index.html"]);
});
