"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const frontend = path.join(__dirname, "..");

test("registration and recovery use shared KingFlow auth-page styles", () => {
  const styles = fs.readFileSync(path.join(frontend, "css", "auth-pages.css"), "utf8");
  assert.match(styles, /--brand-primary:\s*#667eea/i);
  assert.match(styles, /input:focus-visible[\s\S]*border-color:\s*var\(--brand-primary\)/);

  for (const page of ["signup.html", "reset-password.html"]) {
    const html = fs.readFileSync(path.join(frontend, page), "utf8");
    assert.match(html, /href="\/css\/auth-pages\.css"/);
    assert.match(html, /name="theme-color" content="#667eea"/);
  }
});

test("all page form controls have an accessible name", () => {
  const pages = fs.readdirSync(frontend).filter((file) => file.endsWith(".html"));
  for (const page of pages) {
    const html = fs.readFileSync(path.join(frontend, page), "utf8");
    const explicitLabels = new Set(
      [...html.matchAll(/<label\b[^>]*\bfor=["']([^"']+)["'][^>]*>/gi)].map((match) => match[1]),
    );
    const labelRanges = [...html.matchAll(/<label\b[^>]*>[\s\S]*?<\/label>/gi)]
      .map((label) => [label.index, label.index + label[0].length]);

    const controls = [...html.matchAll(/<(input|select|textarea)\b[^>]*>/gi)];
    for (const control of controls) {
      const tag = control[0];
      const type = tag.match(/\btype=["']([^"']+)["']/i)?.[1]?.toLowerCase();
      if (["hidden", "submit", "button", "reset", "image"].includes(type)) continue;

      const id = tag.match(/\bid=["']([^"']+)["']/i)?.[1];
      const hasAriaName = /\baria-label=["'][^"']+|\baria-labelledby=["'][^"']+/i.test(tag);
      const isWrappedByLabel = labelRanges.some(([start, end]) => control.index > start && control.index < end);
      const hasLabel = isWrappedByLabel || (id && explicitLabels.has(id));
      assert.ok(hasAriaName || hasLabel, `${page} contains a form control without a label: ${tag}`);
    }
  }
});

test("logo upload control is keyboard accessible", () => {
  const onboarding = fs.readFileSync(path.join(frontend, "onboarding.html"), "utf8");
  const onboardingScript = fs.readFileSync(path.join(frontend, "js", "onboarding.js"), "utf8");
  assert.match(onboarding, /id="uploadArea"[^>]*role="button"[^>]*tabindex="0"/);
  assert.match(onboarding, /id="logoPreview"[^>]*alt="Vista previa del logo de la barbería"/);

  const start = onboardingScript.indexOf("uploadArea.addEventListener('keydown'");
  const end = onboardingScript.indexOf("\n});", start) + 4;
  assert.ok(start >= 0 && end > start, "logo upload keyboard handler must exist");

  let handler;
  let clicks = 0;
  const sandbox = {
    uploadArea: { addEventListener(type, callback) { if (type === "keydown") handler = callback; } },
    document: { getElementById(id) { return id === "logoFile" ? { click() { clicks += 1; } } : null; } },
  };
  vm.runInNewContext(onboardingScript.slice(start, end), sandbox);

  for (const key of ["Enter", " "]) {
    let prevented = false;
    handler({ key, preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
  }
  assert.equal(clicks, 2);
});
