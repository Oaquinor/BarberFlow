const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');

let currentUser = null;
let barbershopProfile = null;
let dashboardLayout = null;
let accessToken = null;
let serviceCache = [];
let editingServiceId = null;
let selectedAppointmentsDate = null;
let selectedAppointmentsView = 'day';
let dashboardBusinessDate = null;
let notificationRefreshTimer = null;
let serviceTimerInterval = null;
const ownerClientCache = new Map();
const ownerBarberCache = new Map();
const OWNER_CLIENTS_PAGE_SIZE = 50;
let ownerClientsOffset = 0;
let ownerClientsSearch = '';
let ownerClientsSearchTimer = null;
let ownerClientsRequestId = 0;
const OWNER_CLIENT_HISTORY_PAGE_SIZE = 20;
let ownerClientHistoryClientId = null;
let ownerClientHistoryOffset = 0;
let ownerClientHistoryRequestId = 0;

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[char]);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function updateActiveServiceTimer(startedAt, estimatedMinutes, nextAppointment) {
    if (serviceTimerInterval) clearInterval(serviceTimerInterval);
    serviceTimerInterval = null;
    if (!startedAt) {
        setText('elapsedTime', '00:00:00');
        return;
    }

    const startedAtMs = new Date(startedAt).getTime();
    if (!Number.isFinite(startedAtMs)) {
        setText('elapsedTime', '00:00:00');
        return;
    }

    const renderElapsed = () => {
        const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));
        const hours = Math.floor(elapsedSeconds / 3600);
        const minutes = Math.floor((elapsedSeconds % 3600) / 60);
        const seconds = elapsedSeconds % 60;
        setText('elapsedTime', [hours, minutes, seconds].map(value => String(value).padStart(2, '0')).join(':'));
        const durationSeconds = Math.max(1, Number(estimatedMinutes) || 0) * 60;
        const progressPct = Math.min(100, Math.floor((elapsedSeconds / durationSeconds) * 100));
        setText('activeServiceProgress', `${progressPct}%`);
        const progressBar = document.getElementById('activeServiceProgressBar');
        if (progressBar) progressBar.style.width = `${progressPct}%`;
        const alerts = [];
        if (elapsedSeconds > durationSeconds) {
            alerts.push('⚠️ El servicio superó su duración estimada.');
        } else if (progressPct >= 80) {
            alerts.push(`⏰ ${Math.ceil(durationSeconds / 60 - elapsedSeconds / 60)} minutos restantes del tiempo estimado`);
        }
        const nextAppointmentAt = nextAppointment?.scheduled_time
            ? new Date(nextAppointment.scheduled_time).getTime()
            : NaN;
        if (Number.isFinite(nextAppointmentAt)) {
            const minutesUntilNext = Math.max(0, Math.ceil((nextAppointmentAt - Date.now()) / 60000));
            if (minutesUntilNext <= 10) alerts.push(`🚨 Próxima cita en ${minutesUntilNext} minutos`);
            else if (minutesUntilNext <= 20) alerts.push(`⚠️ Próxima cita en ${minutesUntilNext} minutos`);
        }
        setText('activeServiceAlert', alerts.join(' · ') || `🔥 Servicio en curso · ${progressPct}% del tiempo estimado`);
    };

    renderElapsed();
    serviceTimerInterval = setInterval(renderElapsed, 1000);
}

function setTrend(id, delta, suffix, currency = false) {
    const el = document.getElementById(id);
    if (!el) return;

    if (currency) {
        el.textContent = `${delta >= 0 ? '↗️' : '↘️'} ${fmtMoneyFromCents(delta)} ${suffix}`;
        return;
    }

    el.textContent = `${delta >= 0 ? '↗️' : '↘️'} ${delta >= 0 ? '+' : ''}${delta}${suffix}`;
}

function renderNextAppointment(next) {
    if (!next) {
        setText('nextAppointmentTime', '--:--');
        setText('nextAppointmentEta', 'Sin próxima cita');
        setText('nextAppointmentClient', 'Agenda del día');
        setText('nextAppointmentService', 'No tienes citas próximas');
        setText('nextAppointmentDuration', '⏱️ -- min estimados');
        return;
    }

    setText('nextAppointmentTime', fmtHour(next.scheduled_time));
    setText('nextAppointmentClient', next.client_name || 'Cliente');
    setText('nextAppointmentService', next.service_type || 'Servicio');
    setText('nextAppointmentDuration', `⏱️ ${next.estimated_duration || 0} min estimados`);
    const etaEl = document.getElementById('nextAppointmentEta');
    if (etaEl) {
        const minutesUntil = Math.max(0, Math.round((new Date(next.scheduled_time) - new Date()) / 60000));
        etaEl.textContent = minutesUntil <= 1 ? 'Ahora' : `En ${minutesUntil} minutos`;
    }
}

function renderWeeklyChart(weeklyCounts) {
    const chartBars = document.getElementById('performanceChartBars');
    if (!chartBars) return;

    const data = Array.isArray(weeklyCounts) ? weeklyCounts : [];
    if (!data.length) {
        chartBars.innerHTML = '<div class="chart-bar future" style="height:100%;"><div class="bar-fill" style="height:0%"></div><span class="bar-label">-</span></div>';
        return;
    }

    chartBars.innerHTML = data.map((item) => {
        const pct = Math.max(0, Math.min(100, Number(item.height_percent) || 0));
        const isFuture = Number(item.count || 0) === 0;
        return `
            <div class="chart-bar ${isFuture ? 'future' : ''}" style="height: ${Math.max(25, pct)}%;">
                <div class="bar-fill" style="height: 100%;" title="${escapeHtml(item.label)}: ${Number(item.count) || 0} citas"></div>
                <span class="bar-label">${escapeHtml(item.label)}</span>
            </div>
        `;
    }).join('');
}

function renderAchievements(achievements) {
    const grid = document.getElementById('achievementsGrid');
    if (!grid) return;

    const items = Array.isArray(achievements?.items) ? achievements.items : [];
    if (!items.length) {
        grid.innerHTML = '<div class="achievement-card"><h4>Sin logros aún</h4><p>Completa citas para desbloquear progreso.</p></div>';
        return;
    }

    grid.innerHTML = items.map((item) => {
        const current = Number(item.current || 0);
        const target = Math.max(1, Number(item.target || 1));
        const progress = Math.min(100, Math.round((current / target) * 100));
        const unlocked = item.earned === true;

        return `
            <div class="achievement-card ${unlocked ? 'unlocked' : 'locked'}">
                <div class="achievement-icon ${unlocked ? '' : 'locked-icon'}">${unlocked ? escapeHtml(item.icon || '🏆') : '🔒'}</div>
                <h4>${escapeHtml(item.title)}</h4>
                <p>${escapeHtml(item.description)}</p>
                <div class="achievement-points">${Number(item.points) || 0} puntos</div>
                <div class="achievement-progress">
                    <div class="progress-bar small">
                        <div class="progress-fill" style="width: ${progress}%;"></div>
                    </div>
                    <span>${current}/${target}</span>
                </div>
            </div>
        `;
    }).join('');
}

function fmtMoneyFromCents(cents) {
    const value = Number(cents || 0) / 100;
    const currency = barbershopProfile?.currency || 'USD';
    try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value);
    } catch (_) {
        return `${currency} ${value.toFixed(2)}`;
    }
}

function fmtHour(dateLike) {
    const d = new Date(dateLike);
    return d.toLocaleTimeString('es-DO', {
        hour: '2-digit', minute: '2-digit',
        timeZone: barbershopProfile?.timezone || 'UTC',
    });
}

function getGoalLabel(goal) {
    const labels = {
        more_clients: 'Crecimiento',
        organization: 'Organización',
        reduce_cancellations: 'Retención',
        save_time: 'Eficiencia',
        better_service: 'Calidad',
        productivity: 'Productividad'
    };
    return labels[goal] || 'Personalizado';
}

function labelStatus(status) {
    const map = {
        pending: '📅 Pendiente',
        confirmed: '📅 Confirmada',
        in_progress: '🔥 En Servicio',
        completed: '✅ Completada',
        cancelled: '❌ Cancelada',
        no_show: '🚫 No asistió'
    };
    return map[status] || status;
}

function cardClassForStatus(status) {
    if (status === 'completed') return 'completed';
    if (status === 'in_progress') return 'in-progress';
    return 'upcoming';
}

function statusClassForStatus(status) {
    if (status === 'completed') return 'completed';
    if (status === 'in_progress') return 'in-progress';
    return 'confirmed';
}

function canMarkAppointmentNoShow(appointment, now = Date.now()) {
    const scheduledAt = Date.parse(appointment?.scheduled_time);
    const durationMinutes = Number(appointment?.estimated_duration);
    return ['pending', 'confirmed'].includes(appointment?.status) &&
        Number.isFinite(scheduledAt) && Number.isFinite(durationMinutes) && durationMinutes >= 0 &&
        now >= scheduledAt + durationMinutes * 60_000;
}

function applyBranding(profile) {
    const logoElement = document.querySelector('.logo h1');
    if (logoElement && profile?.logo_url) {
        let imageUrl;
        let apiOrigin;
        try {
            imageUrl = new URL(profile.logo_url, API_ROOT);
            apiOrigin = new URL(API_ROOT, window.location.origin).origin;
        } catch (_) {
            imageUrl = null;
        }
        logoElement.replaceChildren();
        const trustedOrigins = new Set([window.location.origin, apiOrigin]);
        if (imageUrl && trustedOrigins.has(imageUrl.origin) && ['http:', 'https:'].includes(imageUrl.protocol) &&
            !imageUrl.username && !imageUrl.password) {
            const logo = document.createElement('img');
            logo.src = imageUrl.href;
            logo.alt = '';
            logo.style.cssText = 'height:40px;vertical-align:middle;margin-right:10px';
            logoElement.append(logo);
        }
        logoElement.append(document.createTextNode(profile.name || 'KingFlow Barber'));
    } else if (logoElement && profile?.name) {
        logoElement.textContent = `👑 ${profile.name}`;
    }

    const brandColorPattern = /^#[0-9a-f]{6}$/i;
    const automaticBranding = currentUser?.feature_flags?.branding_auto === true;
    if (automaticBranding && brandColorPattern.test(profile?.primary_color || '')) {
        document.documentElement.style.setProperty('--brand-primary', profile.primary_color);
    } else {
        document.documentElement.style.setProperty('--brand-primary', '#667eea');
    }
    if (automaticBranding && brandColorPattern.test(profile?.secondary_color || '')) {
        document.documentElement.style.setProperty('--brand-secondary', profile.secondary_color);
    } else {
        document.documentElement.style.setProperty('--brand-secondary', '#764ba2');
    }

    const authHeaderTitle = document.querySelector('.auth-header h2');
    const authHeaderSubtitle = document.querySelector('.auth-header p');
    if (authHeaderTitle && profile?.name) authHeaderTitle.textContent = `Iniciar Sesión - ${profile.name}`;
    if (authHeaderSubtitle && profile?.name) authHeaderSubtitle.textContent = `Accede a tu cuenta de ${profile.name}`;
}

