const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = (APP_CONFIG.apiBaseUrl || window.location.origin).replace(/\/$/, '');

let currentUser = null;
let barbershopProfile = null;
let dashboardLayout = null;
let accessToken = null;
let serviceCache = [];
let selectedServiceCategory = null;
let serviceSearchQuery = '';
let editingServiceId = null;
let selectedAppointmentsDate = null;
let selectedAppointmentsView = 'day';
let appointmentsRequestSequence = 0;
let dashboardRequestSequence = 0;
let cashSummaryRequestSequence = 0;
let dashboardBusinessDate = null;
let notificationRefreshTimer = null;
let serviceTimerInterval = null;
let performanceChartResizeObserver = null;
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

function withoutLeadingEmoji(value) {
    return String(value ?? '').replace(/^(?:\p{Extended_Pictographic}\uFE0F?\s*)+/u, '').trim();
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
            alerts.push('El servicio superó su duración estimada.');
        } else if (progressPct >= 80) {
            alerts.push(`⏰ ${Math.ceil(durationSeconds / 60 - elapsedSeconds / 60)} minutos restantes del tiempo estimado`);
        }
        const nextAppointmentAt = nextAppointment?.scheduled_time
            ? new Date(nextAppointment.scheduled_time).getTime()
            : NaN;
        if (Number.isFinite(nextAppointmentAt)) {
            const minutesUntilNext = Math.max(0, Math.ceil((nextAppointmentAt - Date.now()) / 60000));
            if (minutesUntilNext <= 20) alerts.push(`Próxima cita en ${minutesUntilNext} minutos`);
        }
        setText('activeServiceAlert', alerts.join(' · ') || `Servicio en curso · ${progressPct}% del tiempo estimado`);
    };

    renderElapsed();
    serviceTimerInterval = setInterval(renderElapsed, 1000);
}

function setTrend(id, delta, suffix, currency = false) {
    const el = document.getElementById(id);
    if (!el) return;

    if (currency) {
        el.textContent = `${delta >= 0 ? '↑' : '↓'} ${fmtMoneyFromCents(delta)} ${suffix}`;
        return;
    }

    el.textContent = `${delta >= 0 ? '↑' : '↓'} ${delta >= 0 ? '+' : ''}${delta}${suffix}`;
}

function renderNextAppointment(next) {
    const startButton = document.getElementById('startNextAppointmentButton');
    if (!next) {
        setText('nextAppointmentTime', '--:--');
        setText('nextAppointmentEta', 'Sin próxima cita');
        setText('nextAppointmentClient', 'Agenda del día');
        setText('nextAppointmentService', 'No tienes citas próximas');
        setText('nextAppointmentDuration', '-- min estimados');
        if (startButton) startButton.hidden = true;
        return;
    }

    setText('nextAppointmentTime', fmtHour(next.scheduled_time));
    setText('nextAppointmentClient', next.client_name || 'Cliente');
    setText('nextAppointmentService', next.service_type || 'Servicio');
    setText('nextAppointmentDuration', `${next.estimated_duration || 0} min estimados`);
    const minutesUntil = Math.max(0, Math.ceil((new Date(next.scheduled_time).getTime() - Date.now()) / 60000));
    if (startButton) {
        startButton.dataset.appointmentId = String(Number(next.id));
        startButton.hidden = false;
        startButton.disabled = minutesUntil > 15;
        startButton.textContent = minutesUntil > 15 ? 'Disponible 15 min antes' : 'Iniciar cita';
    }
    const etaEl = document.getElementById('nextAppointmentEta');
    if (etaEl) {
        const minutesUntil = Math.max(0, Math.round((new Date(next.scheduled_time) - new Date()) / 60000));
        etaEl.textContent = minutesUntil <= 1 ? 'Ahora' : `En ${minutesUntil} minutos`;
    }
}

function renderWeeklyChart(weeklyCounts) {
    const canvas = document.getElementById('performanceChartCanvas');
    if (!canvas) return;
    const data = Array.isArray(weeklyCounts) ? weeklyCounts : [];
    const summary = document.getElementById('performanceChartSummary');
    if (summary) summary.textContent = data.length
        ? data.map(item => `${item.label}: ${Number(item.count) || 0} citas`).join('. ')
        : 'Aún no hay datos de citas para este periodo.';

    const draw = () => {
        const width = canvas.clientWidth;
        if (!width) return;
        const height = Math.max(208, Math.min(270, Math.round(width * .35)));
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        canvas.style.height = `${height}px`;
        const context = canvas.getContext('2d');
        if (!context) return;
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
        context.clearRect(0, 0, width, height);

        const left = 38, right = 10, top = 15, bottom = 35;
        const plotWidth = width - left - right;
        const plotHeight = height - top - bottom;
        const maximum = Math.max(4, ...data.map(item => Number(item.count) || 0));
        const ink = getComputedStyle(document.documentElement).getPropertyValue('--kf-muted').trim() || '#77746d';
        const grid = '#ebe7e0';
        context.font = '11px Inter, ui-sans-serif, system-ui, sans-serif';
        context.textBaseline = 'middle';
        context.lineWidth = 1;
        for (let tick = 0; tick <= 4; tick += 1) {
            const y = top + plotHeight - plotHeight * tick / 4;
            context.beginPath(); context.moveTo(left, y); context.lineTo(width - right, y);
            context.strokeStyle = grid; context.stroke();
            context.fillStyle = ink; context.textAlign = 'right';
            context.fillText(String(Math.round(maximum * tick / 4)), left - 9, y);
        }

        if (!data.length) {
            context.fillStyle = ink; context.textAlign = 'center';
            context.fillText('Aún no hay actividad para mostrar', left + plotWidth / 2, top + plotHeight / 2);
            return;
        }

        const hasActivity = data.some(item => (Number(item.count) || 0) > 0);
        if (!hasActivity) {
            context.fillStyle = ink; context.textAlign = 'center';
            context.fillText('Sin citas completadas esta semana', left + plotWidth / 2, top + plotHeight / 2);
            const slot = plotWidth / data.length;
            data.forEach((item, index) => {
                context.fillStyle = ink; context.textAlign = 'center';
                context.fillText(String(item.label || '').slice(0, 10), left + slot * index + slot / 2, height - 14);
            });
            return;
        }

        const slot = plotWidth / data.length;
        const barWidth = Math.min(38, slot * .54);
        const brand = getComputedStyle(document.documentElement).getPropertyValue('--brand-primary').trim() || '#b98752';
        const gradient = context.createLinearGradient(0, top, 0, top + plotHeight);
        gradient.addColorStop(0, '#d5b48b');
        gradient.addColorStop(1, brand);
        data.forEach((item, index) => {
            const count = Math.max(0, Number(item.count) || 0);
            const barHeight = count ? Math.max(4, plotHeight * count / maximum) : 3;
            const x = left + slot * index + (slot - barWidth) / 2;
            const y = top + plotHeight - barHeight;
            context.beginPath();
            context.roundRect(x, y, barWidth, barHeight, [6, 6, 1, 1]);
            context.fillStyle = count ? gradient : '#e8e3da';
            context.fill();
            context.textAlign = 'center';
            if (count) {
                context.fillStyle = '#5a4635';
                context.fillText(String(count), x + barWidth / 2, Math.max(top + 6, y - 10));
            }
            context.fillStyle = ink;
            context.fillText(String(item.label || '').slice(0, 10), left + slot * index + slot / 2, height - 14);
        });
    };
    draw();
    if (typeof ResizeObserver === 'function') {
        if (!performanceChartResizeObserver) performanceChartResizeObserver = new ResizeObserver(draw);
        performanceChartResizeObserver.disconnect();
        performanceChartResizeObserver.observe(canvas);
    } else {
        window.addEventListener('resize', draw, { once: true });
    }
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
                <div class="achievement-icon ${unlocked ? '' : 'locked-icon'}" aria-hidden="true">${unlocked
                    ? '<svg viewBox="0 0 24 24"><path d="M7 4h10v4a5 5 0 0 1-10 0V4ZM7 6H4v2a4 4 0 0 0 4 4M17 6h3v2a4 4 0 0 1-4 4M12 13v4m-4 3h8m-7-3h6"/></svg>'
                    : '<svg viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></svg>'}</div>
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
        return `${escapeHtml(currency)} ${value.toFixed(2)}`;
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
        pending: 'Pendiente',
        confirmed: 'Confirmada',
        in_progress: 'En servicio',
        completed: 'Completada',
        cancelled: 'Cancelada',
        no_show: 'No asistió'
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
        logoElement.textContent = profile.name;
    }
    const logoMark = document.querySelector('.logo-mark');
    if (logoMark && profile?.name) logoMark.textContent = profile.name.trim().charAt(0).toUpperCase() || 'K';

    const brandColorPattern = /^#[0-9a-f]{6}$/i;
    const readableBrandText = hex => {
        const rgb = hex.match(/[\da-f]{2}/gi).map(value => parseInt(value, 16));
        const luminance = values => values.map(value => { const c = value / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; })
            .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
        const ratio = value => 1.05 / (value + .05);
        if (ratio(luminance(rgb)) >= 4.5) return hex;
        for (let factor = .95; factor > 0; factor -= .01) {
            const darker = rgb.map(value => Math.round(value * factor));
            if (ratio(luminance(darker)) >= 4.5) return `#${darker.map(value => value.toString(16).padStart(2, '0')).join('')}`;
        }
        return '#363831';
    };
    const brandForegroundText = hex => {
        const rgb = hex.match(/[\da-f]{2}/gi).map(value => parseInt(value, 16));
        const luminance = rgb.map(value => { const c = value / 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; })
            .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
        return luminance > .1791 ? '#161713' : '#ffffff';
    };
    const automaticBranding = currentUser?.role === 'barbershop_owner' || currentUser?.feature_flags?.branding_auto === true;
    if (automaticBranding && brandColorPattern.test(profile?.primary_color || '')) {
        document.documentElement.style.setProperty('--brand-primary', profile.primary_color);
        document.documentElement.style.setProperty('--brand-text-color', readableBrandText(profile.primary_color));
        document.documentElement.style.setProperty('--brand-on-primary', brandForegroundText(profile.primary_color));
    } else {
        document.documentElement.style.setProperty('--brand-primary', '#b98752');
        document.documentElement.style.setProperty('--brand-text-color', readableBrandText('#b98752'));
        document.documentElement.style.setProperty('--brand-on-primary', brandForegroundText('#b98752'));
    }
    if (automaticBranding && brandColorPattern.test(profile?.secondary_color || '')) {
        document.documentElement.style.setProperty('--brand-secondary', profile.secondary_color);
    } else {
        document.documentElement.style.setProperty('--brand-secondary', '#5a4635');
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
        if (!response.ok) {
            showToast('No fue posible validar la configuración de tu barbería. Intenta iniciar sesión nuevamente.', 'error');
            return false;
        }

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
        showToast('No fue posible validar la configuración de tu barbería. Revisa tu conexión e inicia sesión nuevamente.', 'error');
        return false;
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
                    <span class="insight-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.2 2"/></svg></span>
                    <div class="insight-content">
                        <h4>Insight personalizado</h4>
                    <p>${escapeHtml(insight)}</p>
                    </div>
                </div>
            `).join('');
        }

        const quickActionsTitle = document.querySelector('.quick-actions h3');
        if (quickActionsTitle && dashboardLayout.layout_type) {
            quickActionsTitle.textContent = 'Accesos rápidos';
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
                    <strong>${message.type === 'celebration' ? 'Buen avance' : 'Sugerencia para tu negocio'}</strong>
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
                <div class="contextual-greeting-card">
                    <span class="contextual-greeting-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 3 14 9l6 3-6 2-2 7-2-7-6-2 6-3 2-6Z"/></svg></span>
                    <span class="contextual-greeting-text">${escapeHtml(withoutLeadingEmoji(greeting.message))}</span>
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
                    showToast('Link copiado', 'info');
                } catch (_) {
                    showToast('No se pudo copiar automáticamente');
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

        if (result) result.textContent = `Turnos creados: ${data.created_slots}`;
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
                ${renderAppointmentPreferences(appointment)}
                ${currentUser?.role === 'barber' && Number(appointment.client_id) > 0 ? `
                    <details class="barber-style-passport" data-appointment-id="${Number(appointment.id)}" data-client-id="${Number(appointment.client_id)}">
                        <summary>Style Passport compartido</summary>
                        <p class="barber-style-passport-status" role="status" aria-live="polite">Solo aparecerá la información que el cliente autorizó compartir.</p>
                        <div class="barber-style-passport-items"></div>
                        <button class="btn-secondary barber-style-passport-load" type="button">Consultar registros compartidos</button>
                    </details>` : ''}
                <div class="appointment-meta">
                    <span>${Number(appointment.estimated_duration) || 0} min</span>
                    <span>${fmtMoneyFromCents(appointment.service_price || 0)}</span>
                </div>
                <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
                    ${appointment.status === 'pending' ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="confirmed">Confirmar</button>` : ''}
                    ${['pending', 'confirmed'].includes(appointment.status) ? `<button class="btn-start appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="in_progress">Iniciar servicio</button>` : ''}
                    ${appointment.status === 'in_progress' ? `<button class="btn-secondary appointment-payment" type="button" data-appointment-id="${Number(appointment.id)}">Cobrar y finalizar</button>` : ''}
                    ${['pending', 'confirmed'].includes(appointment.status) ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="cancelled">Cancelar</button>` : ''}
                    ${canMarkAppointmentNoShow(appointment) ? `<button class="btn-secondary appointment-status-action" type="button" data-appointment-id="${Number(appointment.id)}" data-status="no_show">Marcar inasistencia</button>` : ''}
                </div>
            </div>
        </div>
    `).join('');
}

