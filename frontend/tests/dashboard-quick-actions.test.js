"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
const script = fs.readFileSync(path.join(__dirname, "..", "js", "main.js"), "utf8");

test("dashboard quick actions navigate to their matching tabs", () => {
  assert.match(html, /id="quickStatsButton"[\s\S]*?Ver rendimiento/);
  assert.match(html, /id="quickAgendaButton"[\s\S]*?Ver agenda/);
  assert.match(html, /id="quickWalkInButton"[\s\S]*?Iniciar servicio presencial/);
  assert.match(html, /id="quickServicesButton"[\s\S]*?Administrar servicios/);
  assert.match(script, /getElementById\('quickStatsButton'\)\?\.addEventListener\('click',\s*\(\)\s*=>\s*showTab\('performance'\)\)/);
  assert.match(script, /getElementById\('quickAgendaButton'\)\?\.addEventListener\('click',\s*\(\)\s*=>\s*showTab\('appointments'\)\)/);
  assert.match(script, /getElementById\('quickWalkInButton'\)\?\.addEventListener\('click',[\s\S]*?showTab\('appointments'\)/);
  assert.match(script, /getElementById\('quickServicesButton'\)\?\.addEventListener\('click',\s*\(\)\s*=>\s*showTab\('services'\)\)/);
});

test("walk-in panel offers distinct queue and immediate-start actions", () => {
  assert.match(html, /id="queueWalkInButton"[^>]*>Añadir a la fila/);
  assert.match(html, /id="walkInForm"[\s\S]*?Iniciar servicio presencial/);
  assert.match(script, /registerWalkIn\(false\)/);
  assert.match(script, /start_immediately:\s*startImmediately/);
  assert.match(script, /checked_in_at/);
  assert.match(script, /En espera · turno/);
});

test("workspace exposes the operating, close, business, screen, and help areas", () => {
  for (const label of ["Agenda", "Citas", "Turnos", "Cerrar jornada", "Historial", "Rendimiento", "Servicios", "Mi sitio", "Pantallas", "Configuración", "Equipo", "Inventario", "Lista de espera", "Clientes", "Plan y uso", "Acerca de"]) {
    assert.ok(html.includes(`>${label}</span></button>`) || html.includes(`>${label}</p>`), `missing workspace entry: ${label}`);
  }
  assert.match(html, /data-appointment-mode="bookings"/);
  assert.match(html, /data-appointment-mode="queue"/);
  assert.match(html, /id="cashHistoryForm"/);
  assert.match(html, /id="screenFullscreenButton"/);
  assert.match(script, /function loadCashHistory\(/);
  assert.match(script, /function loadScreenBoard\(/);
  assert.match(script, /function showTab\(tabName, requestedButton = null\)/);
});