async function loadBarbershopProfile() {
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/profile`, {
            headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!response.ok) return true;

        barbershopProfile = await response.json();

        if (barbershopProfile && !barbershopProfile.onboarding_completed) {
            window.location.href = '/onboarding.html';
            return false;
        }

        applyBranding(barbershopProfile);
        await loadContextualGreeting();
        await loadDashboardLayout();
        await loadSmartMessages();
        return true;
    } catch (error) {
        console.error('Error loading profile:', error);
        return true;
    }
}

async function loadDashboardLayout() {
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/dashboard-layout`, {
            headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!response.ok) return;

        dashboardLayout = await response.json();
        const goalBadge = document.getElementById('goalBadge');
        if (goalBadge && barbershopProfile) {
            goalBadge.textContent = `• Enfoque: ${getGoalLabel(barbershopProfile.primary_goal)}`;
        }

        const insightsContainer = document.querySelector('.insights-list');
        if (insightsContainer && Array.isArray(dashboardLayout.insights) && dashboardLayout.insights.length) {
            insightsContainer.innerHTML = dashboardLayout.insights.map((insight, index) => `
                <div class="insight-item ${index % 2 === 0 ? 'positive' : 'warning'}">
                    <span class="insight-icon">${index % 2 === 0 ? '🎯' : '💡'}</span>
                    <div class="insight-content">
                        <h4>Insight personalizado</h4>
                    <p>${escapeHtml(insight)}</p>
                    </div>
                </div>
            `).join('');
        }

        const quickActionsTitle = document.querySelector('.quick-actions h3');
        if (quickActionsTitle && dashboardLayout.layout_type) {
            quickActionsTitle.textContent = `⚡ Acciones Rápidas • ${dashboardLayout.layout_type.toUpperCase()}`;
        }
    } catch (error) {
        console.error('Error loading dashboard layout:', error);
    }
}

async function loadSmartMessages() {
    try {
        const contextByGoal = {
            more_clients: 'high_return_rate',
            organization: 'consistent',
            reduce_cancellations: 'perfect_week',
            save_time: 'improved_speed',
            better_service: 'record_day',
            productivity: 'full_schedule'
        };

        const achievement_type = contextByGoal[barbershopProfile?.primary_goal] || 'consistent';
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/motivational-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
            body: JSON.stringify({ achievement_type })
        });

        if (!response.ok) return;

        const message = await response.json();
        const container = document.getElementById('smartMessages');
        if (container && message) {
            container.innerHTML = `
                <div style="background: rgba(255,255,255,0.95); border-left: 5px solid var(--brand-primary); padding: 14px 16px; border-radius: 12px; margin-bottom: 16px;">
                    <strong>${escapeHtml(message.icon)} ${message.type === 'celebration' ? 'Celebración' : 'Mensaje inteligente'}</strong>
                    <div style="margin-top: 6px; color: #444;">${escapeHtml(message.message)}</div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading smart message:', error);
    }
}

async function loadContextualGreeting() {
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/greeting`, {
            headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!response.ok) return;

        const greeting = await response.json();
        const greetingElement = document.getElementById('contextualGreeting');
        if (greetingElement) {
            greetingElement.innerHTML = `
                <div style="background: rgba(255,255,255,0.15); padding: 15px 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
                    <span style="font-size: 1.2em;">${escapeHtml(greeting.icon)}</span>
                    <span style="margin-left: 10px; font-weight: 600;">${escapeHtml(greeting.message)}</span>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading greeting:', error);
    }
}

async function loadShareLink() {
    if (!accessToken) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/share-link`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) return;

        const data = await response.json();
        const input = document.getElementById('shareLinkInput');
        const copyBtn = document.getElementById('copyShareLinkBtn');
        const waBtn = document.getElementById('shareWhatsappBtn');

        if (input) input.value = data.client_link;

        if (copyBtn) {
            copyBtn.onclick = async () => {
                try {
                    await navigator.clipboard.writeText(data.client_link);
                    showToast('✅ Link copiado', 'info');
                } catch (_) {
                    showToast('⚠️ No se pudo copiar automáticamente');
                }
            };
        }

        if (waBtn) {
            const shareUrl = window.KingFlowSecurity?.trustedWhatsAppShareUrl(data.whatsapp_share_link);
            waBtn.disabled = !shareUrl;
            waBtn.title = shareUrl ? 'Compartir enlace por WhatsApp' : 'El enlace de WhatsApp no es válido';
            waBtn.onclick = shareUrl
                ? () => window.open(shareUrl, '_blank', 'noopener,noreferrer')
                : null;
        }
    } catch (error) {
        console.error('Error loading share link:', error);
    }
}

async function createBarberSlots() {
    if (!accessToken) return;

    const date = document.getElementById('slotDate')?.value;
    const start_time = document.getElementById('slotStart')?.value;
    const end_time = document.getElementById('slotEnd')?.value;
    const slot_minutes = Number(document.getElementById('slotMinutes')?.value || 30);
    const result = document.getElementById('createSlotsResult');

    if (!date || !start_time || !end_time) {
        if (result) result.textContent = 'Completa fecha y rango horario';
        return;
    }

    if (result) result.textContent = 'Creando turnos...';

    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/slots`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ date, start_time, end_time, slot_minutes })
        });

        const data = await response.json();
        if (!response.ok) {
            if (result) result.textContent = data.detail || 'No se pudieron crear turnos';
            return;
        }

        if (result) result.textContent = `✅ Turnos creados: ${data.created_slots}`;
        await loadBarberDashboardData();
        await loadCashSummary();
    } catch (error) {
        console.error(error);
        if (result) result.textContent = 'Error de conexión creando turnos';
    }
}

async function createBarberAbsence(event) {
    event.preventDefault();
    const result = document.getElementById('barberAbsenceResult');
    const payload = {
        date: document.getElementById('absenceDate').value,
        start_time: document.getElementById('absenceStart').value,
        end_time: document.getElementById('absenceEnd').value,
        reason: document.getElementById('absenceReason').value.trim() || null,
    };
    if (!payload.date || !payload.start_time || !payload.end_time) {
        result.textContent = 'Completa la fecha y el rango de la ausencia.';
        return;
    }
    result.textContent = 'Registrando ausencia…';
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/absences`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo registrar la ausencia.';
            return;
        }
        result.textContent = `Ausencia registrada. ${Number(data.affected_slots) || 0} turnos existentes quedan ocultos durante ese rango.`;
        event.currentTarget.reset();
        const dateField = document.getElementById('absenceDate');
        if (dateField) dateField.value = payload.date;
        await loadBarberAbsences();
    } catch (error) {
        result.textContent = error.message || 'Error de conexión al registrar la ausencia.';
    }
}

async function loadBarberAbsences() {
    const list = document.getElementById('barberAbsenceList');
    if (!list || currentUser?.role !== 'barber') return;
    try {
        const rows = await (await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/absences`)).json();
        const timezone = barbershopProfile?.timezone || 'UTC';
        list.innerHTML = rows.map(row => `
            <li>
                ${escapeHtml(new Date(row.starts_at).toLocaleString('es-DO', { timeZone: timezone }))}
                — ${escapeHtml(new Date(row.ends_at).toLocaleTimeString('es-DO', { timeZone: timezone }))}
                · ${escapeHtml(row.reason || 'Sin motivo indicado')}
                <button type="button" class="btn-secondary cancel-barber-absence" data-id="${Number(row.id)}">Cancelar ausencia</button>
            </li>`).join('') || '<li>No tienes ausencias futuras registradas.</li>';
    } catch (error) {
        list.textContent = error.message || 'No se pudieron cargar las ausencias.';
    }
}

async function cancelBarberAbsence(event) {
    const button = event.target.closest('.cancel-barber-absence');
    if (!button || !await showConfirmation(
        '¿Cancelar esta ausencia? Los turnos originales volverán a estar disponibles.',
        { title: 'Cancelar ausencia', confirmLabel: 'Cancelar ausencia', danger: true },
    )) return;
    const result = document.getElementById('barberAbsenceResult');
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/absences/${Number(button.dataset.id)}`, {
            method: 'DELETE',
        });
        const data = await response.json();
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo cancelar la ausencia.';
            return;
        }
        result.textContent = 'Ausencia cancelada; los turnos originales vuelven a estar disponibles.';
        await loadBarberAbsences();
    } catch (error) {
        result.textContent = error.message || 'Error de conexión al cancelar la ausencia.';
    }
}