function renderAppointmentPreferences(appointment) {
    const answers = appointment.booking_answers && typeof appointment.booking_answers === 'object'
        ? Object.entries(appointment.booking_answers).filter(([question, answer]) =>
            typeof question === 'string' && typeof answer === 'string' && question.trim() && answer.trim())
        : [];
    const legacyNotes = typeof appointment.client_notes === 'string' ? appointment.client_notes.trim() : '';
    if (!answers.length && !legacyNotes) return '';
    const answerMarkup = answers.map(([question, answer]) =>
        `<div><dt>${escapeHtml(question)}</dt><dd>${escapeHtml(answer)}</dd></div>`).join('');
    const legacyMarkup = legacyNotes
        ? `<p>${escapeHtml(legacyNotes).replace(/\n/g, '<br>')}</p>`
        : '';
    return `<section class="appointment-notes"><strong>Preferencias del cliente</strong>${legacyMarkup}` +
        (answerMarkup ? `<dl class="appointment-question-answers">${answerMarkup}</dl>` : '') + '</section>';
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
    const requestSequence = ++appointmentsRequestSequence;
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
        if (requestSequence !== appointmentsRequestSequence) return;
        if (selectedAppointmentsView === 'day') renderAppointmentDay(data.business_date, data.appointments);
        else renderAppointmentCalendar(data);
    } catch (error) {
        if (requestSequence !== appointmentsRequestSequence) return;
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

function filterServices(services, category, query) {
    const normalizedQuery = String(query || '').trim().toLocaleLowerCase();
    return services.filter((service) => {
        const serviceCategory = String(service.category || '').trim();
        if (category && serviceCategory !== category) return false;
        if (!normalizedQuery) return true;
        return [service.name, service.description, serviceCategory]
            .some((value) => String(value || '').toLocaleLowerCase().includes(normalizedQuery));
    });
}

function renderServiceCategoryFilters(services) {
    const container = document.getElementById('serviceCategories');
    if (!container) return;

    const categories = [...new Set(services
        .map((service) => String(service.category || '').trim())
        .filter(Boolean))]
        .sort((left, right) => left.localeCompare(right));
    if (selectedServiceCategory && !categories.includes(selectedServiceCategory)) {
        selectedServiceCategory = null;
    }

    const options = [
        { label: 'Todos', category: null },
        ...categories.map((category) => ({ label: category, category })),
    ];
    container.replaceChildren(...options.map((option) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `category-btn${selectedServiceCategory === option.category ? ' active' : ''}`;
        button.dataset.category = option.category || '';
        button.dataset.allCategories = String(option.category === null);
        button.setAttribute('aria-pressed', String(selectedServiceCategory === option.category));
        button.textContent = option.label;
        return button;
    }));
}

function renderServiceCatalog(services) {
    const list = document.getElementById('servicesList');
    if (!list) return;

    renderServiceCategoryFilters(services);
    if (!services.length) {
        list.innerHTML = '<div class="service-item"><div class="service-info"><h4>Sin servicios activos</h4><p>Crea servicios desde tu configuración para verlos aquí.</p></div></div>';
        return;
    }

    const visibleServices = filterServices(services, selectedServiceCategory, serviceSearchQuery);
    if (!visibleServices.length) {
        list.innerHTML = '<div class="service-item"><div class="service-info"><h4>No hay servicios coincidentes</h4><p>Prueba otra categoría o búsqueda.</p></div></div>';
        return;
    }

    list.innerHTML = visibleServices.map((service) => {
        const imageUrl = trustedBusinessImage(service.image_url);
        const visual = imageUrl
            ? `<img class="service-catalog-photo" src="${escapeHtml(imageUrl)}" alt="Foto de ${escapeHtml(service.name)}" loading="lazy">`
            : '<div class="service-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="m8 8 12 12M8 16 19 5m-6 5 2 2"/></svg></div>';
        return `
        <div class="service-item ${service.category === 'combo' ? 'featured' : ''}">
            ${visual}
            <div class="service-info">
                <h4>${escapeHtml(service.name)}</h4>
                <p>${escapeHtml(service.description || 'Servicio personalizado de la barbería')}</p>
                <div class="service-meta">
                    <span class="tag">${escapeHtml(service.category || 'General')}</span>
                    <span>${service.duration_minutes || 0} min</span>
                </div>
            </div>
            <div class="service-price">${fmtMoneyFromCents(service.price_cents || 0)}</div>
            ${currentUser?.role === 'barbershop_owner' ? `<button class="btn-icon service-action" type="button" aria-label="Editar servicio" data-action="edit" data-service-id="${Number(service.id)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 16-.8 4.8L8 20l11.9-11.9a2.5 2.5 0 0 0-3.5-3.5L4 16Z"/><path d="m14.5 6.5 3.5 3.5"/></svg></button><button class="btn-icon service-action" type="button" aria-label="Desactivar servicio" data-action="delete" data-service-id="${Number(service.id)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16m-13 0 .7 13h8.6L17 7M9 7V4h6v3m-4 4v5m2-5v5"/></svg></button>` : ''}
        </div>
    `;
    }).join('');
}

function handleServiceCategoryClick(event) {
    const button = event.target.closest('button.category-btn');
    if (!button || !event.currentTarget.contains(button)) return;
    selectedServiceCategory = button.dataset.allCategories === 'true' ? null : button.dataset.category;
    renderServiceCatalog(serviceCache);
}

