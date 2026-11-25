const { expect, test } = require("@playwright/test");

test("owner service catalog filters live categories together with search", async ({ page }) => {
  await page.goto("/index.html");
  await page.evaluate(() => {
    currentUser = { role: "barbershop_owner" };
    serviceCache = [
      { id: 1, name: "Corte clásico", description: "Cabello", category: "haircut", duration_minutes: 30, price_cents: 1000, image_url: "/images/barbershop-hero.png" },
      { id: 2, name: "Barba premium", description: "Perfilado", category: "beard", duration_minutes: 20, price_cents: 800 },
    ];
    renderServiceCatalog(serviceCache);
    document.getElementById("dashboardSection").style.display = "block";
    showTab("services");
  });

  const categories = page.getByRole("group", { name: "Filtrar servicios por categoría" });
  const list = page.locator("#servicesList");
  await categories.getByRole("button", { name: "beard" }).click();
  await expect(list).toContainText("Barba premium");
  await expect(list).not.toContainText("Corte clásico");

  await page.getByRole("searchbox", { name: "Buscar servicios" }).fill("perfilado");
  await expect(list).toContainText("Barba premium");
  await expect(list).not.toContainText("Corte clásico");
  await page.getByRole("searchbox", { name: "Buscar servicios" }).fill("");
  await categories.getByRole("button", { name: "Todos" }).click();
  await expect(list).toContainText("Corte clásico");
  await expect(list).toContainText("Barba premium");
  await expect(list.getByRole("img", { name: "Foto de Corte clásico" })).toBeVisible();
  await expect(list.locator(".service-icon")).toHaveCount(1);
});
