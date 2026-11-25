const { expect, test } = require("@playwright/test");

test("owner sees a live, readable storefront preview from their settings", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 1000 });
  await page.goto("/index.html");
  await page.evaluate(() => {
    document.getElementById("loginSection").style.display = "none";
    document.getElementById("dashboardSection").style.display = "grid";
    document.getElementById("ownerManagementTab").style.display = "block";
    document.getElementById("ownerManagementTab").style.display = "block";
    document.getElementById("ownerManagementTabButton").hidden = false;
    currentUser = { role: "barbershop_owner" };
    serviceCache = [{
      name: "Corte clásico",
      price_cents: 1250,
      duration_minutes: 35,
      is_active: true,
    }];
    document.getElementById("businessSettingsName").value = "Barbería de Prueba";
    document.getElementById("businessSettingsDescription").value = "Cortes precisos y atención cercana.";
    document.getElementById("businessCancellationWindow").value = "12";
    setupBrandPreview();
    const coverPreview = document.getElementById("businessCoverPreview");
    const cover = document.createElement("img");
    cover.src = "/images/barbershop-hero.png";
    cover.alt = "Vista previa de portada para la barbería";
    coverPreview.append(cover);
  });

  const preview = page.locator("#brandPreview");
  await expect(preview).toContainText("Barbería de Prueba");
  await expect(preview).toContainText("Cortes precisos y atención cercana.");
  await expect(preview).toContainText("Corte clásico");
  await expect(preview.locator("#brandContrastNote")).toContainText("WCAG AA");
  await expect(page.locator("#businessCancellationWindow")).toHaveValue("12");

  await page.getByRole("button", { name: "Oliva y lima" }).click();
  await expect(page.getByRole("button", { name: "Oliva y lima" })).toHaveAttribute("aria-pressed", "true");
  await expect(preview).toHaveCSS("--preview-primary", "#9aa276");
  const submitButton = page.locator("#businessSettingsForm .settings-submit button");
  await expect(submitButton).toHaveCSS("min-height", "48px");
  await page.locator("#businessSettingsForm").screenshot({ path: "test-results/brand-settings-preview.png" });

  for (const width of [320, 375, 390, 430, 768, 1024, 1366, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    const geometry = await page.evaluate(() => {
      const submit = document.querySelector("#businessSettingsForm .settings-submit button").getBoundingClientRect();
      const cover = document.querySelector("#businessCoverPreview img").getBoundingClientRect();
      return {
        viewport: document.documentElement.clientWidth,
        document: document.documentElement.scrollWidth,
        submitLeft: submit.left,
        submitRight: submit.right,
        coverLeft: cover.left,
        coverRight: cover.right,
      };
    });
    expect(geometry.document, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(width + 1);
    expect(geometry.submitLeft, `submit starts outside viewport at ${width}px`).toBeGreaterThanOrEqual(-1);
    expect(geometry.submitRight, `submit ends outside viewport at ${width}px`).toBeLessThanOrEqual(width + 1);
    expect(geometry.coverLeft, `cover starts outside viewport at ${width}px`).toBeGreaterThanOrEqual(-1);
    expect(geometry.coverRight, `cover ends outside viewport at ${width}px`).toBeLessThanOrEqual(width + 1);
  }
});