async function loadBarberDashboardData() {
    if (!accessToken) return;
    const requestSequence = ++dashboardRequestSequence;

    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/dashboard`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });

        if (!response.ok) return;

        const data = await response.json();
        if (requestSequence !== dashboardRequestSequence) return;
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

        setText('statsCompletedTrend', `${completedDelta >= 0 ? '↑' : '↓'} ${completedDelta >= 0 ? '+' : ''}${completedDelta} vs ayer`);
        setText('statsRevenueTrend', `${revenueDeltaCents >= 0 ? '↑' : '↓'} ${fmtMoneyFromCents(revenueDeltaCents)} vs ayer`);
        setText('statsEfficiencyTrend', `${efficiencyDelta >= 0 ? '↑' : '↓'} ${efficiencyDelta >= 0 ? '+' : ''}${efficiencyDelta}% vs ayer`);
        const businessDate = data.business_date || businessTodayDate();
        dashboardBusinessDate = businessDate;
        if (!selectedAppointmentsDate) selectedAppointmentsDate = businessDate;

        const active = data.active_appointment ||
            (Array.isArray(data.appointments) ? data.appointments : []).find((a) => a.status === 'in_progress') || null;
        const finishServiceButton = document.getElementById('finishServiceButton');
        const activeServiceStatus = document.getElementById('activeServiceStatus');
        if (finishServiceButton) finishServiceButton.disabled = !active;
        const startNextButton = document.getElementById('startNextAppointmentButton');
        if (startNextButton && active) startNextButton.hidden = true;
        if (active) {
            if (activeServiceStatus) {
                activeServiceStatus.textContent = 'En servicio';
                activeServiceStatus.classList.add('in-progress');
            }
            setText('activeServiceClient', active.client_name || 'Cliente');
            setText('activeServiceType', active.service_type || 'Servicio');
            setText('activeServiceEstimated', `${active.estimated_duration || 0} minutos`);
            updateActiveServiceTimer(active.actual_start_time, active.estimated_duration, data.next_appointment);
        } else {
            if (activeServiceStatus) {
                activeServiceStatus.textContent = 'Sin cita activa';
                activeServiceStatus.classList.remove('in-progress');
            }
            updateActiveServiceTimer(null);
            setText('activeServiceClient', 'Sin servicio activo');
            setText('activeServiceType', 'Esperando próximas citas');
            setText('activeServiceEstimated', '-- minutos');
            setText('activeServiceProgress', '0%');
            const progressBar = document.getElementById('activeServiceProgressBar');
            if (progressBar) progressBar.style.width = '0%';
            setText('activeServiceAlert', 'Sin servicio activo en este momento');
        }

        renderNextAppointment(data.next_appointment);
        if (active) {
            const startNextButton = document.getElementById('startNextAppointmentButton');
            if (startNextButton) startNextButton.hidden = true;
        }

        if (selectedAppointmentsView === 'day' && selectedAppointmentsDate === businessDate) {
            renderAppointmentDay(businessDate, data.appointments);
        } else {
            await loadAppointmentsForDate(selectedAppointmentsDate);
        }
        if (requestSequence !== dashboardRequestSequence) return;

        const services = Array.isArray(data.services) ? data.services : [];
        serviceCache = services;
        populateWalkInServices(services);
        renderServiceCatalog(services);

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

async function loadBarberStylePassport(clientId, appointmentId, container) {
    const status = container?.querySelector('.barber-style-passport-status');
    const list = container?.querySelector('.barber-style-passport-items');
    if (!status || !list || !Number.isInteger(clientId) || clientId <= 0
        || !Number.isInteger(appointmentId) || appointmentId <= 0) return;
    const sessionToken = accessToken;
    if (!sessionToken) return;
    status.textContent = 'Consultando registros autorizados…';
    list.replaceChildren();
    try {
        const data = await ownerFetch(`/owner/clients/${clientId}/style-passport`);
        if (accessToken !== sessionToken) return;
        const entries = Array.isArray(data.items) ? data.items : [];
        if (!entries.length) {
            status.textContent = 'El cliente no ha compartido registros de estilo con esta barbería.';
            return;
        }
        entries.forEach((entry) => {
            const card = document.createElement('article');
            card.className = 'barber-style-passport-entry';
            const heading = document.createElement('h5');
            heading.textContent = entry.haircut_type || entry.service || 'Corte guardado';
            const details = document.createElement('p');
            let serviceDate = 'Fecha no disponible';
            if (entry.service_date) {
                const rawDate = String(entry.service_date);
                const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(rawDate) ? rawDate : `${rawDate}Z`);
                if (Number.isFinite(date.getTime())) {
                    serviceDate = new Intl.DateTimeFormat('es-DO', {
                        dateStyle: 'medium', timeStyle: 'short',
                        timeZone: barbershopProfile?.timezone || 'UTC',
                    }).format(date);
                }
            }
            details.textContent = `${entry.service || 'Servicio'} · ${serviceDate}`;
            card.append(heading, details);
            [
                ['Degradado', entry.fade_style], ['Largo superior', entry.top_length],
                ['Lados', entry.sides_length], ['Barba', entry.beard_style],
                ['Productos', entry.products_used], ['Preferencias', entry.preferences],
                ['Notas técnicas', entry.barber_notes], ['Recomendaciones', entry.recommendations],
            ].filter(([, value]) => typeof value === 'string' && value.trim()).forEach(([label, value]) => {
                const detail = document.createElement('p');
                detail.textContent = `${label}: ${value}`;
                card.append(detail);
            });
            const photos = Array.isArray(entry.photos) ? entry.photos : [];
            if (photos.length) {
                const photoList = document.createElement('div');
                photoList.className = 'barber-style-passport-photos';
                photos.forEach((photo) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'btn-secondary';
                    button.textContent = photo.kind === 'reference'
                        ? 'Ver referencia privada' : 'Ver resultado privado';
                    button.addEventListener('click', async () => {
                        button.disabled = true;
                        try {
                            const response = await KingFlowAuth.fetch(
                                `${API_ROOT}/api/v1/owner/clients/${clientId}/style-passport/` +
                                `${Number(entry.id)}/photos/${Number(photo.id)}`,
                                { headers: { Authorization: `Bearer ${accessToken}` } },
                            );
                            const image = document.createElement('img');
                            if (!response.ok) throw new Error('No se pudo abrir la foto compartida.');
                            const imageBlob = await response.blob();
                            if (accessToken !== sessionToken) return;
                            image.alt = photo.kind === 'reference'
                                ? 'Foto de referencia compartida por el cliente'
                                : 'Foto del resultado compartida por el cliente';
                            const objectUrl = URL.createObjectURL(imageBlob);
                            image.src = objectUrl;
                            image.addEventListener('load', () => URL.revokeObjectURL(objectUrl), { once: true });
                            image.addEventListener('error', () => URL.revokeObjectURL(objectUrl), { once: true });
                            photoList.append(image);
                        } catch (error) {
                            status.textContent = error.message || 'No se pudo abrir la fotografía.';
                        } finally {
                            button.disabled = false;
                        }
                    });
                    photoList.append(button);
                });
                card.append(photoList);
            }
            const notesForm = document.createElement('form');
            notesForm.className = 'barber-style-passport-notes';
            const notesLabel = document.createElement('label');
            notesLabel.textContent = 'Nota técnica';
            const notes = document.createElement('textarea');
            notes.maxLength = 2000;
            notes.value = entry.barber_notes || '';
            notesLabel.append(notes);
            const recommendationsLabel = document.createElement('label');
            recommendationsLabel.textContent = 'Recomendación para la próxima visita';
            const recommendations = document.createElement('textarea');
            recommendations.maxLength = 2000;
            recommendations.value = entry.recommendations || '';
            recommendationsLabel.append(recommendations);
            const save = document.createElement('button');
            save.type = 'submit';
            save.className = 'btn-secondary';
            save.textContent = 'Guardar notas técnicas';
            notesForm.append(notesLabel, recommendationsLabel, save);
            notesForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                save.disabled = true;
                try {
                    await ownerFetch(
                        `/owner/clients/${clientId}/style-passport/${Number(entry.id)}`,
                        {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                barber_notes: notes.value.trim() || null,
                                recommendations: recommendations.value.trim() || null,
                            }),
                        },
                    );
                    status.textContent = 'Las notas del equipo se guardaron.';
                } catch (error) {
                    status.textContent = error.message || 'No se pudieron guardar las notas.';
                } finally {
                    save.disabled = false;
                }
            });
            card.append(notesForm);
            list.append(card);
        });
        status.textContent = `${entries.length} registro(s) compartido(s)`;
    } catch (error) {
        status.textContent = error.message || 'No se pudieron consultar los registros compartidos.';
    }
}

function trustedBusinessImage(value) {
    if (typeof value !== 'string' || !value.trim()) return '';
    try {
        const url = new URL(value, API_ROOT);
        const apiOrigin = new URL(API_ROOT, window.location.origin).origin;
        return url.origin === apiOrigin && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
            ? url.href : '';
    } catch (_) {
        return '';
    }
}

function renderBusinessGallery(images) {
    const container = document.getElementById('businessGalleryPreview');
    if (!container) return;
    container.replaceChildren();
    (Array.isArray(images) ? images : []).forEach((imageUrl) => {
        const src = trustedBusinessImage(imageUrl);
        if (!src) return;
        const item = document.createElement('figure');
        item.className = 'business-gallery-item';
        const image = document.createElement('img');
        image.src = src;
        image.alt = 'Foto de la galería de cortes';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn-secondary';
        remove.textContent = 'Quitar';
        remove.dataset.galleryImage = imageUrl;
        item.append(image, remove);
        container.append(item);
    });
    const imageSelect = document.getElementById('serviceImageUrl');
    if (imageSelect) {
        const selected = imageSelect.value;
        imageSelect.replaceChildren(new Option('Sin foto', ''));
        (Array.isArray(images) ? images : []).forEach((imageUrl, index) => {
            const option = new Option(`Foto de galería ${index + 1}`, imageUrl);
            imageSelect.add(option);
        });
        if ([...imageSelect.options].some((option) => option.value === selected)) imageSelect.value = selected;
        renderServiceImagePreview();
    }
}

function renderServiceImagePreview() {
    const preview = document.getElementById('serviceImagePreview');
    const imageUrl = document.getElementById('serviceImageUrl')?.value;
    if (!preview) return;
    preview.replaceChildren();
    const src = trustedBusinessImage(imageUrl);
    if (!src) {
        preview.textContent = 'Sin foto seleccionada';
        return;
    }
    const image = document.createElement('img');
    image.src = src;
    image.alt = 'Vista previa de la foto del servicio';
    preview.append(image);
}

document.getElementById('serviceImageUrl')?.addEventListener('change', renderServiceImagePreview);
document.getElementById('serviceImageFile')?.addEventListener('change', async (event) => {
    const input = event.currentTarget;
    const result = document.getElementById('serviceImageUploadResult');
    const file = input.files?.[0];
    if (!file || currentUser?.role !== 'barbershop_owner') return;
    const gallery = barbershopProfile?.gallery_images || [];
    if (gallery.length >= 8) {
        result.textContent = 'La galería está llena. Quita una foto antes de añadir otra.';
        input.value = '';
        return;
    }
    result.textContent = 'Subiendo foto del servicio…';
    const body = new FormData();
    body.append('file', file);
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/upload-gallery-image`, { method: 'POST', body });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo subir la foto del servicio.');
        barbershopProfile.gallery_images = data.gallery_images || gallery;
        renderBusinessGallery(barbershopProfile.gallery_images);
        const added = barbershopProfile.gallery_images.find(url => !gallery.includes(url));
        if (added) document.getElementById('serviceImageUrl').value = added;
        renderServiceImagePreview();
        result.textContent = 'Foto subida y seleccionada para este servicio.';
    } catch (error) {
        result.textContent = error.message || 'No se pudo subir la foto del servicio.';
    } finally {
        input.value = '';
    }
});

function renderBusinessLogo(logoUrl) {
    const preview = document.getElementById('businessLogoPreview');
    if (!preview) return;
    preview.replaceChildren();
    const src = trustedBusinessImage(logoUrl);
    if (src) {
        const image = document.createElement('img');
        image.src = src;
        image.alt = 'Logo actual de la barbería';
        preview.append(image);
    } else {
        const placeholder = document.createElement('span');
        placeholder.className = 'logo-placeholder';
        placeholder.textContent = barbershopProfile?.name?.trim()?.charAt(0)?.toUpperCase() || 'K';
        preview.append(placeholder);
    }
}