function renderAppointmentDay(businessDate, appointments) {
    const date = new Date(`${businessDate}T12:00:00`);
    setText('appointmentsDateHeader', date.toLocaleDateString('es-DO', {
        weekday: 'long', day: '2-digit', month: 'long', year: 'numeric'
    }));

    const items = Array.isArray(appointments) ? appointments : [];
    setText('summaryTotal', String(items.length));
    setText('summaryCompleted', String(items.filter((item) => item.status === 'completed').length));
    setText('summaryPending', String(items.filter((item) => ['pending', 'confirmed'].includes(item.status)).length));
    setText('summaryInProgress', String(items.filter((item) => item.status === 'in_progress').length));

    const appointmentsList = document.getElementById('appointmentsList');
    const calendar = document.getElementById('appointmentsCalendarViewport');
    if (calendar) calendar.hidden = true;
    if (appointmentsList) appointmentsList.hidden = false;
    const dateInput = document.getElementById('appointmentsAnchorDate');
    if (dateInput) dateInput.value = businessDate;
    if (!appointmentsList) return;
    if (!items.length) {
        appointmentsList.innerHTML = '<div class="appointment-card"><div class="appointment-content"><p class="service-name">No hay citas para este día.</p></div></div>';
        return;
    }
    appointmentsList.innerHTML = items.map((appointment) => `
        <div class="appointment-card ${cardClassForStatus(appointment.status)}">
            <div class="appointment-time-badge ${appointment.status === 'in_progress' ? 'current' : ''}">${fmtHour(appointment.scheduled_time)}</div>
            <div class="appointment-content">
                <div class="appointment-header">
                    <h4>${escapeHtml(appointment.client_name || 'Cliente')}</h4>
                    <span class="status-badge ${statusClassForStatus(appointment.status)}">${escapeHtml(labelStatus(appointment.status))}</span>
                </div>
                <p class="service-name">${escapeHtml(appointment.service_type || 'Servicio')}</p>
                <div class="appointment-meta">
                    <span>⏱️ ${Number(appointment.estimated_duration) || 0} min</span>
                    <span>💰 ${fmtMoneyFromCents(appointment.service_price || 0)}</span>
                </div>
                <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
                    ${appointment.status === 'pending' ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="confirmed">✅ Confirmar</button>` : ''}
                    ${['pending', 'confirmed'].includes(appointment.status) ? `<button class="btn-start appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="in_progress">▶️ Iniciar</button>` : ''}
                    ${appointment.status === 'in_progress' ? `<button class="btn-secondary appointment-payment" type="button" data-appointment-id="${Number(appointment.id)}">💳 Cobrar y finalizar</button>` : ''}
                    ${['pending', 'confirmed'].includes(appointment.status) ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="cancelled">❌ Cancelar</button>` : ''}
                    ${canMarkAppointmentNoShow(appointment) ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="no_show">🚫 No asistió</button>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

function businessTodayDate() {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: barbershopProfile?.timezone || 'UTC', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
}

function renderAppointmentCalendar(data) {
    const list = document.getElementById('appointmentsList');
    const viewport = document.getElementById('appointmentsCalendarViewport');
    const grid = document.getElementById('appointmentsCalendarGrid');
    if (!grid || !viewport || !list) return;
    list.hidden = true;
    viewport.hidden = false;
    const dateInput = document.getElementById('appointmentsAnchorDate');
    if (dateInput) dateInput.value = data.anchor_date;
    const summary = data.summary || {};
    setText('summaryTotal', String(summary.total || 0));
    setText('summaryCompleted', String(summary.completed || 0));
    setText('summaryPending', String(summary.pending || 0));
    setText('summaryInProgress', String(summary.in_progress || 0));

    const formatDate = (value, options) => new Intl.DateTimeFormat('es-DO', {
        ...options, timeZone: 'UTC',
    }).format(new Date(`${value}T12:00:00Z`));
    if (data.view === 'month') {
        setText('appointmentsDateHeader', formatDate(data.anchor_date, { month: 'long', year: 'numeric' }));
    } else {
        const lastDate = new Date(`${data.end_date_exclusive}T12:00:00Z`);
        lastDate.setUTCDate(lastDate.getUTCDate() - 1);
        const finalDay = lastDate.toISOString().slice(0, 10);
        setText('appointmentsDateHeader', `Semana · ${formatDate(data.start_date, { day: 'numeric', month: 'short' })} – ${formatDate(finalDay, { day: 'numeric', month: 'short', year: 'numeric' })}`);
    }

    const weekdays = Array.from({ length: 7 }, (_, index) => {
        const day = new Date(Date.UTC(2024, 0, 1 + index, 12));
        return `<div class="calendar-weekday">${new Intl.DateTimeFormat('es-DO', { weekday: 'short', timeZone: 'UTC' }).format(day)}</div>`;
    }).join('');
    const cells = [];
    const days = data.days || [];
    if (data.view === 'month' && days.length) {
        const firstWeekday = (new Date(`${days[0].date}T12:00:00Z`).getUTCDay() + 6) % 7;
        for (let index = 0; index < firstWeekday; index += 1) cells.push('<div class="calendar-day outside-month" aria-hidden="true"></div>');
    }
    const today = businessTodayDate();
    days.forEach(day => {
        const appointments = day.appointments || [];
        const entries = appointments.slice(0, data.view === 'month' ? 3 : 5).map(item => `
            <div class="calendar-entry ${item.status === 'completed' ? 'completed' : item.status === 'in_progress' ? 'in-progress' : ''}"
                 title="${escapeHtml(`${fmtHour(item.scheduled_time)} · ${item.client_name || 'Cliente'} · ${item.service_type || 'Servicio'}`)}">
                ${escapeHtml(fmtHour(item.scheduled_time))} · ${escapeHtml(item.service_type || 'Servicio')}
            </div>
        `).join('');
        const extraCount = appointments.length - (data.view === 'month' ? 3 : 5);
        cells.push(`
            <section class="calendar-day ${day.date === today ? 'today' : ''}">
                <div class="calendar-day-heading">
                    <button class="calendar-day-select" type="button" data-date="${escapeHtml(day.date)}" aria-label="Ver citas del ${escapeHtml(day.date)}">${Number(day.date.slice(-2))}</button>
                    <span class="calendar-day-count">${appointments.length || ''}</span>
                </div>
                ${entries}${extraCount > 0 ? `<small>+${extraCount} más</small>` : ''}
            </section>
        `);
    });
    const trailingCells = (7 - (cells.length % 7)) % 7;
    for (let index = 0; index < trailingCells; index += 1) cells.push('<div class="calendar-day outside-month" aria-hidden="true"></div>');
    grid.innerHTML = `${weekdays}${cells.join('')}`;
}

function populateWalkInServices(services) {
    const select = document.getElementById('walkInServiceSelect');
    if (!select) return;
    const current = select.value;
    select.replaceChildren(new Option('Selecciona un servicio', ''));
    (Array.isArray(services) ? services : []).forEach((service) => {
        select.add(new Option(
            `${service.name} · ${fmtMoneyFromCents(service.price_cents)}`,
            String(Number(service.id)),
        ));
    });
    if ([...select.options].some((option) => option.value === current)) select.value = current;
}

async function loadAppointmentsForDate(businessDate = selectedAppointmentsDate) {
    if (!accessToken || !businessDate) return;
    selectedAppointmentsDate = businessDate;
    const dateInput = document.getElementById('appointmentsAnchorDate');
    if (dateInput) dateInput.value = businessDate;
    setText('appointmentsDateHeader', 'Cargando agenda…');
    try {
        const endpoint = selectedAppointmentsView === 'day'
            ? `${API_ROOT}/api/v1/barber/appointments?target_date=${encodeURIComponent(businessDate)}`
            : `${API_ROOT}/api/v1/barber/appointments/calendar?view=${encodeURIComponent(selectedAppointmentsView)}&anchor_date=${encodeURIComponent(businessDate)}`;
        const response = await KingFlowAuth.fetch(
            endpoint,
            { headers: { Authorization: `Bearer ${accessToken}` } },
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo cargar la agenda');
        if (selectedAppointmentsView === 'day') renderAppointmentDay(data.business_date, data.appointments);
        else renderAppointmentCalendar(data);
    } catch (error) {
        setText('appointmentsDateHeader', 'No se pudo cargar la agenda');
        const list = document.getElementById('appointmentsList');
        if (list) list.textContent = error.message;
        const calendar = document.getElementById('appointmentsCalendarGrid');
        if (calendar) calendar.textContent = error.message;
    }
}

function changeAppointmentsDate(dayDelta) {
    const baseDate = selectedAppointmentsDate || dashboardBusinessDate || businessTodayDate();
    const target = new Date(`${baseDate}T12:00:00Z`);
    if (selectedAppointmentsView === 'week') target.setUTCDate(target.getUTCDate() + dayDelta * 7);
    else if (selectedAppointmentsView === 'month') {
        target.setUTCDate(1);
        target.setUTCMonth(target.getUTCMonth() + dayDelta);
    } else target.setUTCDate(target.getUTCDate() + dayDelta);
    loadAppointmentsForDate(target.toISOString().slice(0, 10));
}

document.getElementById('appointmentsPrevDay')?.addEventListener('click', () => changeAppointmentsDate(-1));
document.getElementById('appointmentsNextDay')?.addEventListener('click', () => changeAppointmentsDate(1));
document.getElementById('appointmentsToday')?.addEventListener('click', () => loadAppointmentsForDate(businessTodayDate()));
document.getElementById('appointmentsView')?.addEventListener('change', event => {
    selectedAppointmentsView = event.target.value;
    loadAppointmentsForDate(selectedAppointmentsDate || businessTodayDate());
});
document.getElementById('appointmentsAnchorDate')?.addEventListener('change', event => {
    if (event.target.value) loadAppointmentsForDate(event.target.value);
});
document.getElementById('appointmentsCalendarGrid')?.addEventListener('click', event => {
    const button = event.target.closest('.calendar-day-select');
    if (!button) return;
    selectedAppointmentsView = 'day';
    const viewSelect = document.getElementById('appointmentsView');
    if (viewSelect) viewSelect.value = 'day';
    loadAppointmentsForDate(button.dataset.date);
});

async function loadBarberDashboardData() {
    if (!accessToken) return;

    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/dashboard`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });

        if (!response.ok) return;

        const data = await response.json();
        const summary = data.summary || {};
        const total = Number(summary.total || 0);
        const completed = Number(summary.completed || 0);
        const pending = Number(summary.pending || 0);
        const inProgress = Number(summary.in_progress || 0);

        setText('summaryTotal', String(total));
        setText('summaryCompleted', String(completed));
        setText('summaryPending', String(pending));
        setText('summaryInProgress', String(inProgress));

        setText('statsCompletedToday', String(completed));
        setText('statsRevenueToday', fmtMoneyFromCents(summary.revenue_cents || 0));
        setText('statsEfficiency', `${Number(summary.efficiency_percent || 0)}%`);
        setText('statsPendingCount', String(pending));

        const completedDelta = Number(summary.completed_delta || 0);
        const revenueDeltaCents = Number(summary.revenue_delta_cents || 0);
        const efficiencyDelta = Number(summary.efficiency_delta || 0);

        setText('statsCompletedTrend', `${completedDelta >= 0 ? '↗️' : '↘️'} ${completedDelta >= 0 ? '+' : ''}${completedDelta} vs ayer`);
        setText('statsRevenueTrend', `${revenueDeltaCents >= 0 ? '↗️' : '↘️'} ${fmtMoneyFromCents(revenueDeltaCents)} vs ayer`);
        setText('statsEfficiencyTrend', `${efficiencyDelta >= 0 ? '↗️' : '↘️'} ${efficiencyDelta >= 0 ? '+' : ''}${efficiencyDelta}% vs ayer`);
        const businessDate = data.business_date || businessTodayDate();
        dashboardBusinessDate = businessDate;
        if (!selectedAppointmentsDate) selectedAppointmentsDate = businessDate;

        const active = data.active_appointment ||
            (Array.isArray(data.appointments) ? data.appointments : []).find((a) => a.status === 'in_progress') || null;
        if (active) {
            setText('activeServiceClient', active.client_name || 'Cliente');
            setText('activeServiceType', active.service_type || 'Servicio');
            setText('activeServiceEstimated', `${active.estimated_duration || 0} minutos`);
            updateActiveServiceTimer(active.actual_start_time, active.estimated_duration, data.next_appointment);
        } else {
            updateActiveServiceTimer(null);
            setText('activeServiceClient', 'Sin servicio activo');
            setText('activeServiceType', 'Esperando próximas citas');
            setText('activeServiceEstimated', '-- minutos');
            setText('activeServiceProgress', '0%');
            const progressBar = document.getElementById('activeServiceProgressBar');
            if (progressBar) progressBar.style.width = '0%';
            setText('activeServiceAlert', '⏳ Sin servicio activo en este momento');
        }

        renderNextAppointment(data.next_appointment);

        if (selectedAppointmentsView === 'day' && selectedAppointmentsDate === businessDate) {
            renderAppointmentDay(businessDate, data.appointments);
        } else {
            await loadAppointmentsForDate(selectedAppointmentsDate);
        }

        const servicesList = document.getElementById('servicesList');
        if (servicesList) {
            const services = Array.isArray(data.services) ? data.services : [];
            serviceCache = services;
            populateWalkInServices(services);
            if (!services.length) {
                servicesList.innerHTML = '<div class="service-item"><div class="service-info"><h4>Sin servicios activos</h4><p>Crea servicios desde tu configuración para verlos aquí.</p></div></div>';
            } else {
                servicesList.innerHTML = services.map((s) => `
                    <div class="service-item ${s.category === 'combo' ? 'featured' : ''}">
                        <div class="service-icon">✂️</div>
                        <div class="service-info">
                            <h4>${escapeHtml(s.name)}</h4>
                            <p>${escapeHtml(s.description || 'Servicio personalizado de la barbería')}</p>
                            <div class="service-meta">
                                <span class="tag">${escapeHtml(s.category || 'General')}</span>
                                <span>⏱️ ${s.duration_minutes || 0} min</span>
                            </div>
                        </div>
                        <div class="service-price">${fmtMoneyFromCents(s.price_cents || 0)}</div>
                        ${currentUser?.role === 'barbershop_owner' ? `<button class="btn-icon service-action" type="button" aria-label="Editar servicio" data-action="edit" data-service-id="${Number(s.id)}">✏️</button><button class="btn-icon service-action" type="button" aria-label="Desactivar servicio" data-action="delete" data-service-id="${Number(s.id)}">🗑️</button>` : ''}
                    </div>
                `).join('');
            }
        }

        renderWeeklyChart(data.weekly_counts);

        const achievements = data.achievements || {};
        setText('achievementUnlocked', String(Number(achievements.unlocked || 0)));
        setText('achievementPoints', String(Number(achievements.points || 0)));
        setText('achievementProgress', `${Number(achievements.progress_percent || 0)}%`);
        renderAchievements(achievements);
    } catch (error) {
        console.error('Error loading barber dashboard data:', error);
    }
}

