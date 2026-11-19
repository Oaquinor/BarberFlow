const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');
const API_BASE = `${API_ROOT}/api/v1`;
let shopCurrency = 'USD';
let shopTimezone = 'UTC';
let availableSlots = [];
let serviceCatalog = [];

function q(name) {
  return new URLSearchParams(window.location.search).get(name);
}

const shopSlug = q('shop');

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

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function formatMoney(cents) {
  try {
    return new Intl.NumberFormat('es-DO', { style: 'currency', currency: shopCurrency }).format((Number(cents) || 0) / 100);
  } catch (_) {
    return `${shopCurrency} ${((Number(cents) || 0) / 100).toFixed(2)}`;
  }
}

async function loadShop() {
  if (!shopSlug) {
    shopNameEl.textContent = '❌ Falta identificar la barbería';
    return;
  }
  const res = await fetch(`${API_BASE}/public/${shopSlug}`);
  if (!res.ok) {
    shopNameEl.textContent = '❌ Barbería no disponible';
    return;
  }

  const shop = await res.json();
  shopCurrency = shop.currency || 'USD';
  shopTimezone = shop.timezone || 'UTC';
  shopNameEl.textContent = `💈 ${shop.name}`;
  document.title = `${shop.name} - Cliente`;

  const brandColorPattern = /^#[0-9a-f]{6}$/i;
  if (brandColorPattern.test(shop.primary_color || '')) {
    document.documentElement.style.setProperty('--brand-primary', shop.primary_color);
  }
  if (brandColorPattern.test(shop.secondary_color || '')) {
    document.documentElement.style.setProperty('--brand-secondary', shop.secondary_color);
  }
  if (shop.logo_url) {
    try {
      const logoUrl = new URL(shop.logo_url, API_ROOT);
      if (logoUrl.origin === new URL(API_ROOT).origin && ['http:', 'https:'].includes(logoUrl.protocol)) {
        const logo = document.getElementById('shopLogo');
        logo.src = logoUrl.href;
        logo.alt = `Logo de ${shop.name}`;
        logo.referrerPolicy = 'no-referrer';
        logo.hidden = false;
      }
    } catch (_) {
      // Ignore an invalid legacy logo URL and keep the booking page usable.
    }
  }

  const sres = await fetch(`${API_BASE}/public/${shopSlug}/services`);
  serviceCatalog = sres.ok ? await sres.json() : [];

  serviceSelect.innerHTML = serviceCatalog
    .map(s => `<option value="${Number(s.id)}">${escapeHtml(s.name)} - ${formatMoney(s.price_cents)} (${Number(s.duration_minutes)} min)</option>`)
    .join('');

  await loadSlots(selectedServiceDuration());
}

function selectedServiceDuration() {
  const service = serviceCatalog.find(item => Number(item.id) === Number(serviceSelect.value));
  const duration = Number(service?.duration_minutes);
  return Number.isInteger(duration) && duration > 0 ? duration : null;
}

async function fetchSlots(durationMinutes) {
  const url = new URL(`${API_BASE}/public/${shopSlug}/slots`);
  if (Number.isInteger(Number(durationMinutes)) && Number(durationMinutes) > 0) {
    url.searchParams.set('duration_minutes', String(Number(durationMinutes)));
  }
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : [];
  } catch (_) {
    return [];
  }
}

async function loadSlots(durationMinutes = selectedServiceDuration()) {
  const slots = await fetchSlots(durationMinutes);
  availableSlots = Array.isArray(slots) ? slots : [];

  if (!availableSlots.length) {
    scheduledTimeSelect.innerHTML = '<option value="">Sin turnos disponibles</option>';
    return;
  }

  scheduledTimeSelect.innerHTML = availableSlots.map(s => {
    const label = `${new Date(s.slot_start).toLocaleString('es-DO', { timeZone: shopTimezone })} · ${escapeHtml(s.barber_name)}`;
    return `<option value="${escapeHtml(s.slot_start)}">${label}</option>`;
  }).join('');
}