function renderBusinessCover(coverUrl) {
    const preview = document.getElementById('businessCoverPreview');
    if (!preview) return;
    preview.replaceChildren();
    const src = trustedBusinessImage(coverUrl);
    const image = document.createElement('img');
    image.src = src || '/images/barbershop-hero.png';
    image.alt = src ? 'Foto de portada actual' : 'Portada predeterminada';
    preview.append(image);
    if (src) {
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'btn-secondary';
        remove.textContent = 'Restaurar portada predeterminada';
        remove.id = 'removeBusinessCoverBtn';
        preview.append(remove);
    }
}

document.getElementById('businessCoverFile')?.addEventListener('change', async (event) => {
    const input = event.currentTarget;
    const result = document.getElementById('businessCoverResult');
    const file = input.files?.[0];
    if (!file || currentUser?.role !== 'barbershop_owner') return;
    result.textContent = 'Subiendo portada…';
    const body = new FormData();
    body.append('file', file);
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/upload-cover`, { method: 'POST', body });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo actualizar la portada.');
        barbershopProfile.cover_image_url = data.cover_image_url;
        renderBusinessCover(data.cover_image_url);
        result.textContent = 'Portada actualizada en tu página pública.';
    } catch (error) {
        result.textContent = error.message || 'No se pudo actualizar la portada.';
    } finally {
        input.value = '';
    }
});

document.getElementById('businessCoverPreview')?.addEventListener('click', async (event) => {
    if (event.target.id !== 'removeBusinessCoverBtn' || currentUser?.role !== 'barbershop_owner') return;
    const button = event.target;
    const result = document.getElementById('businessCoverResult');
    button.disabled = true;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/cover-image`, { method: 'DELETE' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo restaurar la portada.');
        barbershopProfile.cover_image_url = null;
        renderBusinessCover(null);
        result.textContent = 'Portada predeterminada restaurada.';
    } catch (error) {
        button.disabled = false;
        result.textContent = error.message || 'No se pudo restaurar la portada.';
    }
});

document.getElementById('businessLogoFile')?.addEventListener('change', async (event) => {
    const input = event.currentTarget;
    const result = document.getElementById('businessLogoResult');
    const file = input.files?.[0];
    if (!file || currentUser?.role !== 'barbershop_owner') return;
    result.textContent = 'Subiendo logo…';
    const body = new FormData();
    body.append('file', file);
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/upload-logo`, {
            method: 'POST', body,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo actualizar el logo.');
        barbershopProfile.logo_url = data.logo_url;
        renderBusinessLogo(data.logo_url);
        result.textContent = 'Logo actualizado en tu página pública.';
    } catch (error) {
        result.textContent = error.message || 'No se pudo actualizar el logo.';
    } finally {
        input.value = '';
    }
});

document.getElementById('businessGalleryFiles')?.addEventListener('change', async (event) => {
    const input = event.currentTarget;
    const result = document.getElementById('businessGalleryResult');
    const files = [...(input.files || [])];
    if (!files.length || currentUser?.role !== 'barbershop_owner') return;
    result.textContent = 'Subiendo fotos…';
    try {
        let gallery = [...(barbershopProfile?.gallery_images || [])];
        for (const file of files) {
            if (gallery.length >= 8) throw new Error('La galería admite hasta 8 fotos.');
            const body = new FormData();
            body.append('file', file);
            const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/upload-gallery-image`, {
                method: 'POST', body,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'No se pudo subir una foto.');
            gallery = data.gallery_images || gallery;
        }
        barbershopProfile.gallery_images = gallery;
        renderBusinessGallery(gallery);
        result.textContent = 'Fotos publicadas en tu página de reservas.';
    } catch (error) {
        result.textContent = error.message || 'No se pudo subir la galería.';
    } finally {
        input.value = '';
    }
});

document.getElementById('businessGalleryPreview')?.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-gallery-image]');
    if (!button || currentUser?.role !== 'barbershop_owner') return;
    const result = document.getElementById('businessGalleryResult');
    button.disabled = true;
    try {
        const query = new URLSearchParams({ image_url: button.dataset.galleryImage });
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/onboarding/gallery-image?${query}`, { method: 'DELETE' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || 'No se pudo quitar la foto.');
        barbershopProfile.gallery_images = data.gallery_images || [];
        renderBusinessGallery(barbershopProfile.gallery_images);
        result.textContent = 'Foto retirada de tu página pública.';
    } catch (error) {
        button.disabled = false;
        result.textContent = error.message || 'No se pudo quitar la foto.';
    }
});

async function loadOwnerManagement() {
    if (currentUser?.role !== 'barbershop_owner') return;
    const settingsForm = document.getElementById('businessSettingsForm');
    if (settingsForm && barbershopProfile) {
        document.getElementById('businessSettingsName').value = barbershopProfile.name || '';
        document.getElementById('businessSettingsDescription').value = barbershopProfile.description || '';
        document.getElementById('businessBookingQuestions').value = (barbershopProfile.booking_questions || []).join('\n');
        document.getElementById('businessSettingsOpening').value = barbershopProfile.opening_time?.slice(0, 5) || '';
        document.getElementById('businessSettingsClosing').value = barbershopProfile.closing_time?.slice(0, 5) || '';
        document.getElementById('businessCancellationWindow').value = String(barbershopProfile.cancellation_window_hours ?? 0);
        document.getElementById('businessStylePassportRetention').value = barbershopProfile.style_passport_retention_days == null ? '' : String(barbershopProfile.style_passport_retention_days);
        document.getElementById('businessSettingsTimezone').value = barbershopProfile.timezone || '';
        document.getElementById('businessSettingsPrimary').value = /^#[0-9a-f]{6}$/i.test(barbershopProfile.primary_color || '') ? barbershopProfile.primary_color : '#b98752';
        document.getElementById('businessSettingsSecondary').value = /^#[0-9a-f]{6}$/i.test(barbershopProfile.secondary_color || '') ? barbershopProfile.secondary_color : '#5a4635';
        document.getElementById('businessSettingsTheme').value = barbershopProfile.public_theme || 'light';
        renderBusinessGallery(barbershopProfile.gallery_images || []);
        renderBusinessLogo(barbershopProfile.logo_url);
        renderBusinessCover(barbershopProfile.cover_image_url);
        settingsForm.onsubmit = saveBusinessSettings;
        if (!settingsForm.dataset.brandPreviewReady) {
            setupBrandPreview();
            settingsForm.dataset.brandPreviewReady = 'true';
        }
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
        await loadOwnerWaitlist();
        await loadOwnerInventory();
        await loadDemandForecast();
    } catch (error) {
        barberBody.textContent = '';
        const clientsResult = document.getElementById('ownerClientsResult');
        if (clientsResult) clientsResult.textContent = error.message || 'No se pudo cargar la administración.';
    }
}

async function loadOwnerWaitlist() {
    const body = document.getElementById('ownerWaitlistBody');
    const result = document.getElementById('ownerWaitlistResult');
    if (!body || !result || currentUser?.role !== 'barbershop_owner') return;
    result.textContent = 'Cargando solicitudes…';
    body.replaceChildren();
    const status = document.getElementById('ownerWaitlistStatus')?.value || '';
    const query = new URLSearchParams({ limit: '100' });
    if (status) query.set('status', status);
    try {
        const data = await ownerFetch(`/owner/waitlist?${query.toString()}`);
        const items = data.items || [];
        body.innerHTML = items.map(entry => {
            const phone = String(entry.phone || '').replace(/\D/g, '');
            const waUrl = phone.length >= 6 && phone.length <= 20
                ? `https://wa.me/${phone}?text=${encodeURIComponent(`Hola ${entry.client_name}, recibimos tu solicitud para ${entry.service_name}. ¿Aún deseas que te contactemos cuando haya disponibilidad?`)}`
                : '';
            const dateRange = [entry.preferred_date_start, entry.preferred_date_end].filter(Boolean);
            const dateLabel = dateRange.length === 2 ? `${dateRange[0]} – ${dateRange[1]}` : dateRange[0] || 'Flexible';
            const statusLabel = { new: 'Pendiente', contacted: 'Contactado', closed: 'Cerrado' }[entry.status] || 'Desconocido';
            const nextStatus = entry.status === 'new' ? 'contacted' : entry.status === 'contacted' ? 'closed' : 'new';
            const actionLabel = nextStatus === 'contacted' ? 'Marcar contactado' : nextStatus === 'closed' ? 'Cerrar solicitud' : 'Reabrir';
            return `<tr><td data-label="Cliente">${escapeHtml(entry.client_name)}<br><a href="tel:${phone}">${escapeHtml(entry.phone)}</a></td>
                <td data-label="Servicio">${escapeHtml(entry.service_name)}</td><td data-label="Barbero">${escapeHtml(entry.barber_name || 'Cualquiera')}</td>
                <td data-label="Fechas preferidas">${escapeHtml(dateLabel)}</td><td data-label="Detalle">${escapeHtml(entry.notes || '—')}</td>
                <td data-label="Recibida">${escapeHtml(new Date(entry.created_at).toLocaleString('es-DO', { timeZone: barbershopProfile?.timezone || 'UTC' }))}</td>
                <td data-label="Estado">${escapeHtml(statusLabel)}</td><td data-label="Acciones">${waUrl ? `<a class="btn-secondary" href="${waUrl}" target="_blank" rel="noopener noreferrer">WhatsApp</a>` : ''}
                <button class="btn-secondary owner-waitlist-status" data-id="${Number(entry.id)}" data-next-status="${nextStatus}" type="button">${actionLabel}</button></td></tr>`;
        }).join('');
        result.textContent = items.length ? `${items.length} solicitud(es) · ${Number(data.total)} en este filtro` : 'No hay solicitudes para mostrar.';
    } catch (error) {
        body.replaceChildren();
        result.textContent = error.message || 'No se pudo cargar la lista de espera.';
    }
}