async function ownerFetch(path, options = {}) {
    const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1${path}`, {
        ...options,
        headers: { ...(options.headers || {}), Authorization: `Bearer ${accessToken}` },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'No se pudo completar la solicitud');
    return data;
}

async function loadOwnerManagement() {
    if (currentUser?.role !== 'barbershop_owner') return;
    const settingsForm = document.getElementById('businessSettingsForm');
    if (settingsForm && barbershopProfile) {
        document.getElementById('businessSettingsName').value = barbershopProfile.name || '';
        document.getElementById('businessSettingsOpening').value = barbershopProfile.opening_time?.slice(0, 5) || '';
        document.getElementById('businessSettingsClosing').value = barbershopProfile.closing_time?.slice(0, 5) || '';
        document.getElementById('businessSettingsTimezone').value = barbershopProfile.timezone || '';
        document.getElementById('businessSettingsPrimary').value = /^#[0-9a-f]{6}$/i.test(barbershopProfile.primary_color || '') ? barbershopProfile.primary_color : '#667eea';
        document.getElementById('businessSettingsSecondary').value = /^#[0-9a-f]{6}$/i.test(barbershopProfile.secondary_color || '') ? barbershopProfile.secondary_color : '#764ba2';
        settingsForm.onsubmit = saveBusinessSettings;
    }
    const barberBody = document.getElementById('ownerBarbersBody');
    try {
        const [barberData, commissionData] = await Promise.all([
            ownerFetch('/owner/barbers'),
            ownerFetch('/owner/barber-commissions'),
        ]);
        barberBody.innerHTML = (barberData.items || []).map(barber => `
            <tr><td data-label="Nombre">${escapeHtml(barber.full_name)}</td><td data-label="Correo">${escapeHtml(barber.email)}</td>
                <td data-label="Teléfono">${escapeHtml(barber.phone || '—')}</td>
                <td data-label="Comisión (%)"><form class="owner-barber-rate-form" data-id="${Number(barber.id)}"><input aria-label="Tasa de comisión porcentual" type="number" min="0" max="100" step="0.01" value="${(Number(barber.commission_rate_basis_points || 0) / 100).toFixed(2)}" style="width:82px"><button class="btn-secondary" type="submit">Guardar</button></form></td>
                <td data-label="Estado">${barber.is_active ? 'Activo' : 'Inactivo'}</td>
                <td data-label="Acción"><button class="btn-secondary owner-barber-edit" type="button" data-id="${Number(barber.id)}">Editar</button>
                    <button class="btn-secondary owner-barber-status" type="button" data-id="${Number(barber.id)}" data-active="${barber.is_active}">${barber.is_active ? 'Desactivar' : 'Activar'}</button></td></tr>
        `).join('');
        ownerBarberCache.clear();
        (barberData.items || []).forEach(barber => ownerBarberCache.set(Number(barber.id), barber));
        renderOwnerCommissions(commissionData);
        const walkInBarberSelect = document.getElementById('walkInBarberSelect');
        if (walkInBarberSelect) {
            const selectedBarber = walkInBarberSelect.value;
            walkInBarberSelect.replaceChildren(new Option('Selecciona un barbero', ''));
            (barberData.items || []).filter((barber) => barber.is_active).forEach((barber) => {
                walkInBarberSelect.add(new Option(barber.full_name, String(Number(barber.id))));
            });
            if ([...walkInBarberSelect.options].some((option) => option.value === selectedBarber)) {
                walkInBarberSelect.value = selectedBarber;
            }
        }
        await loadOwnerClients();
        await loadDemandForecast();
    } catch (error) {
        barberBody.textContent = '';
        const clientsResult = document.getElementById('ownerClientsResult');
        if (clientsResult) clientsResult.textContent = error.message || 'No se pudo cargar la administración.';
    }
}

async function loadOwnerClients() {
    const body = document.getElementById('ownerClientsBody');
    const result = document.getElementById('ownerClientsResult');
    if (!body || !result || currentUser?.role !== 'barbershop_owner') return;
    const requestId = ++ownerClientsRequestId;
    const query = new URLSearchParams({
        limit: String(OWNER_CLIENTS_PAGE_SIZE),
        offset: String(ownerClientsOffset),
    });
    if (ownerClientsSearch) query.set('search', ownerClientsSearch);
    result.textContent = 'Buscando clientes…';
    body.replaceChildren();
    ownerClientCache.clear();
    const previousClients = document.getElementById('previousOwnerClients');
    const nextClients = document.getElementById('nextOwnerClients');
    if (previousClients) previousClients.disabled = true;
    if (nextClients) nextClients.disabled = true;
    try {
        const data = await ownerFetch(`/owner/clients?${query.toString()}`);
        if (requestId !== ownerClientsRequestId) return;
        const clients = data.items || [];
        const totalClients = Number(data.total) || 0;
        clients.forEach(client => ownerClientCache.set(Number(client.id), client));
        const pageLabel = document.getElementById('ownerClientsPage');
        if (pageLabel) pageLabel.textContent = totalClients
            ? `Clientes ${ownerClientsOffset + 1}–${ownerClientsOffset + clients.length} de ${totalClients}`
            : '0 clientes';
        if (previousClients) previousClients.disabled = ownerClientsOffset === 0;
        if (nextClients) nextClients.disabled = ownerClientsOffset + clients.length >= totalClients;
        body.innerHTML = clients.map(client => `
            <tr><td data-label="Cliente">${escapeHtml(client.full_name)}</td><td data-label="Teléfono">${escapeHtml(client.phone || '—')}</td>
                <td data-label="Citas">${Number(client.appointment_count || 0)}</td><td data-label="Completadas">${Number(client.completed_count || 0)}</td>
                <td data-label="Última visita">${client.last_visit ? escapeHtml(new Date(client.last_visit).toLocaleString('es-DO', { timeZone: barbershopProfile?.timezone || 'UTC' })) : '—'}</td>
                <td data-label="Total pagado">${fmtMoneyFromCents(client.total_paid_cents || 0)}</td><td data-label="Estado">${client.is_active ? 'Activo' : 'Inactivo'}</td>
                <td data-label="Acciones"><button class="btn-secondary owner-client-history" type="button" data-id="${Number(client.id)}">Historial</button><button class="btn-secondary owner-client-edit" type="button" data-id="${Number(client.id)}">Editar</button>
                    <button class="btn-secondary owner-client-status" type="button" data-id="${Number(client.id)}" data-active="${client.is_active}">${client.is_active ? 'Desactivar' : 'Activar'}</button></td></tr>
        `).join('');
        result.textContent = ownerClientsSearch
            ? `${totalClients} cliente(s) coinciden con la búsqueda`
            : `${clients.length} clientes cargados en esta página`;
    } catch (error) {
        if (requestId !== ownerClientsRequestId) return;
        body.textContent = '';
        result.textContent = error.message || 'No se pudieron cargar los clientes.';
    }
}

async function loadOwnerClientHistory() {
    const dialog = document.getElementById('ownerClientHistoryDialog');
    const list = document.getElementById('ownerClientHistoryItems');
    const result = document.getElementById('ownerClientHistoryResult');
    if (!dialog?.open || !list || !result || !ownerClientHistoryClientId
        || currentUser?.role !== 'barbershop_owner') return;
    const requestId = ++ownerClientHistoryRequestId;
    const query = new URLSearchParams({
        limit: String(OWNER_CLIENT_HISTORY_PAGE_SIZE),
        offset: String(ownerClientHistoryOffset),
    });
    result.textContent = 'Cargando historial…';
    list.replaceChildren();
    const previous = document.getElementById('previousOwnerClientHistory');
    const next = document.getElementById('nextOwnerClientHistory');
    if (previous) previous.disabled = true;
    if (next) next.disabled = true;
    try {
        const data = await ownerFetch(
            `/owner/clients/${Number(ownerClientHistoryClientId)}/appointments?${query.toString()}`,
        );
        if (requestId !== ownerClientHistoryRequestId) return;
        const items = data.items || [];
        const total = Number(data.total) || 0;
        const timezone = barbershopProfile?.timezone || 'UTC';
        const statusLabels = {
            pending: 'Pendiente', confirmed: 'Confirmada', in_progress: 'En servicio',
            completed: 'Completada', cancelled: 'Cancelada', no_show: 'No asistió',
        };
        const methodLabels = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', other: 'Otro' };
        list.innerHTML = items.map((item) => {
            const payment = item.payment;
            const paymentSummary = payment
                ? `Cobro: ${fmtMoneyFromCents(Number(payment.amount_cents || 0) + Number(payment.tip_cents || 0))} ${escapeHtml(payment.currency)} · ${escapeHtml(methodLabels[payment.method] || payment.method)}${Number(payment.tip_cents) > 0 ? ` (incluye propina de ${fmtMoneyFromCents(payment.tip_cents)})` : ''}`
                : 'Sin cobro registrado';
            const actualDuration = item.actual_duration == null
                ? '' : ` · Atención real: ${Number(item.actual_duration)} min`;
            return `<article class="appointment-card">
                <div class="appointment-header"><h4>${escapeHtml(item.service_type)}</h4><span class="status-badge">${escapeHtml(statusLabels[item.status] || item.status)}</span></div>
                <p>${escapeHtml(new Date(item.scheduled_time).toLocaleString('es-DO', { timeZone: timezone }))} · ${Number(item.estimated_duration)} min estimados${actualDuration}</p>
                <p>Barbero: ${escapeHtml(item.barber_name || 'No disponible')} · Precio del servicio: ${fmtMoneyFromCents(item.service_price_cents || 0)}</p>
                <p>${paymentSummary}</p>
                ${payment ? `<small>Pago recibido: ${escapeHtml(new Date(payment.received_at).toLocaleString('es-DO', { timeZone: timezone }))}</small>` : ''}
            </article>`;
        }).join('') || '<p>Este cliente aún no tiene citas registradas.</p>';
        const page = document.getElementById('ownerClientHistoryPage');
        if (page) page.textContent = total
            ? `Citas ${ownerClientHistoryOffset + 1}–${ownerClientHistoryOffset + items.length} de ${total}`
            : '0 citas';
        if (previous) previous.disabled = ownerClientHistoryOffset === 0;
        if (next) next.disabled = ownerClientHistoryOffset + items.length >= total;
        result.textContent = `${total} cita(s) en el historial`;
    } catch (error) {
        if (requestId !== ownerClientHistoryRequestId) return;
        list.textContent = '';
        result.textContent = error.message || 'No se pudo cargar el historial.';
    }
}

document.getElementById('previousOwnerClientHistory')?.addEventListener('click', async () => {
    if (ownerClientHistoryOffset <= 0) return;
    ownerClientHistoryOffset = Math.max(0, ownerClientHistoryOffset - OWNER_CLIENT_HISTORY_PAGE_SIZE);
    await loadOwnerClientHistory();
});

document.getElementById('nextOwnerClientHistory')?.addEventListener('click', async () => {
    if (document.getElementById('nextOwnerClientHistory')?.disabled) return;
    ownerClientHistoryOffset += OWNER_CLIENT_HISTORY_PAGE_SIZE;
    await loadOwnerClientHistory();
});

document.getElementById('closeOwnerClientHistory')?.addEventListener('click', () => {
    document.getElementById('ownerClientHistoryDialog')?.close();
});

document.getElementById('ownerClientHistoryDialog')?.addEventListener('close', () => {
    ownerClientHistoryRequestId += 1;
    ownerClientHistoryClientId = null;
    ownerClientHistoryOffset = 0;
});

document.getElementById('previousOwnerClients')?.addEventListener('click', async () => {
    if (ownerClientsOffset <= 0) return;
    ownerClientsOffset = Math.max(0, ownerClientsOffset - OWNER_CLIENTS_PAGE_SIZE);
    await loadOwnerClients();
});

document.getElementById('nextOwnerClients')?.addEventListener('click', async () => {
    if (document.getElementById('nextOwnerClients')?.disabled) return;
    ownerClientsOffset += OWNER_CLIENTS_PAGE_SIZE;
    await loadOwnerClients();
});

document.getElementById('ownerClientSearch')?.addEventListener('input', (event) => {
    ownerClientsSearch = event.currentTarget.value.trim();
    ownerClientsOffset = 0;
    ownerClientsRequestId += 1;
    document.getElementById('ownerClientsBody')?.replaceChildren();
    const clientsResult = document.getElementById('ownerClientsResult');
    if (clientsResult) clientsResult.textContent = 'Buscando clientes…';
    ownerClientCache.clear();
    const previousClients = document.getElementById('previousOwnerClients');
    const nextClients = document.getElementById('nextOwnerClients');
    if (previousClients) previousClients.disabled = true;
    if (nextClients) nextClients.disabled = true;
    clearTimeout(ownerClientsSearchTimer);
    ownerClientsSearchTimer = setTimeout(loadOwnerClients, 250);
});

async function loadOwnerSubscription() {
    const summary = document.getElementById('ownerSubscriptionSummary');
    if (!summary || currentUser?.role !== 'barbershop_owner') return;
    summary.textContent = 'Consultando suscripción y uso…';
    try {
        const data = await ownerFetch('/billing/subscription');
        const planLabels = { free: 'Free', basic: 'Basic', professional: 'Professional', enterprise: 'Enterprise' };
        const statusLabels = { active: 'Activa', expired: 'Vencida', cancelled: 'Cancelada', suspended: 'Suspendida', inactive: 'Inactiva' };
        const dateOptions = { dateStyle: 'medium', timeZone: barbershopProfile?.timezone || 'UTC' };
        const usageLabels = { barbers: 'Barberos', appointments: 'Citas del periodo', clients: 'Clientes' };
        const usage = Object.entries(data.usage || {}).map(([key, item]) => {
            const limit = item.limit == null ? 'sin límite' : String(Number(item.limit));
            return `<div class="stat-card"><div class="stat-value">${Number(item.used)} / ${escapeHtml(limit)}</div><div class="stat-label">${escapeHtml(usageLabels[key] || key)}</div></div>`;
        }).join('');
        summary.innerHTML = `<p><strong>${escapeHtml(planLabels[data.plan] || data.plan)}</strong> · ${escapeHtml(statusLabels[data.status] || data.status)} · ${Number(data.days_remaining)} días restantes</p>
            <p>Periodo: ${escapeHtml(new Date(data.current_period_start).toLocaleDateString('es-DO', dateOptions))} – ${escapeHtml(new Date(data.current_period_end).toLocaleDateString('es-DO', dateOptions))}.</p>
            <p>Renovación manual: cada periodo requiere que un administrador registre el pago recibido. El sistema no procesa ni programa cargos automáticos.</p>
            <div class="stats-grid">${usage}</div>`;
    } catch (error) {
        summary.textContent = error.message || 'No se pudo cargar el estado del plan.';
    }
}

document.getElementById('refreshOwnerSubscription')?.addEventListener('click', loadOwnerSubscription);

document.getElementById('ownerClientsBody')?.addEventListener('click', async (event) => {
    const historyButton = event.target.closest('.owner-client-history');
    const editButton = event.target.closest('.owner-client-edit');
    const statusButton = event.target.closest('.owner-client-status');
    if (historyButton && currentUser?.role === 'barbershop_owner') {
        const client = ownerClientCache.get(Number(historyButton.dataset.id));
        if (!client) return;
        ownerClientHistoryClientId = client.id;
        ownerClientHistoryOffset = 0;
        document.getElementById('ownerClientHistoryTitle').textContent = `Historial · ${client.full_name}`;
        document.getElementById('ownerClientHistoryDialog').showModal();
        await loadOwnerClientHistory();
        return;
    }
    if (editButton && currentUser?.role === 'barbershop_owner') {
        const client = ownerClientCache.get(Number(editButton.dataset.id));
        if (!client) return;
        document.getElementById('ownerClientEditId').value = String(client.id);
        document.getElementById('ownerClientFirstName').value = client.first_name || '';
        document.getElementById('ownerClientLastName').value = client.last_name || '';
        document.getElementById('ownerClientPhone').value = client.phone || '';
        document.getElementById('ownerClientEditForm').hidden = false;
        document.getElementById('ownerClientsResult').textContent = '';
        return;
    }
    if (!statusButton || currentUser?.role !== 'barbershop_owner') return;
    const nextActive = statusButton.dataset.active !== 'true';
    if (!await showConfirmation(`${nextActive ? 'Reactivar' : 'Desactivar'} este acceso de cliente?`, {
        title: `${nextActive ? 'Reactivar' : 'Desactivar'} cliente`,
        confirmLabel: nextActive ? 'Reactivar' : 'Desactivar', danger: !nextActive,
    })) return;
    const result = document.getElementById('ownerClientsResult');
    try {
        await ownerFetch(`/owner/clients/${Number(statusButton.dataset.id)}/status`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: nextActive }),
        });
        await loadOwnerManagement();
        result.textContent = `Acceso de cliente ${nextActive ? 'activado' : 'desactivado'}; su historial se conserva.`;
    } catch (error) {
        result.textContent = error.message;
    }
});

document.getElementById('showOwnerClientCreate')?.addEventListener('click', () => {
    if (currentUser?.role !== 'barbershop_owner') return;
    document.getElementById('ownerClientCreateForm').hidden = false;
    document.getElementById('ownerClientCreateFirstName').focus();
    document.getElementById('ownerClientsResult').textContent = '';
});

document.getElementById('cancelOwnerClientCreate')?.addEventListener('click', () => {
    const form = document.getElementById('ownerClientCreateForm');
    form.reset();
    form.hidden = true;
});

document.getElementById('ownerClientCreateForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (currentUser?.role !== 'barbershop_owner') return;
    const form = document.getElementById('ownerClientCreateForm');
    const result = document.getElementById('ownerClientsResult');
    try {
        const created = await ownerFetch('/owner/clients', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                first_name: document.getElementById('ownerClientCreateFirstName').value.trim(),
                last_name: document.getElementById('ownerClientCreateLastName').value.trim(),
                phone: document.getElementById('ownerClientCreatePhone').value.trim(),
            }),
        });
        form.reset();
        form.hidden = true;
        ownerClientsOffset = 0;
        ownerClientsSearch = '';
        const searchInput = document.getElementById('ownerClientSearch');
        if (searchInput) searchInput.value = '';
        await loadOwnerManagement();
        result.textContent = `Cliente ${created.full_name} registrado.`;
    } catch (error) {
        result.textContent = error.message || 'No se pudo registrar el cliente.';
    }
});

document.getElementById('ownerClientEditForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (currentUser?.role !== 'barbershop_owner') return;
    const form = document.getElementById('ownerClientEditForm');
    const result = document.getElementById('ownerClientsResult');
    const clientId = Number(document.getElementById('ownerClientEditId').value);
    try {
        await ownerFetch(`/owner/clients/${clientId}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                first_name: document.getElementById('ownerClientFirstName').value.trim(),
                last_name: document.getElementById('ownerClientLastName').value.trim(),
                phone: document.getElementById('ownerClientPhone').value.trim() || null,
            }),
        });
        form.hidden = true;
        await loadOwnerManagement();
        result.textContent = 'Datos del cliente guardados; su historial de citas y cobros se conserva.';
    } catch (error) {
        result.textContent = error.message;
    }
});

