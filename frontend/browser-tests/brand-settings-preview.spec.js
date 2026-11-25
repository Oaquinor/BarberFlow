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
  await expect(page.locator("#businessStylePassportRetention")).toHaveValue("");
  await expect(page.locator("#businessStylePassportRetention option")).toHaveCount(5);

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

test("owner confirms retention changes and saves the selected policy", async ({ page }) => {
  let requestBody;
  await page.route("**/api/v1/onboarding/business-settings", async (route) => {
    requestBody = route.request().postDataJSON();
    await route.fulfill({ json: {
      id: 7, name: "Barbería de Prueba", timezone: "America/Santo_Domingo",
      style_passport_retention_days: 180,
    } });
  });
  await page.goto("/index.html");
  await page.evaluate(() => {
    sessionStorage.setItem("token", "owner-test-token");
    loadBarberDashboardData = async () => {};
    loadOwnerManagement = async () => {};
    currentUser = { role: "barbershop_owner" };
    barbershopProfile = {
      name: "Barbería de Prueba", timezone: "America/Santo_Domingo",
      style_passport_retention_days: null,
    };
    document.getElementById("businessSettingsName").value = "Barbería de Prueba";
    document.getElementById("businessSettingsDescription").value = "Cortes precisos.";
    document.getElementById("businessSettingsOpening").value = "09:00";
    document.getElementById("businessSettingsClosing").value = "19:00";
    document.getElementById("businessCancellationWindow").value = "0";
    document.getElementById("businessSettingsTimezone").value = "America/Santo_Domingo";
    document.getElementById("businessSettingsPrimary").value = "#b98752";
    document.getElementById("businessSettingsSecondary").value = "#5a4635";
    document.getElementById("businessSettingsTheme").value = "light";
    document.getElementById("businessStylePassportRetention").value = "180";
    void saveBusinessSettings({ preventDefault() {} });
  });

  await expect(page.getByRole("dialog")).toContainText("también se aplicará a los registros existentes");
  await page.getByRole("button", { name: "Aplicar política" }).click();
  await expect.poll(() => requestBody?.style_passport_retention_days).toBe(180);
  await expect(page.locator("#businessSettingsResult")).toContainText("Configuración guardada");
});
