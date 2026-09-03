const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || 'http://127.0.0.1:8000').replace(/\/$/, '');
const API_BASE = `${API_ROOT}/api/v1`;

function q(name) {
  return new URLSearchParams(window.location.search).get(name);
}

const shopSlug = q('shop') || 'kingflow-barber';

const shopNameEl = document.getElementById('shopName');
const serviceSelect = document.getElementById('serviceSelect');
const scheduledTimeSelect = document.getElementById('scheduledTime');
const bookBtn = document.getElementById('bookBtn');
const bookResult = document.getElementById('bookResult');
const trackBtn = document.getElementById('trackBtn');
const trackList = document.getElementById('trackList');
const supportBtn = document.getElementById('supportBtn');

const showBookBtn = document.getElementById('showBookBtn');
const showTrackBtn = document.getElementById('showTrackBtn');
const showSupportBtn = document.getElementById('showSupportBtn');

const bookSection = document.getElementById('bookSection');
const trackSection = document.getElementById('trackSection');
const supportSection = document.getElementById('supportSection');

function showPanel(panel) {
  if (bookSection) bookSection.style.display = panel === 'book' ? 'block' : 'none';
  if (trackSection) trackSection.style.display = panel === 'track' ? 'block' : 'none';
  if (supportSection) supportSection.style.display = panel === 'support' ? 'block' : 'none';

  const map = {
    book: showBookBtn,
    track: showTrackBtn,
    support: showSupportBtn,
  };

  [showBookBtn, showTrackBtn, showSupportBtn].forEach((btn) => {
    if (btn) btn.classList.remove('active');
  });

  if (map[panel]) {
    map[panel].classList.add('active');
  }
}

async function loadShop() {
  const res = await fetch(`${API_BASE}/public/${shopSlug}`);
  if (!res.ok) {
    shopNameEl.textContent = '❌ Barbería no disponible';
    return;
  }

  const shop = await res.json();
  shopNameEl.textContent = `💈 ${shop.name}`;
  document.title = `${shop.name} - Cliente`;

  if (shop.primary_color) {
    document.documentElement.style.setProperty('--brand-primary', shop.primary_color);
  }
  if (shop.secondary_color) {
    document.documentElement.style.setProperty('--brand-secondary', shop.secondary_color);
  }

  const sres = await fetch(`${API_BASE}/public/${shopSlug}/services`);
  const services = sres.ok ? await sres.json() : [];

  serviceSelect.innerHTML = services
    .map(s => `<option value="${s.id}">${s.name} - $${(s.price_cents / 100).toFixed(2)} (${s.duration_minutes} min)</option>`)
    .join('');

  await loadSlots();
}

async function loadSlots() {
  const res = await fetch(`${API_BASE}/public/${shopSlug}/slots`);
  const slots = res.ok ? await res.json() : [];

  if (!slots.length) {
    scheduledTimeSelect.innerHTML = '<option value="">Sin turnos disponibles</option>';
    return;
  }

  scheduledTimeSelect.innerHTML = slots.map(s => {
    const label = `${new Date(s.slot_start).toLocaleString()} · ${s.barber_name}`;
    return `<option value="${s.slot_start}">${label}</option>`;
  }).join('');
}

async function bookAppointment() {
  const client_name = document.getElementById('clientName').value.trim();
  const phone = document.getElementById('clientPhone').value.trim();
  const service_id = Number(serviceSelect.value);
  const dt = scheduledTimeSelect.value;
  const notes = document.getElementById('clientNotes').value.trim();

  if (!client_name || !phone || !service_id || !dt) {
    bookResult.textContent = 'Completa todos los campos requeridos.';
    return;
  }

  bookResult.textContent = 'Agendando...';

  const payload = {
    client_name,
    phone,
    service_id,
    scheduled_time: dt,
    notes: notes || null,
  };

  const res = await fetch(`${API_BASE}/public/${shopSlug}/appointments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) {
    bookResult.textContent = data.detail || 'No fue posible agendar la cita.';
    return;
  }

  bookResult.innerHTML = `✅ Cita creada (ID ${data.appointment_id}). <br>🔗 Seguimiento: <a href="${data.tracking_link}" target="_blank">Abrir</a>`;
  document.getElementById('trackPhone').value = phone;
  document.getElementById('trackId').value = data.appointment_id;
  await loadSlots();
}

function statusLabel(status) {
  const map = {
    pending: 'Pendiente',
    confirmed: 'Confirmada',
    in_progress: 'En proceso',
    completed: 'Completada',
    cancelled: 'Cancelada',
    no_show: 'No asistió',
  };
  return map[status] || status;
}

async function trackAppointments() {
  const phone = document.getElementById('trackPhone').value.trim();
  const idValue = document.getElementById('trackId').value.trim();
  const appointment_id = idValue ? Number(idValue) : null;

  if (!phone) {
    trackList.innerHTML = '<div class="item">Ingresa tu teléfono.</div>';
    return;
  }

  trackList.innerHTML = '<div class="item">Consultando...</div>';

  const res = await fetch(`${API_BASE}/public/${shopSlug}/track`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, appointment_id }),
  });

  const data = await res.json();
  if (!res.ok) {
    trackList.innerHTML = `<div class="item">${data.detail || 'Error de consulta.'}</div>`;
    return;
  }

  if (!data.items || data.items.length === 0) {
    trackList.innerHTML = '<div class="item">No hay citas registradas para ese teléfono.</div>';
    return;
  }

  trackList.innerHTML = data.items.map(item => {
    const d = new Date(item.scheduled_time).toLocaleString();
    return `<div class="item"><strong>ID ${item.appointment_id}</strong> • ${statusLabel(item.status)}<br>${item.service_type}<br>${d}${item.barber_name ? `<br>Barbero: ${item.barber_name}` : ''}</div>`;
  }).join('');
}

async function sendSupport() {
  const name = document.getElementById('supportName').value.trim();
  const email = document.getElementById('supportEmail').value.trim();
  const phone = document.getElementById('supportPhone').value.trim();
  const message = document.getElementById('supportMessage').value.trim();
  const result = document.getElementById('supportResult');

  if (!name || !message) {
    result.textContent = 'Nombre y mensaje son requeridos.';
    return;
  }

  result.textContent = 'Enviando...';
  const res = await fetch(`${API_BASE}/support/contact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email: email || null, phone: phone || null, message }),
  });

  const data = await res.json();
  if (!res.ok) {
    result.textContent = data.detail || 'No se pudo enviar soporte.';
    return;
  }

  result.textContent = `✅ Soporte enviado a ${data.sent_to} usuario(s).`;
}

bookBtn.addEventListener('click', bookAppointment);
trackBtn.addEventListener('click', trackAppointments);
if (supportBtn) supportBtn.addEventListener('click', sendSupport);

if (showBookBtn) showBookBtn.addEventListener('click', () => showPanel('book'));
if (showTrackBtn) showTrackBtn.addEventListener('click', () => showPanel('track'));
if (showSupportBtn) showSupportBtn.addEventListener('click', () => showPanel('support'));

window.addEventListener('DOMContentLoaded', async () => {
  showPanel('book');
  await loadShop();

  const phoneQuery = q('phone');
  const trackId = q('track');
  if (phoneQuery) document.getElementById('trackPhone').value = phoneQuery;
  if (trackId) document.getElementById('trackId').value = trackId;

  if (phoneQuery || trackId) {
    showPanel('track');
    trackAppointments();
  }
});