document.getElementById('cancelOwnerClientEdit')?.addEventListener('click', () => {
    document.getElementById('ownerClientEditForm').hidden = true;
});

async function saveBusinessSettings(event) {
    event.preventDefault();
    const result = document.getElementById('businessSettingsResult');
    const payload = {
        name: document.getElementById('businessSettingsName').value.trim(),
        opening_time: document.getElementById('businessSettingsOpening').value,
        closing_time: document.getElementById('businessSettingsClosing').value,
        timezone: document.getElementById('businessSettingsTimezone').value.trim(),
        primary_color: document.getElementById('businessSettingsPrimary').value,
        secondary_color: document.getElementById('businessSettingsSecondary').value,
    };
    if (payload.timezone !== barbershopProfile?.timezone && !await showConfirmation(
        'Cambiar la zona horaria cambiará cómo se muestran las horas de todas las citas existentes. ¿Continuar?'
        , { title: 'Confirmar cambio de zona horaria', confirmLabel: 'Guardar cambios' }
    )) return;
    result.textContent = 'Guardando configuración…';
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/business-settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo guardar la configuración.';
            return;
        }
        barbershopProfile = data;
        applyBranding(data);
        result.textContent = 'Configuración guardada y aplicada al negocio.';
        await loadBarberDashboardData();
        await loadOwnerManagement();
    } catch (error) {
        result.textContent = error.message || 'Error de conexión al guardar la configuración.';
    }
}

function renderDemandForecast(data) {
    const summary = document.getElementById('demandForecastSummary');
    const insights = document.getElementById('demandForecastInsights');
    const daysContainer = document.getElementById('demandForecastDays');
    if (!summary || !insights || !daysContainer) return;

    const historyCount = Number(data.completed_services_in_history) || 0;
    const historyState = data.sufficient_history ? 'Historial suficiente para una referencia orientativa.' : 'Historial limitado; se muestran las reservas ya conocidas.';
    summary.textContent = `${historyCount} servicios completados · período ${data.history_start} a ${data.history_end}. ${historyState}`;
    insights.innerHTML = (Array.isArray(data.insights) ? data.insights : [])
        .map(message => `<li>${escapeHtml(message)}</li>`).join('');
    daysContainer.innerHTML = (Array.isArray(data.forecast) ? data.forecast : []).map(day => {
        const dateLabel = new Date(`${day.date}T12:00:00Z`).toLocaleDateString('es-DO', {
            weekday: 'long', day: 'numeric', month: 'short', timeZone: 'UTC',
        });
        const peakText = (day.peak_hours || []).map(hour =>
            `${escapeHtml(hour.hour)} · ${Number(hour.expected_appointments).toFixed(1)}`
        ).join('<br>') || 'Sin hora pico identificada';
        return `<article class="demand-forecast-day">
            <h4>${escapeHtml(dateLabel)}</h4>
            <p><strong>${Number(day.expected_appointments).toFixed(1)}</strong> servicios estimados</p>
            <p>${Number(day.known_bookings) || 0} reservas conocidas · confianza ${escapeHtml(day.confidence)}</p>
            <p><strong>Horas de mayor volumen</strong><br>${peakText}</p>
        </article>`;
    }).join('');
}