serviceSelect.addEventListener('change', () => loadSlots(selectedServiceDuration()));

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

  bookResult.replaceChildren();
  bookResult.append(document.createTextNode(`✅ Cita creada (ID ${Number(data.appointment_id)}). `));
  const link = document.createElement('a');
  const trackingUrl = new URL(data.tracking_link, window.location.origin);
  if (!['http:', 'https:'].includes(trackingUrl.protocol)) {
    bookResult.textContent = '✅ Cita creada. No fue posible abrir el enlace de seguimiento.';
    return;
  }
  link.href = trackingUrl.href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = 'Abrir seguimiento privado';
  bookResult.append(link);
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
  const token = document.getElementById('trackToken').value.trim();

  if (!token) {
    trackList.textContent = 'Ingresa el código privado que recibiste al reservar.';
    return;
  }

  trackList.textContent = 'Consultando...';

  const res = await fetch(`${API_BASE}/public/${shopSlug}/track`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });

  const data = await res.json();
  if (!res.ok) {
    trackList.textContent = data.detail || 'Error de consulta.';
    return;
  }

  if (!data.items || data.items.length === 0) {
    trackList.textContent = 'No se encontró una cita con ese código de seguimiento.';
    return;
  }

  const slotResults = new Map();
  const cards = await Promise.all(data.items.map(async (item) => {
    const d = new Date(item.scheduled_time).toLocaleString('es-DO', { timeZone: shopTimezone });
    const cancelButton = ['pending', 'confirmed'].includes(item.status)
      ? `<button class="secondary cancel-booking" type="button" data-token="${escapeHtml(token)}">Cancelar cita</button>`
      : '';
    const canReschedule = ['pending', 'confirmed'].includes(item.status);
    const duration = Number(item.estimated_duration);
    let availableForService = [];
    if (canReschedule) {
      if (!slotResults.has(duration)) slotResults.set(duration, fetchSlots(duration));
      availableForService = await slotResults.get(duration);
    }
    const rescheduleControls = ['pending', 'confirmed'].includes(item.status) && availableForService.length
      ? `<label class="field">Nuevo turno<select class="reschedule-slot" data-token="${escapeHtml(token)}">${availableForService.map(slot => {
          const label = `${new Date(slot.slot_start).toLocaleString('es-DO', { timeZone: shopTimezone })} · ${escapeHtml(slot.barber_name)}`;
          return `<option value="${Number(slot.availability_id)}">${label}</option>`;
        }).join('')}</select></label><button class="secondary reschedule-booking" type="button" data-token="${escapeHtml(token)}">Reprogramar cita</button>`
      : '';
    return `<div class="item"><strong>ID ${Number(item.appointment_id)}</strong> • ${escapeHtml(statusLabel(item.status))}<br>${escapeHtml(item.service_type)}<br>${escapeHtml(d)}${item.barber_name ? `<br>Barbero: ${escapeHtml(item.barber_name)}` : ''}<br>${rescheduleControls}<br>${cancelButton}</div>`;
  }));
  trackList.innerHTML = cards.join('');
}

trackList.addEventListener('click', async (event) => {
  const rescheduleButton = event.target.closest('.reschedule-booking');
  if (rescheduleButton) {
    const card = rescheduleButton.closest('.item');
    const availabilityId = Number(card?.querySelector('.reschedule-slot')?.value);
    if (!availabilityId) return;
    rescheduleButton.disabled = true;
    const response = await fetch(`${API_BASE}/public/${shopSlug}/appointments/reschedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: rescheduleButton.dataset.token, availability_id: availabilityId }),
    });
    const data = await response.json();
    if (!response.ok) {
      rescheduleButton.disabled = false;
      window.alert(data.detail || 'No se pudo reprogramar la cita.');
      return;
    }
    await loadSlots();
    await trackAppointments();
    return;
  }
  const button = event.target.closest('.cancel-booking');
  if (!button || !window.confirm('¿Quieres cancelar esta cita?')) return;
  button.disabled = true;
  const response = await fetch(`${API_BASE}/public/${shopSlug}/appointments/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: button.dataset.token }),
  });
  const data = await response.json();
  if (!response.ok) {
    button.disabled = false;
    window.alert(data.detail || 'No se pudo cancelar la cita.');
    return;
  }
  await loadSlots();
  await trackAppointments();
});

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
    body: JSON.stringify({ name, email: email || null, phone: phone || null, message, barbershop_slug: shopSlug }),
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

  const trackingToken = q('track_token');
  if (trackingToken) document.getElementById('trackToken').value = trackingToken;

  if (trackingToken) {
    showPanel('track');
    await trackAppointments();
  }
});