document.getElementById('refreshOwnerWaitlist')?.addEventListener('click', loadOwnerWaitlist);
document.getElementById('ownerWaitlistStatus')?.addEventListener('change', loadOwnerWaitlist);
document.getElementById('ownerWaitlistBody')?.addEventListener('click', async (event) => {
    const button = event.target.closest('.owner-waitlist-status');
    if (!button) return;
    const id = Number(button.dataset.id);
    const status = button.dataset.nextStatus;
    if (!Number.isInteger(id) || id <= 0 || !['new', 'contacted', 'closed'].includes(status)) return;
    if (status === 'closed' && !await showConfirmation('¿Cerrar esta solicitud de lista de espera?', {
        title: 'Cerrar solicitud', confirmLabel: 'Cerrar', danger: true,
    })) return;
    button.disabled = true;
    try {
        await ownerFetch(`/owner/waitlist/${id}/status`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
        });
        await loadOwnerWaitlist();
    } catch (error) {
        button.disabled = false;
        document.getElementById('ownerWaitlistResult').textContent = error.message || 'No se pudo actualizar la solicitud.';
    }
});

let ownerInventoryProducts = [];
let retailCart = [];

function moneyInputToCents(value) {
    const match = String(value).trim().match(/^(\d{1,9})(?:\.(\d{1,2}))?$/);
    if (!match) throw new Error('Escribe un importe válido con hasta dos decimales.');
    return Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0'));
}

async function loadOwnerInventory() {
    const productsBody = document.getElementById('ownerInventoryProductsBody');
    const movementsBody = document.getElementById('ownerInventoryMovementsBody');
    const movementProduct = document.getElementById('inventoryMovementProduct');
    const summary = document.getElementById('ownerInventorySummary');
    if (!productsBody || !movementsBody || !movementProduct || !summary || currentUser?.role !== 'barbershop_owner') return;
    productsBody.replaceChildren();
    movementsBody.replaceChildren();
    try {
        const [products, movements] = await Promise.all([
            ownerFetch('/owner/inventory/products?include_inactive=true&limit=100'),
            ownerFetch('/owner/inventory/movements?limit=100'),
        ]);
        ownerInventoryProducts = products.items || [];
        const saleProduct = document.getElementById('retailProduct');
        if (saleProduct) {
            const selectedSaleProduct = saleProduct.value;
            saleProduct.replaceChildren(new Option('Selecciona un producto', ''));
            ownerInventoryProducts.filter(product => product.is_active && Number(product.unit_price_cents) > 0 && Number(product.stock_quantity) > 0)
                .forEach(product => saleProduct.add(new Option(`${product.name} · ${fmtMoneyFromCents(product.unit_price_cents)} · ${product.stock_quantity} disponibles`, String(product.id))));
            if ([...saleProduct.options].some(option => option.value === selectedSaleProduct)) saleProduct.value = selectedSaleProduct;
        }
        renderRetailCart();
        productsBody.innerHTML = ownerInventoryProducts.map(product => `<tr>
            <td data-label="Producto">${escapeHtml(product.name)}<br><small>${escapeHtml(product.category)} · ${escapeHtml(product.unit)}</small></td>
            <td data-label="Código">${escapeHtml(product.barcode || '—')}</td>
            <td data-label="Costo">${fmtMoneyFromCents(product.unit_cost_cents)}</td>
            <td data-label="Precio">${fmtMoneyFromCents(product.unit_price_cents)}</td>
            <td data-label="Existencias">${Number(product.stock_quantity)} ${escapeHtml(product.unit)}${product.low_stock ? ' · Reponer' : ''}</td>
            <td data-label="Estado">${product.is_active ? 'Activo' : 'Inactivo'}</td></tr>`).join('');
        const selected = movementProduct.value;
        movementProduct.replaceChildren(new Option('Selecciona un producto', ''));
        ownerInventoryProducts.filter(product => product.is_active).forEach(product => {
            movementProduct.add(new Option(`${product.name} · ${product.stock_quantity} ${product.unit}`, String(product.id)));
        });
        if ([...movementProduct.options].some(option => option.value === selected)) movementProduct.value = selected;
        const productNames = new Map(ownerInventoryProducts.map(product => [Number(product.id), product.name]));
        const labels = { receipt: 'Recepción', return: 'Devolución', consumption: 'Consumo', adjustment: 'Ajuste', sale: 'Venta' };
        movementsBody.innerHTML = (movements.items || []).map(item => `<tr>
            <td data-label="Fecha">${escapeHtml(new Date(item.created_at).toLocaleString('es-DO', { timeZone: barbershopProfile?.timezone || 'UTC' }))}</td>
            <td data-label="Producto">${escapeHtml(productNames.get(Number(item.product_id)) || `#${Number(item.product_id)}`)}</td>
            <td data-label="Movimiento">${escapeHtml(labels[item.reason] || item.reason)}</td>
            <td data-label="Variación">${Number(item.quantity_delta) > 0 ? '+' : ''}${Number(item.quantity_delta)}</td>
            <td data-label="Costo por unidad">${fmtMoneyFromCents(item.unit_cost_cents)}</td>
            <td data-label="Nota">${escapeHtml(item.note || '—')}</td></tr>`).join('');
        summary.textContent = `${Number(products.total)} producto(s) · ${Number(movements.total)} movimiento(s) recientes`;
    } catch (error) {
        summary.textContent = error.message || 'No se pudo cargar el inventario.';
    }
}

function renderRetailCart() {
    const cart = document.getElementById('retailCart');
    const submit = document.querySelector('#retailSaleForm [type="submit"]');
    if (!cart) return;
    const rows = retailCart.map(item => {
        const product = ownerInventoryProducts.find(candidate => Number(candidate.id) === item.product_id);
        if (!product) return '';
        const unitPrice = Number(product.unit_price_cents) || 0;
        return `<tr><td data-label="Producto">${escapeHtml(product.name)}</td><td data-label="Cantidad">${item.quantity}</td><td data-label="Precio">${fmtMoneyFromCents(unitPrice)}</td><td data-label="Subtotal">${fmtMoneyFromCents(unitPrice * item.quantity)}</td><td data-label="Acción"><button class="btn-secondary retail-cart-remove" type="button" data-product-id="${item.product_id}" aria-label="Quitar ${escapeHtml(product.name)}">Quitar</button></td></tr>`;
    }).filter(Boolean);
    const total = retailCart.reduce((sum, item) => {
        const product = ownerInventoryProducts.find(candidate => Number(candidate.id) === item.product_id);
        return sum + (Number(product?.unit_price_cents) || 0) * item.quantity;
    }, 0);
    cart.innerHTML = rows.length
        ? `<table><thead><tr><th>Producto</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th><th>Acción</th></tr></thead><tbody>${rows.join('')}</tbody><tfoot><tr><th colspan="3">Total</th><th>${fmtMoneyFromCents(total)}</th><td></td></tr></tfoot></table>`
        : '<p>El carrito está vacío. Añade productos para preparar la venta.</p>';
    if (submit) submit.disabled = !rows.length || total <= 0 || total > 2_000_000_000;
}

document.getElementById('retailAddCartItem')?.addEventListener('click', () => {
    const productId = Number(document.getElementById('retailProduct').value);
    const quantity = Number(document.getElementById('retailQuantity').value);
    const product = ownerInventoryProducts.find(item => Number(item.id) === productId && item.is_active);
    const result = document.getElementById('retailSaleResult');
    if (!product || !Number.isInteger(quantity) || quantity < 1 || quantity > 100_000) {
        result.textContent = 'Selecciona un producto y una cantidad válida.';
        return;
    }
    const cartLine = retailCart.find(item => item.product_id === productId);
    const nextQuantity = (cartLine?.quantity || 0) + quantity;
    if (nextQuantity > Number(product.stock_quantity)) {
        result.textContent = `Solo hay ${Number(product.stock_quantity)} unidades disponibles de ${product.name}.`;
        return;
    }
    if (!cartLine && retailCart.length >= 50) {
        result.textContent = 'El carrito admite hasta 50 productos distintos por venta.';
        return;
    }
    if (cartLine) cartLine.quantity = nextQuantity;
    else retailCart.push({ product_id: productId, quantity });
    result.textContent = '';
    document.getElementById('retailQuantity').value = '1';
    renderRetailCart();
});

document.getElementById('retailCart')?.addEventListener('click', event => {
    const remove = event.target.closest('.retail-cart-remove');
    if (!remove) return;
    const productId = Number(remove.dataset.productId);
    retailCart = retailCart.filter(item => item.product_id !== productId);
    renderRetailCart();
});

async function loadOwnerRetailSales() {
    const root = document.getElementById('retailRecentSales');
    if (!root || currentUser?.role !== 'barbershop_owner') return;
    try {
        const data = await ownerFetch('/owner/inventory/sales?limit=10');
        const methodLabels = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', other: 'Otro' };
        const rows = data.items || [];
        root.innerHTML = rows.length
            ? `<table><thead><tr><th>Fecha</th><th>Venta</th><th>Artículos</th><th>Cobro</th><th>Total</th></tr></thead><tbody>${rows.map(sale => `<tr><td data-label="Fecha">${escapeHtml(new Date(sale.sold_at).toLocaleString('es-DO', { timeZone: barbershopProfile?.timezone || 'UTC' }))}</td><td data-label="Venta">#${Number(sale.id)}</td><td data-label="Artículos">${(sale.items || []).map(item => `${escapeHtml(item.product_name)} × ${Number(item.quantity)}`).join(', ')}</td><td data-label="Cobro">${escapeHtml(methodLabels[sale.payment_method] || sale.payment_method)}</td><td data-label="Total">${fmtMoneyFromCents(sale.total_cents)}</td></tr>`).join('')}</tbody></table>`
            : '<p>Aún no hay ventas de productos.</p>';
    } catch (error) {
        root.textContent = error.message || 'No se pudo cargar el historial de ventas.';
    }
}

document.getElementById('refreshOwnerInventory')?.addEventListener('click', loadOwnerInventory);
document.getElementById('ownerInventoryProductForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const result = document.getElementById('ownerInventoryProductResult');
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    result.textContent = 'Guardando producto…';
    try {
        const priceInCents = (id) => moneyInputToCents(document.getElementById(id).value);
        await ownerFetch('/owner/inventory/products', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: document.getElementById('inventoryProductName').value.trim(),
                category: document.getElementById('inventoryProductCategory').value.trim(),
                barcode: document.getElementById('inventoryProductBarcode').value.trim() || null,
                unit: document.getElementById('inventoryProductUnit').value.trim(),
                unit_cost_cents: priceInCents('inventoryProductCost'),
                unit_price_cents: priceInCents('inventoryProductPrice'),
                stock_minimum: Number(document.getElementById('inventoryProductMinimum').value),
            }),
        });
        form.reset();
        document.getElementById('inventoryProductCategory').value = 'General';
        document.getElementById('inventoryProductUnit').value = 'unidad';
        result.textContent = 'Producto creado. Registra una recepción para cargar sus existencias.';
        await loadOwnerInventory();
    } catch (error) {
        result.textContent = error.message || 'No se pudo crear el producto.';
    } finally {
        button.disabled = false;
    }
});

document.getElementById('retailSaleForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const result = document.getElementById('retailSaleResult');
    const button = form.querySelector('[type="submit"]');
    const payload = {
        method: document.getElementById('retailPaymentMethod').value,
        items: retailCart.map(item => ({ ...item })),
    };
    if (!payload.items.length || payload.items.length > 50 || payload.items.some(item => !Number.isInteger(item.product_id) || item.product_id <= 0 || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 100_000)) {
        result.textContent = 'Añade al menos un producto con una cantidad válida.';
        return;
    }
    const signature = JSON.stringify(payload);
    if (form.dataset.requestSignature !== signature) {
        form.dataset.requestSignature = signature;
        form.dataset.requestKey = crypto.randomUUID();
    }
    payload.idempotency_key = form.dataset.requestKey;
    button.disabled = true;
    result.textContent = 'Registrando venta y actualizando existencias…';
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/owner/inventory/sales`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'No se pudo registrar la venta.');
        const amount = new Intl.NumberFormat('es-DO', { style: 'currency', currency: data.currency || cashCurrency }).format(data.total_cents / 100);
        result.textContent = `Venta #${data.id} registrada por ${amount}. Se descontaron las existencias.`;
        retailCart = [];
        form.reset();
        delete form.dataset.requestSignature;
        delete form.dataset.requestKey;
        document.getElementById('retailQuantity').value = '1';
        renderRetailCart();
        await loadCashSummary();
    } catch (error) {
        result.textContent = error.message || 'No se pudo registrar la venta.';
    } finally {
        button.disabled = false;
    }
});

