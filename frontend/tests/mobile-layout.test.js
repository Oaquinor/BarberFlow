"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const frontend = path.join(__dirname, "..");
const page = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
const script = fs.readFileSync(path.join(frontend, "js", "main.js"), "utf8");

test("owner tables switch to labeled cards on narrow screens", () => {
  assert.match(page, /name="viewport" content="width=device-width, initial-scale=1\.0"/);
  assert.match(page, /\.table-wrap\s*\{[^}]*overflow-x:auto/s);
  assert.match(page, /@media\s*\(max-width:\s*992px\)[\s\S]*?\.header\s*\{[^}]*flex-direction:\s*column/);
  assert.match(page, /@media\s*\(max-width:\s*700px\)[\s\S]*?\.table-wrap tbody td::before\s*\{\s*content:attr\(data-label\)/);

  for (const label of [
    "Nombre", "Correo", "Teléfono", "Comisión (%)", "Estado", "Acción",
    "Cliente", "Citas", "Completadas", "Última visita", "Total pagado", "Acciones",
    "Barbero", "Fecha", "Importe", "Tasa", "Liquidación",
    "Grupo", "Transacciones", "Servicios", "Productos", "Propinas", "Total", "Informe",
  ]) {
    assert.ok(script.includes(`data-label="${label}"`), `mobile table must label ${label}`);
  }
});
