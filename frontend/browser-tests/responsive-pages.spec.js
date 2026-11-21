"use strict";

const { test, expect } = require("@playwright/test");

const pages = [
  ["Inicio de owner", "/index.html", "loginForm"],
  ["Registro", "/signup.html", "signupForm"],
  ["Portal de cliente", "/client.html", "showBookBtn"],
  ["Administración", "/admin.html", "gateContainer"],
  ["Onboarding", "/onboarding.html", "step1"],
  ["Recuperación", "/reset-password.html", "requestForm"],
];

const viewports = [
  { name: "small-phone", width: 320, height: 640, isMobile: true, hasTouch: true },
  { name: "phone", width: 375, height: 667, isMobile: true, hasTouch: true },
  { name: "tablet", width: 768, height: 1024, isMobile: false, hasTouch: true },
];

for (const viewport of viewports) {
  test.describe(`${viewport.name} ${viewport.width}x${viewport.height}`, () => {
    test.use({
      viewport: { width: viewport.width, height: viewport.height },
      isMobile: viewport.isMobile,
      hasTouch: viewport.hasTouch,
      deviceScaleFactor: viewport.isMobile ? 2 : 1,
    });

    for (const [label, route, primaryId] of pages) {
      test(`${label} se ajusta al viewport sin desbordamiento horizontal`, async ({ page }) => {
        const pageErrors = [];
        page.on("pageerror", (error) => pageErrors.push(error.message));
        if (route === "/onboarding.html") {
          await page.addInitScript(() => sessionStorage.setItem("token", "browser-layout-test"));
          await page.route("**/api/v1/onboarding/step/**", (request) =>
            request.fulfill({ json: { success: true } }),
          );
        }
        if (route === "/client.html") {
          await page.route("**/api/v1/public/mobile-test**", async (request) => {
            const url = new URL(request.request().url());
            if (url.pathname.endsWith("/services")) {
              await request.fulfill({ json: [{ id: 1, name: "Corte", price_cents: 1500, duration_minutes: 30 }] });
            } else if (url.pathname.endsWith("/slots")) {
              await request.fulfill({ json: [] });
            } else {
              await request.fulfill({ json: {
                id: 1,
                name: "Barbería de prueba",
                currency: "DOP",
                timezone: "America/Santo_Domingo",
              } });
            }
          });
        }
        const targetRoute = route === "/client.html" ? `${route}?shop=mobile-test` : route;
        await page.goto(targetRoute, { waitUntil: "networkidle" });

        await expect(page.locator(`#${primaryId}`)).toBeAttached();
        await expect(page.locator('meta[name="viewport"]')).toHaveAttribute(
          "content",
          /width=device-width/,
        );

        const layout = await page.evaluate(() => ({
          viewportWidth: document.documentElement.clientWidth,
          documentWidth: document.documentElement.scrollWidth,
          bodyWidth: document.body.scrollWidth,
          visibleControls: [...document.querySelectorAll("button, input, select, textarea")]
            .filter((element) => {
              const style = getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0;
            })
            .map((element) => ({
              id: element.id,
              left: Math.round(element.getBoundingClientRect().left),
              right: Math.round(element.getBoundingClientRect().right),
            })),
        }));

        expect(layout.documentWidth, `${label} document width`).toBeLessThanOrEqual(
          layout.viewportWidth + 1,
        );
        expect(layout.bodyWidth, `${label} body width`).toBeLessThanOrEqual(
          layout.viewportWidth + 1,
        );
        const outOfBounds = layout.visibleControls.filter(
          (control) => control.left < -1 || control.right > layout.viewportWidth + 1,
        );
        expect(outOfBounds, `${label} visible controls outside viewport`).toEqual([]);

        if (route === "/client.html") {
          await expect(
            page.locator("#showBookBtn"),
            `Client page errors: ${pageErrors.join(" | ") || "none"}`,
          ).toHaveClass(/active/);
          await page.locator("#showBookBtn").click();
          await expect(page.locator("#bookSection")).toBeVisible();
          const bookingWidth = await page.evaluate(() => ({
            viewport: document.documentElement.clientWidth,
            document: document.documentElement.scrollWidth,
          }));
          expect(bookingWidth.document, "booking panel width").toBeLessThanOrEqual(
            bookingWidth.viewport + 1,
          );
          const bookingControls = await page.locator("#bookSection button, #bookSection input, #bookSection select, #bookSection textarea").evaluateAll(
            (controls) => controls.map((control) => {
              const rect = control.getBoundingClientRect();
              return { left: Math.round(rect.left), right: Math.round(rect.right) };
            }),
          );
          expect(
            bookingControls.filter((control) => control.left < -1 || control.right > bookingWidth.viewport + 1),
            "booking controls outside viewport",
          ).toEqual([]);
        }

        if (route === "/onboarding.html") {
          await page.locator("#barbershopName").fill("KingFlow Test");
          await page.getByRole("button", { name: "Siguiente" }).click();
          await expect(page.locator("#step2")).toBeVisible();
        }

        expect(pageErrors, `${label} uncaught browser errors`).toEqual([]);
      });
    }
  });
}

test("registro y recuperación comparten la identidad visual de KingFlow", async ({ page }) => {
  for (const route of ["/signup.html", "/reset-password.html"]) {
    await page.goto(route, { waitUntil: "networkidle" });
    const design = await page.evaluate(() => ({
      themeColor: document.querySelector('meta[name="theme-color"]').content,
      bodyBackground: getComputedStyle(document.body).backgroundImage,
      cardRadius: getComputedStyle(document.querySelector(".card")).borderRadius,
      fieldRadius: getComputedStyle(document.querySelector("input")).borderRadius,
      buttonBackground: getComputedStyle(document.querySelector("button")).backgroundImage,
    }));

    expect(design.themeColor).toBe("#667eea");
    expect(design.bodyBackground).toContain("linear-gradient");
    expect(design.cardRadius).toBe("20px");
    expect(design.fieldRadius).toBe("12px");
    expect(design.buttonBackground).toContain("linear-gradient");
  }
});
