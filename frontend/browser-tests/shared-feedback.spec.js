const { test, expect } = require("@playwright/test");

test("shared toast and confirmation use accessible browser UI", async ({ page }) => {
  await page.goto("/index.html");

  await page.evaluate(() => window.showToast("<img src=x onerror=alert(1)>", "error"));
  const toast = page.getByRole("alert");
  await expect(toast).toContainText("<img src=x onerror=alert(1)>");
  await expect(toast.locator("img")).toHaveCount(0);
  await toast.getByRole("button", { name: "Cerrar aviso" }).click();
  await expect(toast).toBeHidden();

  const confirmed = page.evaluate(() => window.showConfirmation("¿Cancelar esta cita?", {
    title: "Cancelar cita", confirmLabel: "Cancelar cita", danger: true,
  }));
  const dialog = page.getByRole("dialog", { name: "Cancelar cita" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("¿Cancelar esta cita?");
  await dialog.getByRole("button", { name: "Cancelar cita" }).click();
  await expect(dialog).toBeHidden();
  expect(await confirmed).toBe(true);
});