document.getElementById('ownerInventoryMovementForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const result = document.getElementById('ownerInventoryMovementResult');
    const button = form.querySelector('[type="submit"]');
    const productId = Number(document.getElementById('inventoryMovementProduct').value);
    const reason = document.getElementById('inventoryMovementReason').value;
    const rawQuantity = document.getElementById('inventoryMovementQuantity').value;
    const quantity = Number(rawQuantity);
    if (!Number.isInteger(productId) || productId <= 0 || !Number.isInteger(quantity) || quantity === 0) {
        result.textContent = 'Selecciona producto y una cantidad entera distinta de cero.';
        return;
    }
    if ((reason === 'receipt' || reason === 'return') && quantity < 0 || reason === 'consumption' && quantity > 0) {
        result.textContent = 'La cantidad debe corresponder al tipo de movimiento seleccionado.';
        return;
    }
    let unitCostCents = null;
    try {
        const rawCost = document.getElementById('inventoryMovementCost').value.trim();
        if (rawCost) unitCostCents = moneyInputToCents(rawCost);
    } catch (error) {
        result.textContent = error.message;
        return;
    }
    const payload = {
        quantity_delta: quantity,
        reason,
        unit_cost_cents: unitCostCents,
        note: document.getElementById('inventoryMovementNote').value.trim() || null,
    };
    const signature = JSON.stringify({ productId, ...payload });
    if (form.dataset.requestSignature !== signature) {
        form.dataset.requestSignature = signature;
        form.dataset.requestKey = crypto.randomUUID();
    }
    payload.idempotency_key = form.dataset.requestKey;
    button.disabled = true;
    result.textContent = 'Registrando movimiento…';
    try {
        await ownerFetch(`/owner/inventory/products/${productId}/movements`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        form.reset();
        delete form.dataset.requestSignature;
        delete form.dataset.requestKey;
        document.getElementById('inventoryMovementReason').value = 'receipt';
        result.textContent = 'Movimiento registrado en el historial de inventario.';
        await loadOwnerInventory();
    } catch (error) {
        result.textContent = error.message || 'No se pudo registrar el movimiento.';
    } finally {
        button.disabled = false;
    }
});

function setupBrandPreview() {
    const primary = document.getElementById('businessSettingsPrimary');
    const secondary = document.getElementById('businessSettingsSecondary');
    const theme = document.getElementById('businessSettingsTheme');
    const preview = document.getElementById('brandPreview');
    if (!primary || !secondary || !theme || !preview) return;
    const name = document.getElementById('businessSettingsName');
    const description = document.getElementById('businessSettingsDescription');
    const presets = [...document.querySelectorAll('.brand-presets button')];
    const update = () => {
        preview.dataset.theme = theme.value;
        preview.style.setProperty('--preview-primary', primary.value);
        preview.style.setProperty('--preview-secondary', secondary.value);
        preview.style.setProperty('--preview-soft', `${secondary.value}12`);
        document.getElementById('brandPreviewName').textContent = name?.value.trim() || 'Tu barbería';
        document.getElementById('brandPreviewMark').textContent = (name?.value.trim() || 'K').charAt(0).toUpperCase();
        document.getElementById('brandPreviewDescription').textContent = description?.value.trim()
            || 'La presentación de tu barbería aparecerá aquí.';
        const trustedAsset = value => {
            if (!value) return null;
            try {
                const url = new URL(value, API_ROOT);
                const apiOrigin = new URL(API_ROOT, window.location.origin).origin;
                return new Set([window.location.origin, apiOrigin]).has(url.origin)
                    && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
                    ? url.href : null;
            } catch (_) { return null; }
        };
        const logo = document.getElementById('brandPreviewLogo');
        const logoUrl = trustedAsset(barbershopProfile?.logo_url);
        logo.hidden = !logoUrl;
        if (logoUrl) logo.src = logoUrl;
        else logo.removeAttribute('src');
        document.getElementById('brandPreviewMark').hidden = Boolean(logoUrl);
        const cover = document.getElementById('brandPreviewCover');
        const coverUrl = trustedAsset(barbershopProfile?.cover_image_url);
        cover.hidden = !coverUrl;
        if (coverUrl) cover.src = coverUrl;
        else cover.removeAttribute('src');
        const featuredService = serviceCache.find(service => service.is_active !== false);
        document.getElementById('brandPreviewService').textContent = featuredService?.name || 'Tus servicios';
        document.getElementById('brandPreviewServiceMeta').textContent = featuredService
            ? `${fmtMoneyFromCents(Number(featuredService.price_cents ?? featuredService.price ?? 0))} · ${Number(featuredService.duration_minutes) || 0} min`
            : 'Los precios y duración se mostrarán desde tu catálogo.';
        const rgb = primary.value.match(/[\da-f]{2}/gi)?.map(v => parseInt(v, 16)) || [0, 0, 0];
        const luminance = rgb.map(v => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
        const darkText = luminance > 0.1791;
        const contrast = darkText ? (luminance + 0.05) / 0.05 : 1.05 / (luminance + 0.05);
        preview.style.setProperty('--preview-button-text', darkText ? '#161713' : '#ffffff');
        const contrastNote = document.getElementById('brandContrastNote');
        contrastNote.textContent = `Contraste del botón: ${contrast.toFixed(1)}:1 · ${contrast >= 4.5 ? 'cumple WCAG AA para texto normal' : 'bajo para texto normal; cambia el color principal'} · tema ${theme.value === 'light' ? 'claro' : 'oscuro'}`;
        contrastNote.dataset.level = contrast >= 4.5 ? 'good' : 'low';
        presets.forEach(button => button.setAttribute('aria-pressed', String(
            button.dataset.primary.toLowerCase() === primary.value.toLowerCase()
            && button.dataset.secondary.toLowerCase() === secondary.value.toLowerCase(),
        )));
    };
    [primary, secondary, theme, name, description].filter(Boolean).forEach(input => {
        input.addEventListener('input', update);
        input.addEventListener('change', update);
    });
    presets.forEach(button => button.addEventListener('click', () => {
        primary.value = button.dataset.primary;
        secondary.value = button.dataset.secondary;
        update();
    }));
    update();
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
        await loadOwnerStylePassport(requestId);
    } catch (error) {
        if (requestId !== ownerClientHistoryRequestId) return;
        list.textContent = '';
        result.textContent = error.message || 'No se pudo cargar el historial.';
    }
}