async function loadDemandForecast() {
    const summary = document.getElementById('demandForecastSummary');
    if (currentUser?.role !== 'barbershop_owner' || !summary) return;
    summary.textContent = 'Actualizando pronóstico…';
    try {
        const data = await ownerFetch('/analytics/demand-forecast');
        renderDemandForecast(data);
    } catch (error) {
        summary.textContent = error.message || 'No se pudo cargar el pronóstico';
    }
}

document.getElementById('refreshDemandForecast')?.addEventListener('click', loadDemandForecast);

function renderOwnerCommissions(data) {
    const body = document.getElementById('ownerCommissionsBody');
    const totals = document.getElementById('ownerCommissionTotals');
    const result = document.getElementById('ownerCommissionsResult');
    if (!body) return;
    const describeTotals = (rows) => (rows || []).map(row =>
        fmtMoneyFromCents(row.amount_cents)
    ).join(' · ') || fmtMoneyFromCents(0);
    if (totals) totals.textContent = `Pendiente: ${describeTotals(data.pending_totals_by_currency)} · Pagado: ${describeTotals(data.paid_totals_by_currency)}`;
    body.innerHTML = (data.items || []).map(row => `
        <tr><td data-label="Barbero">${escapeHtml(row.barber_name)}</td>
            <td data-label="Fecha">${escapeHtml(new Date(row.accrued_at).toLocaleString('es-DO', { timeZone: barbershopProfile?.timezone || 'UTC' }))}</td>
            <td data-label="Importe">${fmtMoneyFromCents(row.amount_cents)}</td>
            <td data-label="Tasa">${(Number(row.rate_basis_points) / 100).toFixed(2)}%</td>
            <td data-label="Estado">${row.status === 'paid' ? 'Pagada' : 'Pendiente'}</td>
            <td data-label="Liquidación">${row.status === 'pending' ? `<select class="owner-commission-method" aria-label="Método de pago"><option value="bank_transfer">Transferencia</option><option value="cash">Efectivo</option><option value="card">Tarjeta</option><option value="other">Otro</option></select><input class="owner-commission-reference" maxlength="120" aria-label="Referencia de pago" placeholder="Referencia (opcional)"><button class="btn-secondary owner-commission-pay" type="button" data-id="${Number(row.id)}">Registrar pago</button>` : `${escapeHtml(row.payment_method || '')}${row.payment_reference ? ` · ${escapeHtml(row.payment_reference)}` : ''}`}</td></tr>
    `).join('');
    if (result) result.textContent = `${(data.items || []).length} registros recientes (máximo 200)`;
}

async function loadBarberCommissionSummary() {
    const card = document.getElementById('barberCommissionCard');
    const summary = document.getElementById('barberCommissionSummary');
    if (!card || currentUser?.role !== 'barber') return;
    card.hidden = false;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/commissions`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar las comisiones');
        const total = (items) => (items || []).map(row =>
            fmtMoneyFromCents(row.amount_cents)
        ).join(' · ') || fmtMoneyFromCents(0);
        summary.textContent = `Pendientes: ${total(data.pending_totals_by_currency)} · Pagadas: ${total(data.paid_totals_by_currency)}`;
    } catch (error) {
        summary.textContent = error.message;
    }
}

async function createOwnerBarber(event) {
    event.preventDefault();
    const result = document.getElementById('createBarberResult');
    const payload = {
        first_name: document.getElementById('newBarberFirstName').value.trim(),
        last_name: document.getElementById('newBarberLastName').value.trim(),
        email: document.getElementById('newBarberEmail').value.trim(),
        phone: document.getElementById('newBarberPhone').value.trim() || null,
        password: document.getElementById('newBarberPassword').value,
    };
    result.textContent = 'Creando acceso…';
    try {
        const barber = await ownerFetch('/owner/barbers', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        document.getElementById('createBarberForm').reset();
        result.textContent = `Acceso creado para ${barber.full_name} (${barber.email}). Entrega la contraseña inicial de forma segura.`;
        await loadOwnerManagement();
    } catch (error) {
        result.textContent = error.message;
    }
}

document.getElementById('createBarberForm')?.addEventListener('submit', createOwnerBarber);
document.getElementById('refreshOwnerManagement')?.addEventListener('click', loadOwnerManagement);
document.getElementById('ownerBarbersBody')?.addEventListener('click', async event => {
    const editButton = event.target.closest('.owner-barber-edit');
    if (editButton && currentUser?.role === 'barbershop_owner') {
        const barber = ownerBarberCache.get(Number(editButton.dataset.id));
        if (!barber) return;
        document.getElementById('ownerBarberEditId').value = String(barber.id);
        document.getElementById('ownerBarberFirstName').value = barber.first_name || '';
        document.getElementById('ownerBarberLastName').value = barber.last_name || '';
        document.getElementById('ownerBarberPhone').value = barber.phone || '';
        document.getElementById('ownerBarberEditForm').hidden = false;
        document.getElementById('ownerBarbersResult').textContent = '';
        return;
    }
    const button = event.target.closest('.owner-barber-status');
    if (!button) return;
    button.disabled = true;
    try {
        await ownerFetch(`/owner/barbers/${Number(button.dataset.id)}/status`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: button.dataset.active !== 'true' }),
        });
        await loadOwnerManagement();
    } catch (error) {
        button.disabled = false;
        const result = document.getElementById('createBarberResult');
        if (result) result.textContent = error.message;
    }
});
document.getElementById('ownerBarberEditForm')?.addEventListener('submit', async event => {
    event.preventDefault();
    if (currentUser?.role !== 'barbershop_owner') return;
    const form = document.getElementById('ownerBarberEditForm');
    const button = form.querySelector('button[type="submit"]');
    const result = document.getElementById('ownerBarbersResult');
    button.disabled = true;
    try {
        const barberId = Number(document.getElementById('ownerBarberEditId').value);
        await ownerFetch(`/owner/barbers/${barberId}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                first_name: document.getElementById('ownerBarberFirstName').value.trim(),
                last_name: document.getElementById('ownerBarberLastName').value.trim(),
                phone: document.getElementById('ownerBarberPhone').value.trim() || null,
            }),
        });
        form.hidden = true;
        await loadOwnerManagement();
        result.textContent = 'Ficha del barbero guardada.';
    } catch (error) {
        result.textContent = error.message || 'No se pudo guardar la ficha del barbero.';
    } finally {
        button.disabled = false;
    }
});
document.getElementById('cancelOwnerBarberEdit')?.addEventListener('click', () => {
    const form = document.getElementById('ownerBarberEditForm');
    form.reset();
    form.hidden = true;
});
document.getElementById('ownerBarbersBody')?.addEventListener('submit', async event => {
    const form = event.target.closest('.owner-barber-rate-form');
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector('input');
    const rate = Number(input.value);
    const button = form.querySelector('button');
    button.disabled = true;
    try {
        await ownerFetch(`/owner/barbers/${Number(form.dataset.id)}/commission-rate`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rate_basis_points: Math.round(rate * 100) }),
        });
        await loadOwnerManagement();
    } catch (error) {
        const result = document.getElementById('createBarberResult');
        if (result) result.textContent = error.message;
        button.disabled = false;
    }
});
document.getElementById('refreshOwnerCommissions')?.addEventListener('click', loadOwnerManagement);
document.getElementById('ownerCommissionsBody')?.addEventListener('click', async event => {
    const button = event.target.closest('.owner-commission-pay');
    if (!button) return;
    const row = button.closest('tr');
    button.disabled = true;
    try {
        await ownerFetch(`/owner/barber-commissions/${Number(button.dataset.id)}/pay`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                payment_method: row.querySelector('.owner-commission-method').value,
                payment_reference: row.querySelector('.owner-commission-reference').value.trim() || null,
            }),
        });
        await loadOwnerManagement();
    } catch (error) {
        const result = document.getElementById('ownerCommissionsResult');
        if (result) result.textContent = error.message;
        button.disabled = false;
    }
});

document.getElementById('walkInForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('walkInResult');
    const payload = {
        client_name: document.getElementById('walkInClientName').value.trim(),
        phone: document.getElementById('walkInClientPhone').value.trim(),
        service_id: Number(document.getElementById('walkInServiceSelect').value),
    };
    if (currentUser?.role === 'barbershop_owner') {
        payload.barber_id = Number(document.getElementById('walkInBarberSelect').value);
    }
    result.textContent = 'Registrando y comenzando el servicio…';
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/appointments/walk-in`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo registrar el turno');
        event.currentTarget.reset();
        result.textContent = `Servicio iniciado para ${data.client_name}: ${data.service_type}.`;
        selectedAppointmentsDate = dashboardBusinessDate;
        await loadBarberDashboardData();
    } catch (error) {
        result.textContent = error.message;
    }
});

async function sendLoginSupportRequest() {
    const result = document.getElementById('loginSupportResult');
    const name = document.getElementById('loginSupportName')?.value.trim();
    const email = document.getElementById('loginSupportEmail')?.value.trim();
    const phone = document.getElementById('loginSupportPhone')?.value.trim();
    const message = document.getElementById('loginSupportMessage')?.value.trim();

    if (!result) return;
    if (!name || !message) {
        result.textContent = 'Nombre y mensaje son requeridos.';
        return;
    }

    result.textContent = 'Enviando solicitud...';
    try {
        const response = await fetch(`${API_ROOT}/api/v1/support/contact`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email: email || null, phone: phone || null, message })
        });

        const data = await response.json();
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo enviar la solicitud.';
            return;
        }

        result.textContent = data.notification_sent
            ? `✅ Solicitud #${Number(data.ticket_id)} recibida; se envió un aviso al equipo.`
            : `✅ Solicitud #${Number(data.ticket_id)} recibida y guardada. El aviso por correo no está disponible ahora.`;
    } catch (error) {
        console.error('Error sending login support:', error);
        result.textContent = 'Error de conexión al enviar soporte.';
    }
}

function setupLoginSupportPanel() {
    const toggleBtn = document.getElementById('toggleLoginSupportBtn');
    const panel = document.getElementById('loginSupportPanel');
    const sendBtn = document.getElementById('sendLoginSupportBtn');

    if (toggleBtn && panel) {
        toggleBtn.addEventListener('click', () => {
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        });
    }

    if (sendBtn) {
        sendBtn.addEventListener('click', sendLoginSupportRequest);
    }
}

async function testConnection() {
    const resultDiv = document.getElementById('connectionResult');
    if (!resultDiv) return;

    resultDiv.textContent = 'Probando conexión...';

    try {
        const response = await fetch(`${API_ROOT}/health`);
        if (response.ok) {
            const data = await response.json();
            resultDiv.replaceChildren();
            const message = document.createElement('p');
            message.className = 'success-message';
            message.textContent = `✅ Conexión Exitosa · API: ${data.status} · MySQL: ${data.database}`;
            resultDiv.append(message);
        } else {
            resultDiv.textContent = response.status === 503
                ? 'API disponible, pero MySQL no responde.'
                : `El backend respondió con estado HTTP ${response.status}.`;
        }
    } catch (error) {
        resultDiv.textContent = `❌ No se puede conectar al backend ${API_ROOT}. Verifica que esté corriendo.`;
    }
}

function showTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

    const selectedTab = [...document.querySelectorAll('.tab[data-tab]')]
        .find((tab) => tab.dataset.tab === tabName);
    if (selectedTab) selectedTab.classList.add('active');

    const content = document.getElementById(`${tabName}Tab`);
    if (content) content.style.display = 'block';
    if (tabName === 'ownerManagement' && currentUser?.role === 'barbershop_owner') {
        void loadOwnerSubscription();
    }
}

async function loadNotificationInbox() {
    const list = document.getElementById('notificationInboxItems');
    const result = document.getElementById('notificationInboxResult');
    if (!list || !currentUser) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/notifications?limit=50`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudieron cargar las notificaciones');
        document.getElementById('notificationUnreadCount').textContent = String(Number(data.unread_count) || 0);
        list.replaceChildren();
        (data.items || []).forEach(item => {
            const row = document.createElement('li');
            row.style.cssText = 'display:flex;justify-content:space-between;align-items:flex-start;gap:12px;border:1px solid #e4e4e7;border-radius:10px;padding:12px;';
            const content = document.createElement('div');
            const title = document.createElement('strong');
            title.textContent = item.title;
            const message = document.createElement('p');
            message.textContent = item.message;
            const timestamp = document.createElement('small');
            timestamp.textContent = new Date(item.created_at).toLocaleString('es-DO', {
                timeZone: barbershopProfile?.timezone || 'UTC',
            });
            content.append(title, message, timestamp);
            row.append(content);
            if (!item.read_at) {
                const readButton = document.createElement('button');
                readButton.type = 'button';
                readButton.className = 'btn-secondary notification-mark-read';
                readButton.dataset.id = String(Number(item.id));
                readButton.textContent = 'Marcar leída';
                row.append(readButton);
            }
            list.append(row);
        });
        if (result) result.textContent = data.items?.length ? `${data.items.length} notificaciones recientes` : 'No tienes notificaciones.';
    } catch (error) {
        if (result) result.textContent = error.message;
    }
}

async function loadNotificationUnreadCount() {
    const count = document.getElementById('notificationUnreadCount');
    if (!count || !currentUser) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/notifications/unread-count`);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo actualizar el contador');
        count.textContent = String(Number(data.unread_count) || 0);
    } catch (error) {
        const panel = document.getElementById('inAppNotificationInbox');
        const result = document.getElementById('notificationInboxResult');
        if (panel && !panel.hidden && result) result.textContent = error.message;
    }
}

async function refreshNotificationInbox() {
    const panel = document.getElementById('inAppNotificationInbox');
    if (panel && !panel.hidden) {
        await loadNotificationInbox();
    } else {
        await loadNotificationUnreadCount();
    }
}

document.getElementById('notificationInboxButton')?.addEventListener('click', async () => {
    const panel = document.getElementById('inAppNotificationInbox');
    const button = document.getElementById('notificationInboxButton');
    panel.hidden = !panel.hidden;
    button.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) await loadNotificationInbox();
});
document.getElementById('refreshNotificationInbox')?.addEventListener('click', loadNotificationInbox);
document.getElementById('closeNotificationInbox')?.addEventListener('click', () => {
    document.getElementById('inAppNotificationInbox').hidden = true;
    document.getElementById('notificationInboxButton')?.setAttribute('aria-expanded', 'false');
});
document.getElementById('notificationInboxItems')?.addEventListener('click', async event => {
    const button = event.target.closest('.notification-mark-read');
    if (!button) return;
    button.disabled = true;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/notifications/${Number(button.dataset.id)}/read`, {
            method: 'POST',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo marcar como leída');
        await loadNotificationInbox();
    } catch (error) {
        const result = document.getElementById('notificationInboxResult');
        if (result) result.textContent = error.message;
        button.disabled = false;
    }
});

function resetSessionInterface(message = '') {
    if (notificationRefreshTimer) clearInterval(notificationRefreshTimer);
    notificationRefreshTimer = null;
    if (serviceTimerInterval) clearInterval(serviceTimerInterval);
    serviceTimerInterval = null;
    if (ownerClientsSearchTimer) clearTimeout(ownerClientsSearchTimer);
    ownerClientsSearchTimer = null;
    ownerClientsRequestId += 1;
    ownerClientsSearch = '';
    ownerClientsOffset = 0;
    ownerClientCache.clear();
    localStorage.removeItem('userEmail');
    accessToken = null;
    currentUser = null;

    const dashboard = document.getElementById('dashboardSection');
    if (dashboard) dashboard.style.display = 'none';
    const login = document.getElementById('loginSection');
    if (login) login.style.display = 'flex';
    const userInfo = document.getElementById('userInfo');
    if (userInfo) userInfo.style.display = 'none';
    const notificationButton = document.getElementById('notificationInboxButton');
    if (notificationButton) notificationButton.hidden = true;
    const inbox = document.getElementById('inAppNotificationInbox');
    if (inbox) inbox.hidden = true;
    const clientHistoryDialog = document.getElementById('ownerClientHistoryDialog');
    if (clientHistoryDialog?.open) clientHistoryDialog.close();
    const ownerClientSearch = document.getElementById('ownerClientSearch');
    if (ownerClientSearch) ownerClientSearch.value = '';

    const email = document.getElementById('loginEmail');
    if (email) email.value = '';
    const password = document.getElementById('loginPassword');
    if (password) password.value = '';
    const notice = document.getElementById('sessionExpiredNotice');
    if (notice) {
        notice.textContent = message;
        notice.hidden = !message;
    }
    const passwordDialog = document.getElementById('passwordChangeDialog');
    if (passwordDialog?.open) passwordDialog.close();
}

window.addEventListener('kingflow:auth-expired', () => {
    resetSessionInterface('Tu sesión expiró. Inicia sesión nuevamente para continuar.');
});

function logout() {
    KingFlowAuth.logout();
    resetSessionInterface();

    showToast('👋 Sesión cerrada exitosamente', 'info');
}

function finishService() {
    const inProgressCard = document.querySelector('#appointmentsList .appointment-card.in-progress');
    if (!inProgressCard) {
        showToast('No hay servicio en progreso para finalizar.');
        return;
    }

    const paymentBtn = inProgressCard.querySelector('.appointment-payment');
    if (!paymentBtn) {
        showToast('No se encontró cita para finalizar.');
        return;
    }

    const appointmentId = Number(paymentBtn.dataset.appointmentId);
    if (!Number.isInteger(appointmentId) || appointmentId <= 0) {
        showToast('No se pudo identificar la cita activa.');
        return;
    }

    collectAppointmentPayment(appointmentId);
}

async function updateAppointmentStatus(appointmentId, status) {
    if (!accessToken) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/appointments/${appointmentId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ status })
        });

        const data = await response.json();
        if (!response.ok) {
            showToast(data.detail || 'No se pudo actualizar el estado de la cita');
            return;
        }

        await loadBarberDashboardData();
        await loadCashSummary();
    } catch (error) {
        console.error('Error updating appointment status:', error);
        showToast('Error de conexión actualizando cita');
    }
}

let pendingAppointmentPaymentId = null;

function collectAppointmentPayment(appointmentId) {
    const dialog = document.getElementById('appointmentPaymentDialog');
    const form = document.getElementById('appointmentPaymentForm');
    const result = document.getElementById('appointmentPaymentResult');
    if (!Number.isInteger(Number(appointmentId)) || Number(appointmentId) <= 0 || !dialog || !form) return;
    pendingAppointmentPaymentId = Number(appointmentId);
    form.hidden = false;
    form.reset();
    if (result) result.textContent = '';
    document.getElementById('submitAppointmentPayment').disabled = false;
    document.getElementById('cancelAppointmentPayment').textContent = 'Cancelar';
    dialog.showModal();
    document.getElementById('appointmentPaymentMethod')?.focus();
}

document.getElementById('cancelAppointmentPayment')?.addEventListener('click', () => {
    document.getElementById('appointmentPaymentDialog')?.close();
});

document.getElementById('appointmentPaymentDialog')?.addEventListener('close', () => {
    pendingAppointmentPaymentId = null;
    const form = document.getElementById('appointmentPaymentForm');
    form.hidden = false;
    form.reset();
    document.getElementById('appointmentPaymentResult').textContent = '';
    document.getElementById('submitAppointmentPayment').disabled = false;
    document.getElementById('cancelAppointmentPayment').textContent = 'Cancelar';
});

document.getElementById('appointmentPaymentForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const appointmentId = pendingAppointmentPaymentId;
    const form = document.getElementById('appointmentPaymentForm');
    const method = document.getElementById('appointmentPaymentMethod').value;
    const result = document.getElementById('appointmentPaymentResult');
    const submitButton = document.getElementById('submitAppointmentPayment');
    if (!appointmentId || !['cash', 'card', 'transfer', 'other'].includes(method)) return;
    submitButton.disabled = true;
    result.textContent = 'Registrando el pago…';
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/appointments/${appointmentId}/payment`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ method, tip_cents: 0 })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo registrar el pago. Revisa el estado de la cita antes de reintentar.';
            submitButton.disabled = false;
            return;
        }
        result.textContent = `Pago registrado: ${fmtMoneyFromCents(data.total_cents)} ${data.currency}. El servicio quedó finalizado.`;
        form.hidden = true;
        document.getElementById('cancelAppointmentPayment').textContent = 'Cerrar';
        await Promise.allSettled([loadBarberDashboardData(), loadCashSummary()]);
    } catch (error) {
        console.error('Error recording appointment payment:', error);
        result.textContent = 'No se pudo confirmar la respuesta del servidor. Revisa la cita antes de volver a intentar el cobro.';
        submitButton.disabled = false;
    }
});

let cashBusinessDate = null;
let cashCurrency = 'USD';