async function loadOwnerStylePassport(requestId = ownerClientHistoryRequestId) {
    const list = document.getElementById('ownerStylePassportItems');
    const result = document.getElementById('ownerStylePassportResult');
    if (!list || !result || !ownerClientHistoryClientId) return;
    list.replaceChildren();
    result.textContent = 'Consultando los registros que el cliente compartió…';
    try {
        const data = await ownerFetch(
            `/owner/clients/${Number(ownerClientHistoryClientId)}/style-passport`,
        );
        if (requestId !== ownerClientHistoryRequestId) return;
        const entries = data.items || [];
        if (!entries.length) {
            result.textContent = 'El cliente no ha compartido registros de estilo con esta barbería.';
            return;
        }
        entries.forEach((entry) => {
            const card = document.createElement('article');
            card.className = 'owner-style-passport-card';
            const title = document.createElement('h4');
            title.textContent = entry.haircut_type || entry.service || 'Corte guardado';
            const meta = document.createElement('p');
            meta.textContent = `${entry.service} · ${entry.barber} · ${entry.service_date || ''}`;
            card.append(title, meta);
            [
                ['Fade', entry.fade_style], ['Largo superior', entry.top_length],
                ['Lados', entry.sides_length], ['Barba', entry.beard_style],
                ['Productos', entry.products_used], ['Preferencias', entry.preferences],
                ['Notas del barbero', entry.barber_notes], ['Recomendaciones', entry.recommendations],
            ].filter(([, value]) => value).forEach(([label, value]) => {
                const detail = document.createElement('p');
                detail.textContent = `${label}: ${value}`;
                card.append(detail);
            });
            if ((entry.photos || []).length) {
                const photos = document.createElement('div');
                photos.className = 'owner-style-passport-photos';
                entry.photos.forEach((photo) => {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.textContent = photo.kind === 'reference'
                        ? 'Ver referencia privada' : 'Ver resultado privado';
                    button.addEventListener('click', async () => {
                        button.disabled = true;
                        try {
                            const response = await KingFlowAuth.fetch(
                                `${API_ROOT}/api/v1/owner/clients/${Number(ownerClientHistoryClientId)}` +
                                `/style-passport/${Number(entry.id)}/photos/${Number(photo.id)}`,
                            );
                            if (!response.ok) throw new Error('No se pudo abrir la foto compartida.');
                            const image = document.createElement('img');
                            image.alt = photo.kind === 'reference'
                                ? 'Foto de referencia compartida por el cliente'
                                : 'Foto del resultado compartida por el cliente';
                            image.src = URL.createObjectURL(await response.blob());
                            image.addEventListener('load', () => URL.revokeObjectURL(image.src), { once: true });
                            photos.append(image);
                        } catch (error) {
                            result.textContent = error.message;
                        } finally {
                            button.disabled = false;
                        }
                    });
                    photos.append(button);
                });
                card.append(photos);
            }
            const form = document.createElement('form');
            const notesLabel = document.createElement('label');
            notesLabel.textContent = 'Nota profesional';
            const notes = document.createElement('textarea');
            notes.maxLength = 2000;
            notes.value = entry.barber_notes || '';
            notesLabel.append(notes);
            const recommendationsLabel = document.createElement('label');
            recommendationsLabel.textContent = 'Recomendación para la próxima visita';
            const recommendations = document.createElement('textarea');
            recommendations.maxLength = 2000;
            recommendations.value = entry.recommendations || '';
            recommendationsLabel.append(recommendations);
            const save = document.createElement('button');
            save.type = 'submit';
            save.textContent = 'Guardar nota del equipo';
            form.append(notesLabel, recommendationsLabel, save);
            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                save.disabled = true;
                try {
                    await ownerFetch(
                        `/owner/clients/${Number(ownerClientHistoryClientId)}/style-passport/${Number(entry.id)}`,
                        {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                barber_notes: notes.value.trim() || null,
                                recommendations: recommendations.value.trim() || null,
                            }),
                        },
                    );
                    result.textContent = 'La nota profesional se guardó.';
                    await loadOwnerStylePassport(requestId);
                } catch (error) {
                    result.textContent = error.message || 'No se pudo guardar la nota.';
                    save.disabled = false;
                }
            });
            card.append(form);
            list.append(card);
        });
        result.textContent = `${entries.length} registro(s) compartido(s)`;
    } catch (error) {
        if (requestId !== ownerClientHistoryRequestId) return;
        result.textContent = error.message || 'No se pudo cargar el Style Passport compartido.';
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
        const renewalButton = document.getElementById('ownerRenewalRequestBtn');
        if (renewalButton) renewalButton.hidden = data.status === 'active' && Number(data.days_remaining) > 7;
        const renewalResult = document.getElementById('ownerRenewalRequestResult');
        if (renewalResult) renewalResult.textContent = '';
    } catch (error) {
        summary.textContent = error.message || 'No se pudo cargar el estado del plan.';
    }
}

document.getElementById('refreshOwnerSubscription')?.addEventListener('click', loadOwnerSubscription);
document.getElementById('ownerRenewalRequestBtn')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const result = document.getElementById('ownerRenewalRequestResult');
    if (currentUser?.role !== 'barbershop_owner' || !result) return;
    button.disabled = true;
    result.textContent = 'Enviando solicitud…';
    try {
        const data = await ownerFetch('/billing/renewal-request', { method: 'POST' });
        result.textContent = data.created
            ? `Solicitud #${Number(data.ticket_id)} guardada en la bandeja de soporte. No procesa pagos ni reactiva la cuenta.`
            : `Ya hay una solicitud abierta (#${Number(data.ticket_id)}). La bandeja de soporte conserva la solicitud; no procesa pagos ni reactiva la cuenta.`;
    } catch (error) {
        result.textContent = error.message || 'No se pudo guardar la solicitud de renovación.';
    } finally {
        button.disabled = false;
    }
});

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
        description: document.getElementById('businessSettingsDescription').value.trim() || null,
        opening_time: document.getElementById('businessSettingsOpening').value,
        closing_time: document.getElementById('businessSettingsClosing').value,
        cancellation_window_hours: Number(document.getElementById('businessCancellationWindow').value),
        style_passport_retention_days: document.getElementById('businessStylePassportRetention').value === '' ? null : Number(document.getElementById('businessStylePassportRetention').value),
        timezone: document.getElementById('businessSettingsTimezone').value.trim(),
        primary_color: document.getElementById('businessSettingsPrimary').value,
        secondary_color: document.getElementById('businessSettingsSecondary').value,
        public_theme: document.getElementById('businessSettingsTheme').value,
        booking_questions: document.getElementById('businessBookingQuestions').value
            .split(/\r?\n/).map(question => question.trim()).filter(Boolean),
    };
    const previousRetention = barbershopProfile?.style_passport_retention_days ?? null;
    if (payload.style_passport_retention_days !== previousRetention && payload.style_passport_retention_days !== null && !await showConfirmation(
        `La política de ${payload.style_passport_retention_days} días también se aplicará a los registros existentes. Los que ya superen ese plazo se eliminarán en el próximo ciclo del worker, incluidas sus fotos. Esta acción no se puede deshacer. ¿Continuar?`,
        { title: 'Confirmar retención de Style Passport', confirmLabel: 'Aplicar política' }
    )) return;
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