async function loadCashSummary() {
    if (!accessToken) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/cash/today`);
        if (!response.ok) return;
        const data = await response.json();
        cashBusinessDate = data.business_date;
        cashCurrency = data.currency || 'USD';
        const format = (cents) => new Intl.NumberFormat('es-DO', { style: 'currency', currency: cashCurrency }).format((Number(cents) || 0) / 100);
        setText('cashRegisterDate', `Fecha comercial: ${cashBusinessDate}`);
        setText('cashTotalToday', format(data.total_cents));
        setText('cashExpectedToday', format(data.expected_cash_cents));
        setText('cashPaymentCount', String(data.payment_count || 0));
        const methods = document.getElementById('cashMethods');
        if (methods) {
            const labels = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', other: 'Otro' };
            methods.textContent = Object.entries(data.by_method || {}).map(([key, value]) => `${labels[key] || key}: ${format(value)}`).join(' · ') || 'Aún no hay cobros registrados hoy.';
        }
        const form = document.getElementById('cashCloseForm');
        if (form) form.style.display = data.closed ? 'none' : 'block';
        if (data.closed && data.close) setText('cashCloseResult', `Caja cerrada. Diferencia: ${format(data.close.difference_cents)}`);
    } catch (error) {
        console.error('Error loading cash summary:', error);
    }
}

document.getElementById('cashCloseForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('cashCloseResult');
    const declared = Number(document.getElementById('cashDeclared').value);
    if (!cashBusinessDate || !Number.isFinite(declared) || declared < 0) {
        result.textContent = 'Indica un importe válido para el efectivo contado.';
        return;
    }
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/cash/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ business_date: cashBusinessDate, declared_cash_cents: Math.round(declared * 100), notes: document.getElementById('cashCloseNotes').value.trim() || null })
        });
        const data = await response.json();
        if (!response.ok) {
            result.textContent = data.detail || 'No se pudo cerrar la caja.';
            return;
        }
        const difference = new Intl.NumberFormat('es-DO', { style: 'currency', currency: data.currency }).format(data.difference_cents / 100);
        result.textContent = `Cierre guardado. Diferencia: ${difference}`;
        await loadCashSummary();
    } catch (error) {
        console.error('Error closing cash register:', error);
        result.textContent = 'Error de conexión al cerrar la caja.';
    }
});

function businessDateFor(timeZone, date = new Date()) {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
}

async function loadFinancialReport() {
    if (currentUser?.role !== 'barbershop_owner' || !barbershopProfile) return;
    const startInput = document.getElementById('financialReportStart');
    const endInput = document.getElementById('financialReportEnd');
    if (!startInput.value || !endInput.value) {
        const today = businessDateFor(barbershopProfile.timezone || 'UTC');
        startInput.value = `${today.slice(0, 7)}-01`;
        endInput.value = today;
    }
    const result = document.getElementById('financialReportResult');
    result.textContent = 'Consultando cobros…';
    try {
        const query = new URLSearchParams({ start_date: startInput.value, end_date: endInput.value });
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/analytics/financial-report?${query}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'No se pudo consultar el reporte.');
        const format = (cents) => new Intl.NumberFormat('es-DO', {
            style: 'currency', currency: data.currency,
        }).format((Number(cents) || 0) / 100);
        document.getElementById('financialReportSummary').innerHTML = [
            ['Cobros recibidos', format(data.gross_cents)],
            ['Servicios', format(data.service_revenue_cents)],
            ['Propinas', format(data.tip_cents)],
            ['Pagos', String(data.payment_count)],
        ].map(([label, value]) => `<div class="stat-card"><div class="stat-value">${escapeHtml(value)}</div><div class="stat-label">${escapeHtml(label)}</div></div>`).join('');

        const sections = [
            ['Por día comercial', data.by_day || []],
            ['Por método de pago', data.by_method || []],
            ['Por barbero', data.by_barber || []],
        ];
        document.getElementById('financialReportBreakdowns').innerHTML = sections.map(([title, rows]) => `
            <h4>${escapeHtml(title)}</h4>
            <table><thead><tr><th>Grupo</th><th>Pagos</th><th>Servicios</th><th>Propinas</th><th>Total</th></tr></thead>
            <tbody>${rows.length ? rows.map((row) => `<tr><td data-label="Grupo">${escapeHtml(row.label)}</td><td data-label="Pagos">${Number(row.payment_count)}</td><td data-label="Servicios">${format(row.service_revenue_cents)}</td><td data-label="Propinas">${format(row.tip_cents)}</td><td data-label="Total">${format(row.gross_cents)}</td></tr>`).join('') : '<tr><td colspan="5" data-label="Informe">Sin cobros en el rango.</td></tr>'}</tbody></table>
        `).join('');
        result.textContent = `${data.payment_count} pagos · ${data.start_date} a ${data.end_date} (${data.timezone})`;
    } catch (error) {
        result.textContent = error.message || 'Error de conexión al consultar el reporte.';
    }
}

document.getElementById('financialReportForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    await loadFinancialReport();
});

const serviceForm = document.getElementById('serviceForm');
document.getElementById('newServiceBtn')?.addEventListener('click', () => {
    if (currentUser?.role !== 'barbershop_owner') return;
    editingServiceId = null;
    serviceForm.reset();
    document.getElementById('serviceFormTitle').textContent = 'Nuevo servicio';
    document.getElementById('serviceFormResult').textContent = '';
    serviceForm.hidden = false;
});
document.getElementById('cancelServiceForm')?.addEventListener('click', () => { serviceForm.hidden = true; });
document.getElementById('serviceSearch')?.addEventListener('input', (event) => {
    const query = event.target.value.trim().toLocaleLowerCase();
    document.querySelectorAll('#servicesList .service-item').forEach((item) => {
        item.hidden = !item.textContent.toLocaleLowerCase().includes(query);
    });
});
serviceForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('serviceFormResult');
    const payload = {
        name: document.getElementById('serviceName').value.trim(),
        description: document.getElementById('serviceDescription').value.trim() || null,
        duration_minutes: Number(document.getElementById('serviceDuration').value),
        price: Math.round(Number(document.getElementById('servicePrice').value) * 100),
        category: document.getElementById('serviceCategory').value.trim()
    };
    try {
        const url = editingServiceId ? `${API_ROOT}/api/v1/services/${editingServiceId}` : `${API_ROOT}/api/v1/services/`;
        const response = await KingFlowAuth.fetch(url, {
            method: editingServiceId ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok) { result.textContent = data.detail || 'No se pudo guardar el servicio.'; return; }
        serviceForm.hidden = true;
        await loadBarberDashboardData();
    } catch (error) {
        console.error('Error saving service:', error);
        result.textContent = 'Error de conexión al guardar el servicio.';
    }
});

function editService(serviceId) {
    if (currentUser?.role !== 'barbershop_owner') return;
    const item = serviceCache.find((service) => service.id === serviceId);
    if (!item) return;
    editingServiceId = item.id;
    document.getElementById('serviceFormTitle').textContent = 'Editar servicio';
    document.getElementById('serviceName').value = item.name || '';
    document.getElementById('serviceDescription').value = item.description || '';
    document.getElementById('serviceDuration').value = item.duration_minutes || 30;
    document.getElementById('servicePrice').value = (Number(item.price_cents) / 100).toFixed(2);
    document.getElementById('serviceCategory').value = item.category || 'haircut';
    document.getElementById('serviceFormResult').textContent = '';
    serviceForm.hidden = false;
}

async function deleteService(serviceId) {
    if (currentUser?.role !== 'barbershop_owner' || !await showConfirmation(
        '¿Desactivar este servicio? No aparecerá en nuevas reservas.',
        { title: 'Desactivar servicio', confirmLabel: 'Desactivar', danger: true },
    )) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/services/${serviceId}`, { method: 'DELETE' });
        if (!response.ok) {
            const data = await response.json();
            showToast(data.detail || 'No se pudo desactivar el servicio.');
            return;
        }
        await loadBarberDashboardData();
    } catch (error) {
        console.error('Error deleting service:', error);
        showToast('Error de conexión al desactivar el servicio.');
    }
}

document.getElementById('loginForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const response = await fetch(`${API_ROOT}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();
        if (!response.ok) {
            showToast(`❌ ${data.detail || 'Credenciales inválidas'}`);
            return;
        }

        accessToken = data.access_token;
        KingFlowAuth.setTokens(data.access_token, data.refresh_token);
        localStorage.setItem('userEmail', data.user.email);

        currentUser = {
            email: data.user.email,
            name: data.user.full_name,
            role: data.user.role,
            feature_flags: data.user.feature_flags || {},
        };
        const newServiceBtn = document.getElementById('newServiceBtn');
        if (newServiceBtn) newServiceBtn.hidden = currentUser.role !== 'barbershop_owner';
        const ownerTabButton = document.getElementById('ownerManagementTabButton');
        if (ownerTabButton) ownerTabButton.hidden = currentUser.role !== 'barbershop_owner';
        const financialReportPanel = document.getElementById('ownerFinancialReport');
        if (financialReportPanel) financialReportPanel.hidden = currentUser.role !== 'barbershop_owner';
        const walkInBarberSelect = document.getElementById('walkInBarberSelect');
        if (walkInBarberSelect) {
            const isOwner = currentUser.role === 'barbershop_owner';
            walkInBarberSelect.hidden = !isOwner;
            walkInBarberSelect.disabled = !isOwner;
        }
        const barberAvailabilityTools = document.getElementById('barberAvailabilityTools');
        if (barberAvailabilityTools) barberAvailabilityTools.hidden = currentUser.role !== 'barber';

        if (currentUser.role === 'super_admin') {
            window.location.href = '/admin.html';
            return;
        }

        const canContinue = await loadBarbershopProfile();
        if (!canContinue) return;

        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('dashboardSection').style.display = 'block';
        document.getElementById('serviceModeTab').style.display = 'block';
        document.getElementById('userInfo').style.display = 'flex';
        document.getElementById('userName').textContent = currentUser.name;
        const notificationButton = document.getElementById('notificationInboxButton');
        if (notificationButton) notificationButton.hidden = false;
        if (notificationButton) {
            await loadNotificationUnreadCount();
            if (notificationRefreshTimer) clearInterval(notificationRefreshTimer);
            notificationRefreshTimer = setInterval(refreshNotificationInbox, 60000);
        }

        await loadShareLink();

        const createSlotsBtn = document.getElementById('createSlotsBtn');
        if (createSlotsBtn) createSlotsBtn.onclick = createBarberSlots;
        const absenceForm = document.getElementById('barberAbsenceForm');
        if (absenceForm) absenceForm.onsubmit = createBarberAbsence;
        const absenceList = document.getElementById('barberAbsenceList');
        if (absenceList) absenceList.onclick = cancelBarberAbsence;
        if (currentUser.role === 'barber') await loadBarberAbsences();

        await loadBarberDashboardData();
        const slotDate = document.getElementById('slotDate');
        if (slotDate && !slotDate.value) {
            slotDate.value = dashboardBusinessDate || businessTodayDate();
        }
        await loadCashSummary();
        await loadOwnerManagement();
        await loadOwnerSubscription();
        await loadFinancialReport();
        await loadBarberCommissionSummary();

        const welcomeMessage = barbershopProfile
            ? `✅ Bienvenido a ${barbershopProfile.name}`
            : '✅ Login exitoso';
        showToast(welcomeMessage, 'info');
    } catch (error) {
        console.error(error);
        showToast('❌ No fue posible conectar con el backend de autenticación');
    }
});

accessToken = sessionStorage.getItem('token');
setupLoginSupportPanel();

if (sessionStorage.getItem('kingflow-password-changed') === '1') {
    sessionStorage.removeItem('kingflow-password-changed');
    const notice = document.getElementById('passwordChangeNotice');
    if (notice) {
        notice.textContent = 'Contraseña actualizada. Inicia sesión con tu nueva contraseña.';
        notice.hidden = false;
    }
}

document.getElementById('logoutButton')?.addEventListener('click', logout);
document.getElementById('finishServiceButton')?.addEventListener('click', finishService);
document.getElementById('testConnectionButton')?.addEventListener('click', testConnection);
document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => showTab(tab.dataset.tab));
});
document.getElementById('appointmentsList')?.addEventListener('click', async (event) => {
    const statusButton = event.target.closest('.appointment-status-action');
    if (statusButton) {
        const appointmentId = Number(statusButton.dataset.appointmentId);
        const nextStatus = statusButton.dataset.status;
        if (!Number.isInteger(appointmentId) || appointmentId <= 0) return;
        if (nextStatus === 'no_show' && !await showConfirmation('¿Marcar esta cita como inasistencia?', {
            title: 'Registrar inasistencia', confirmLabel: 'Marcar inasistencia', danger: true,
        })) return;
        void updateAppointmentStatus(appointmentId, nextStatus);
        return;
    }
    const paymentButton = event.target.closest('.appointment-payment');
    if (paymentButton) void collectAppointmentPayment(Number(paymentButton.dataset.appointmentId));
});
document.getElementById('servicesList')?.addEventListener('click', (event) => {
    const button = event.target.closest('.service-action');
    if (!button) return;
    const serviceId = Number(button.dataset.serviceId);
    if (!Number.isInteger(serviceId) || serviceId <= 0) return;
    if (button.dataset.action === 'edit') editService(serviceId);
    if (button.dataset.action === 'delete') void deleteService(serviceId);
});

console.log('🚀 KingFlow Barber Frontend Ready');
console.log('📍 API Base:', API_ROOT);