document.getElementById('businessSettingsPrimary')?.addEventListener('input', (event) => {
    if (/^#[0-9a-f]{6}$/i.test(event.currentTarget.value)) {
        document.documentElement.style.setProperty('--brand-primary', event.currentTarget.value);
    }
});
document.getElementById('businessSettingsSecondary')?.addEventListener('input', (event) => {
    if (/^#[0-9a-f]{6}$/i.test(event.currentTarget.value)) {
        document.documentElement.style.setProperty('--brand-secondary', event.currentTarget.value);
    }
});

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
            ? `Solicitud #${Number(data.ticket_id)} recibida; se envió un aviso al equipo.`
            : `Solicitud #${Number(data.ticket_id)} recibida y guardada. El aviso por correo no está disponible ahora.`;
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
            message.textContent = `Conexión correcta · API: ${data.status} · MySQL: ${data.database}`;
            resultDiv.append(message);
        } else {
            resultDiv.textContent = response.status === 503
                ? 'API disponible, pero MySQL no responde.'
                : `El backend respondió con estado HTTP ${response.status}.`;
        }
    } catch (error) {
        resultDiv.textContent = `No se puede conectar al backend ${API_ROOT}. Verifica que esté corriendo.`;
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
    document.getElementById('appointmentsList')?.replaceChildren?.();
    document.getElementById('appointmentsCalendarGrid')?.replaceChildren?.();
    const login = document.getElementById('loginSection');
    if (login) login.style.display = 'grid';
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

    showToast('Sesión cerrada exitosamente', 'info');
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
    const requestSequence = ++cashSummaryRequestSequence;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/cash/today`);
        if (!response.ok) return;
        const data = await response.json();
        if (requestSequence !== cashSummaryRequestSequence) return;
        cashBusinessDate = data.business_date;
        cashCurrency = data.currency || 'USD';
        const format = (cents) => new Intl.NumberFormat('es-DO', { style: 'currency', currency: cashCurrency }).format((Number(cents) || 0) / 100);
        setText('cashRegisterDate', `Fecha comercial: ${cashBusinessDate}`);
        setText('cashTotalToday', format(data.total_cents));
        setText('cashExpectedToday', format(data.expected_cash_cents));
        setText('cashPaymentCount', String(data.payment_count || 0));
        const pos = document.getElementById('retailPointOfSale');
        if (pos) pos.hidden = currentUser?.role !== 'barbershop_owner' || data.closed;
        if (currentUser?.role === 'barbershop_owner') {
            await loadOwnerInventory();
            await loadOwnerRetailSales();
            await loadOwnerExpenses();
        }
        const methods = document.getElementById('cashMethods');
        if (methods) {
            const labels = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', other: 'Otro' };
            methods.textContent = Object.entries(data.by_method || {}).map(([key, value]) => `${labels[key] || key}: ${format(value)}`).join(' · ') || 'Aún no hay cobros registrados hoy.';
        }
        setText('cashExpenseSummary', data.expense_count
            ? `${data.expense_count} gasto(s) registrado(s): ${format(data.expenses_total_cents)} · ${format(data.cash_expense_cents)} descontados del movimiento neto. El cierre suma el fondo inicial.`
            : 'El movimiento neto excluye el fondo inicial; indícalo al cerrar la caja.');
        const form = document.getElementById('cashCloseForm');
        if (form) form.style.display = data.closed ? 'none' : 'block';
        if (data.closed && data.close) setText('cashCloseResult', `Caja cerrada. Fondo inicial: ${format(data.close.opening_cash_cents)} · efectivo esperado: ${format(data.close.expected_cash_cents)} · diferencia: ${format(data.close.difference_cents)}`);
    } catch (error) {
        console.error('Error loading cash summary:', error);
    }
}

document.getElementById('cashCloseForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('cashCloseResult');
    const declared = Number(document.getElementById('cashDeclared').value);
    const opening = Number(document.getElementById('cashOpening').value);
    if (!cashBusinessDate || !Number.isFinite(declared) || declared < 0 || !Number.isFinite(opening) || opening < 0) {
        result.textContent = 'Indica importes válidos para el fondo inicial y el efectivo contado.';
        return;
    }
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/barber/cash/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ business_date: cashBusinessDate, opening_cash_cents: Math.round(opening * 100), declared_cash_cents: Math.round(declared * 100), notes: document.getElementById('cashCloseNotes').value.trim() || null })
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

let ownerExpensesRequestSequence = 0;

async function loadOwnerExpenses() {
    if (currentUser?.role !== 'barbershop_owner') return;
    const body = document.getElementById('ownerExpensesBody');
    if (!body) return;
    const requestSequence = ++ownerExpensesRequestSequence;
    const start = document.getElementById('financialReportStart')?.value;
    const end = document.getElementById('financialReportEnd')?.value;
    const params = new URLSearchParams({ limit: '50' });
    if (start && end) {
        params.set('start_date', start);
        params.set('end_date', end);
    }
    try {
        const data = await ownerFetch(`/owner/expenses?${params}`);
        if (requestSequence !== ownerExpensesRequestSequence) return;
        const labels = {
            rent: 'Alquiler', utilities: 'Servicios', payroll: 'Nómina', commission: 'Comisiones',
            supplies: 'Insumos', maintenance: 'Mantenimiento', marketing: 'Publicidad',
            administrative: 'Administración', internet: 'Internet', water: 'Agua',
            electricity: 'Electricidad', other: 'Otros',
        };
        const methods = { cash: 'Efectivo', card: 'Tarjeta', transfer: 'Transferencia', other: 'Otro' };
        const timeZone = barbershopProfile?.timezone || 'UTC';
        body.innerHTML = (data.items || []).length ? data.items.map((expense) => {
            const dateLabel = new Intl.DateTimeFormat('es-DO', {
                dateStyle: 'medium', timeStyle: 'short', timeZone,
            }).format(new Date(expense.spent_at));
            return `<tr><td data-label="Fecha">${escapeHtml(dateLabel)}</td><td data-label="Categoría">${escapeHtml(labels[expense.category] || expense.category)}</td><td data-label="Descripción">${escapeHtml(expense.description)}</td><td data-label="Método">${escapeHtml(methods[expense.payment_method] || expense.payment_method)}</td><td data-label="Importe">${escapeHtml(fmtMoneyFromCents(expense.amount_cents, expense.currency))}</td></tr>`;
        }).join('') : '<tr><td colspan="5" data-label="Gastos">No hay gastos en este periodo.</td></tr>';
    } catch (error) {
        if (requestSequence !== ownerExpensesRequestSequence) return;
        body.innerHTML = '<tr><td colspan="5" data-label="Gastos">No se pudieron cargar los gastos.</td></tr>';
    }
}

document.getElementById('ownerExpenseForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const result = document.getElementById('ownerExpenseResult');
    const submit = form.querySelector('[type="submit"]');
    const payload = {
        category: document.getElementById('ownerExpenseCategory').value,
        description: document.getElementById('ownerExpenseDescription').value.trim(),
        amount_cents: Math.round(Number(document.getElementById('ownerExpenseAmount').value) * 100),
        payment_method: document.getElementById('ownerExpenseMethod').value,
    };
    if (!Number.isSafeInteger(payload.amount_cents) || payload.amount_cents <= 0) {
        result.textContent = 'Indica un importe mayor que cero.';
        return;
    }
    const signature = JSON.stringify(payload);
    if (form.dataset.requestSignature !== signature || !form.dataset.requestKey) {
        form.dataset.requestKey = crypto.randomUUID();
        form.dataset.requestSignature = signature;
    }
    submit.disabled = true;
    result.textContent = 'Registrando gasto…';
    try {
        const response = await ownerFetch('/owner/expenses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...payload, idempotency_key: form.dataset.requestKey }),
        });
        result.textContent = `Gasto de ${fmtMoneyFromCents(response.amount_cents, response.currency)} registrado.`;
        form.reset();
        delete form.dataset.requestKey;
        delete form.dataset.requestSignature;
        await Promise.all([loadOwnerExpenses(), loadCashSummary(), loadFinancialReport()]);
    } catch (error) {
        result.textContent = error.message || 'No se pudo registrar el gasto. Puedes reintentar sin duplicarlo.';
    } finally {
        submit.disabled = false;
    }
});

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
            ['Gastos registrados', format(data.expense_total_cents)],
            ['Cobros menos gastos registrados', format(data.balance_after_recorded_expenses_cents)],
            ['Servicios', format(data.service_revenue_cents)],
            ['Productos', format(data.retail_revenue_cents)],
            ['Ventas de productos', String(data.retail_sale_count)],
            ['Propinas', format(data.tip_cents)],
            ['Transacciones', String(data.payment_count)],
            ['Pagos de servicios', String(data.service_payment_count)],
        ].map(([label, value]) => `<div class="stat-card"><div class="stat-value">${escapeHtml(value)}</div><div class="stat-label">${escapeHtml(label)}</div></div>`).join('');

        const sections = [
            ['Por día comercial', data.by_day || []],
            ['Por método de pago', data.by_method || []],
            ['Por barbero', data.by_barber || []],
        ];
        document.getElementById('financialReportBreakdowns').innerHTML = sections.map(([title, rows]) => `
            <h4>${escapeHtml(title)}</h4>
            <table><thead><tr><th>Grupo</th><th>Transacciones</th><th>Servicios</th><th>Productos</th><th>Propinas</th><th>Gastos</th><th>Saldo registrado</th></tr></thead>
            <tbody>${rows.length ? rows.map((row) => `<tr><td data-label="Grupo">${escapeHtml(row.label)}</td><td data-label="Transacciones">${Number(row.payment_count)}</td><td data-label="Servicios">${format(row.service_revenue_cents)}</td><td data-label="Productos">${format(row.retail_revenue_cents)}</td><td data-label="Propinas">${format(row.tip_cents)}</td><td data-label="Gastos">${format(row.expense_cents)}</td><td data-label="Saldo registrado">${format(row.net_after_recorded_expenses_cents)}</td></tr>`).join('') : '<tr><td colspan="7" data-label="Informe">Sin cobros ni gastos en el rango.</td></tr>'}</tbody></table>
        `).join('') + `
            <h4>Gastos por categoría</h4>
            <table><thead><tr><th>Categoría</th><th>Movimientos</th><th>Importe</th></tr></thead>
            <tbody>${(data.expenses_by_category || []).length ? data.expenses_by_category.map((row) => `<tr><td data-label="Categoría">${escapeHtml(row.label)}</td><td data-label="Movimientos">${Number(row.expense_count)}</td><td data-label="Importe">${format(row.amount_cents)}</td></tr>`).join('') : '<tr><td colspan="3" data-label="Gastos">Sin gastos en el rango.</td></tr>'}</tbody></table>`;
        result.textContent = `${data.payment_count} transacciones · ${data.expense_count} gastos · ${data.start_date} a ${data.end_date} (${data.timezone})`;
        await loadOwnerExpenses();
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
    document.getElementById('serviceImageUploadResult').textContent = '';
    renderServiceImagePreview();
    serviceForm.hidden = false;
});
document.getElementById('cancelServiceForm')?.addEventListener('click', () => { serviceForm.hidden = true; });
document.getElementById('serviceSearch')?.addEventListener('input', (event) => {
    serviceSearchQuery = event.target.value;
    renderServiceCatalog(serviceCache);
});
document.getElementById('serviceCategories')?.addEventListener('click', handleServiceCategoryClick);
serviceForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const result = document.getElementById('serviceFormResult');
    const payload = {
        name: document.getElementById('serviceName').value.trim(),
        description: document.getElementById('serviceDescription').value.trim() || null,
        image_url: document.getElementById('serviceImageUrl').value.trim() || null,
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
    document.getElementById('serviceImageUrl').value = item.image_url || '';
    document.getElementById('serviceDuration').value = item.duration_minutes || 30;
    document.getElementById('servicePrice').value = (Number(item.price_cents) / 100).toFixed(2);
    document.getElementById('serviceCategory').value = item.category || 'haircut';
    document.getElementById('serviceFormResult').textContent = '';
    document.getElementById('serviceImageUploadResult').textContent = '';
    renderServiceImagePreview();
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

async function initializeAuthenticatedDashboard(user, { showWelcome = false } = {}) {
        if (user.role === 'client') {
            window.location.replace('/client-account.html');
            return;
        }
        accessToken = sessionStorage.getItem('token') || accessToken;
        currentUser = {
            email: user.email,
            name: user.full_name || user.name || user.email,
            role: user.role,
            feature_flags: user.feature_flags || {},
        };
        localStorage.setItem('userEmail', currentUser.email);
        const newServiceBtn = document.getElementById('newServiceBtn');
        if (newServiceBtn) newServiceBtn.hidden = currentUser.role !== 'barbershop_owner';
        const ownerTabButton = document.getElementById('ownerManagementTabButton');
        if (ownerTabButton) ownerTabButton.hidden = currentUser.role !== 'barbershop_owner';
        const achievementsButton = document.getElementById('achievementsTabButton');
        const achievementsPanel = document.getElementById('achievementsTab');
        if (achievementsButton) achievementsButton.hidden = currentUser.role !== 'barber';
        if (achievementsPanel) achievementsPanel.hidden = currentUser.role !== 'barber';
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

        if (showWelcome) {
            const welcomeMessage = barbershopProfile
                ? `Bienvenido a ${barbershopProfile.name}`
                : 'Acceso correcto';
            showToast(welcomeMessage, 'info');
        }
}

async function restoreAuthenticatedSession() {
    if (!accessToken) return;
    try {
        const response = await KingFlowAuth.fetch(`${API_ROOT}/api/v1/auth/me`);
        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                resetSessionInterface('Tu sesión expiró. Inicia sesión nuevamente para continuar.');
            }
            return;
        }
        await initializeAuthenticatedDashboard(await response.json());
    } catch (error) {
        console.warn('Could not restore the existing session:', error);
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
            showToast(data.detail || 'Credenciales inválidas');
            return;
        }
        accessToken = data.access_token;
        KingFlowAuth.setTokens(data.access_token, data.refresh_token);
        await initializeAuthenticatedDashboard(data.user, { showWelcome: true });
    } catch (error) {
        console.error(error);
        showToast('No fue posible conectar con el backend de autenticación');
    }
});

accessToken = sessionStorage.getItem('token');
setupLoginSupportPanel();
if (accessToken) void restoreAuthenticatedSession();

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
document.getElementById('startNextAppointmentButton')?.addEventListener('click', (event) => {
    const button = event.currentTarget;
    const appointmentId = Number(button.dataset.appointmentId);
    if (!button.disabled && Number.isInteger(appointmentId) && appointmentId > 0) {
        void updateAppointmentStatus(appointmentId, 'in_progress');
    }
});
document.getElementById('quickStatsButton')?.addEventListener('click', () => showTab('performance'));
document.getElementById('quickAgendaButton')?.addEventListener('click', () => showTab('appointments'));
document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
    tab.addEventListener('click', () => showTab(tab.dataset.tab));
});
document.getElementById('appointmentsList')?.addEventListener('click', async (event) => {
    const stylePassportButton = event.target.closest('.barber-style-passport-load');
    if (stylePassportButton) {
        const container = stylePassportButton.closest('.barber-style-passport');
        const clientId = Number(container?.dataset.clientId);
        const appointmentId = Number(container?.dataset.appointmentId);
        if (!Number.isInteger(clientId) || clientId <= 0
            || !Number.isInteger(appointmentId) || appointmentId <= 0) return;
        stylePassportButton.disabled = true;
        stylePassportButton.textContent = 'Actualizar registros';
        try {
            await loadBarberStylePassport(clientId, appointmentId, container);
        } finally {
            stylePassportButton.disabled = false;
        }
        return;
    }
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

console.log('KingFlow Barber Frontend Ready');
console.log('API Base:', API_ROOT);
