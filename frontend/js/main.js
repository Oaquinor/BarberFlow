const API_BASE = 'http://127.0.0.1:8000';
const APP_CONFIG = window.KINGFLOW_CONFIG || {};
const API_ROOT = APP_CONFIG.apiBaseUrl || API_BASE;

let currentUser = null;
let barbershopProfile = null;
let dashboardLayout = null;
let accessToken = null;

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
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

function renderWeeklyChart(weeklyCounts) {
    const chartBars = document.getElementById('performanceChartBars');
    if (!chartBars) return;

    const data = Array.isArray(weeklyCounts) ? weeklyCounts : [];
    if (!data.length) {
        chartBars.innerHTML = '<div class="chart-bar future" style="height:100%;"><div class="bar-fill" style="height:0%"></div><span class="bar-label">-</span></div>';
        return;
    }

    chartBars.innerHTML = data.map((item) => {
        const pct = Number(item.height_percent || 0);
        const isFuture = Number(item.count || 0) === 0;
        return `
            <div class="chart-bar ${isFuture ? 'future' : ''}" style="height: ${Math.max(25, pct)}%;">
                <div class="bar-fill" style="height: 100%;" title="${item.label}: ${item.count} citas"></div>
                <span class="bar-label">${item.label}</span>
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
        const unlocked = current >= target;

        return `
            <div class="achievement-card ${unlocked ? 'unlocked' : 'locked'}">
                <div class="achievement-icon ${unlocked ? '' : 'locked-icon'}">${unlocked ? '🏆' : '🔒'}</div>
                <h4>${item.title}</h4>
                <p>${item.description}</p>
                <div class="achievement-points">${item.points} puntos</div>
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
    return `$${value.toFixed(2)}`;
}

function fmtHour(dateLike) {
    const d = new Date(dateLike);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

function applyBranding(profile) {
    const logoElement = document.querySelector('.logo h1');
    if (logoElement && profile?.logo_url) {
        logoElement.innerHTML = `<img src="${profile.logo_url}" style="height: 40px; vertical-align: middle; margin-right: 10px;">${profile.name}`;
    } else if (logoElement && profile?.name) {
        logoElement.innerHTML = `👑 ${profile.name}`;
    }

    if (profile?.primary_color) {
        document.documentElement.style.setProperty('--brand-primary', profile.primary_color);
    }
    if (profile?.secondary_color) {
        document.documentElement.style.setProperty('--brand-secondary', profile.secondary_color);
    }

    const authHeaderTitle = document.querySelector('.auth-header h2');
    const authHeaderSubtitle = document.querySelector('.auth-header p');
    if (authHeaderTitle && profile?.name) authHeaderTitle.textContent = `Iniciar Sesión - ${profile.name}`;
    if (authHeaderSubtitle && profile?.name) authHeaderSubtitle.textContent = `Accede a tu cuenta de ${profile.name}`;
}

async function loadBarbershopProfile() {
    try {
        const response = await fetch(`${API_ROOT}/api/v1/onboarding/profile`);
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
        renderDynamicAchievements();
        return true;
    } catch (error) {
        console.error('Error loading profile:', error);
        return true;
    }
}

async function loadDashboardLayout() {
    try {
        const response = await fetch(`${API_ROOT}/api/v1/onboarding/dashboard-layout`);
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
                        <p>${insight}</p>
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
        const response = await fetch(`${API_ROOT}/api/v1/onboarding/motivational-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ achievement_type })
        });

        if (!response.ok) return;

        const message = await response.json();
        const container = document.getElementById('smartMessages');
        if (container && message) {
            container.innerHTML = `
                <div style="background: rgba(255,255,255,0.95); border-left: 5px solid var(--brand-primary); padding: 14px 16px; border-radius: 12px; margin-bottom: 16px;">
                    <strong>${message.icon} ${message.type === 'celebration' ? 'Celebración' : 'Mensaje inteligente'}</strong>
                    <div style="margin-top: 6px; color: #444;">${message.message}</div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading smart message:', error);
    }
}

function renderDynamicAchievements() {
    const dynamicContainer = document.getElementById('dynamicAchievements');
    if (!dynamicContainer || !barbershopProfile) return;

    const goal = barbershopProfile.primary_goal || 'more_clients';
    const personality = barbershopProfile.personality || 'friendly';

    const goalAchievements = {
        more_clients: ['🚀 Imán de Clientes', 'Logra 20 clientes nuevos en 30 días', '120'],
        organization: ['📅 Agenda Perfecta', '7 días sin huecos improductivos', '100'],
        reduce_cancellations: ['🛡️ Cero Cancelaciones', 'Mantén tasa de cancelación < 5%', '140'],
        save_time: ['⚡ Maestro del Tiempo', 'Reduce 10% el tiempo promedio por servicio', '130'],
        better_service: ['⭐ Experiencia 5 Estrellas', 'Mantén satisfacción promedio > 4.8', '160'],
        productivity: ['🔥 Modo Bestia', 'Completa 12 servicios en un día', '180']
    };

    const personalityBonus = {
        professional: '🏅 Consistencia Profesional',
        friendly: '🤝 Cliente Amigo',
        energetic: '⚡ Energía Imparable',
        elegant: '💎 Sello Premium',
        authentic: '🎭 Estilo Auténtico'
    };

    const [title, desc, points] = goalAchievements[goal] || goalAchievements.more_clients;
    const bonus = personalityBonus[personality] || '✨ Estilo Único';

    dynamicContainer.innerHTML = `
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 18px;">
            <div class="achievement-card unlocked">
                <div class="achievement-icon">${title.split(' ')[0]}</div>
                <h4>${title.substring(2)}</h4>
                <p>${desc}</p>
                <div class="achievement-points">${points} puntos</div>
                <div class="achievement-rarity epic">Objetivo</div>
            </div>
            <div class="achievement-card unlocked">
                <div class="achievement-icon">${bonus.split(' ')[0]}</div>
                <h4>${bonus.substring(2)}</h4>
                <p>Logro alineado con tu personalidad de marca</p>
                <div class="achievement-points">90 puntos</div>
                <div class="achievement-rarity rare">Marca</div>
            </div>
        </div>
    `;
}

async function loadContextualGreeting() {
    try {
        const response = await fetch(`${API_ROOT}/api/v1/onboarding/greeting`);
        if (!response.ok) return;

        const greeting = await response.json();
        const greetingElement = document.getElementById('contextualGreeting');
        if (greetingElement) {
            greetingElement.innerHTML = `
                <div style="background: rgba(255,255,255,0.15); padding: 15px 20px; border-radius: 12px; margin-bottom: 20px; color: white;">
                    <span style="font-size: 1.2em;">${greeting.icon}</span>
                    <span style="margin-left: 10px; font-weight: 600;">${greeting.message}</span>
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
        const response = await fetch(`${API_ROOT}/api/v1/barber/share-link`, {
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
                    alert('✅ Link copiado');
                } catch (_) {
                    alert('⚠️ No se pudo copiar automáticamente');
                }
            };
        }

        if (waBtn) {
            waBtn.onclick = () => window.open(data.whatsapp_share_link, '_blank');
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
        const response = await fetch(`${API_ROOT}/api/v1/barber/slots`, {
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
    } catch (error) {
        console.error(error);
        if (result) result.textContent = 'Error de conexión creando turnos';
    }
}

async function loadBarberDashboardData() {
    if (!accessToken) return;

    try {
        const response = await fetch(`${API_ROOT}/api/v1/barber/dashboard`, {
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
        setText('appointmentsDateHeader', new Date().toLocaleDateString('es-DO', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }));

        const active = (Array.isArray(data.appointments) ? data.appointments : []).find((a) => a.status === 'in_progress') || null;
        if (active) {
            setText('activeServiceClient', active.client_name || 'Cliente');
            setText('activeServiceType', active.service_type || 'Servicio');
            setText('activeServiceEstimated', `${active.estimated_duration || 0} minutos`);

            const progressPct = Math.min(100, Math.max(1, Math.round((Number(summary.efficiency_percent || 0)))));
            setText('activeServiceProgress', `${progressPct}%`);
            const progressBar = document.getElementById('activeServiceProgressBar');
            if (progressBar) progressBar.style.width = `${progressPct}%`;
            setText('activeServiceAlert', `⚠️ Servicio activo con progreso estimado en ${progressPct}%`);
        } else {
            setText('activeServiceClient', 'Sin servicio activo');
            setText('activeServiceType', 'Esperando próximas citas');
            setText('activeServiceEstimated', '-- minutos');
            setText('activeServiceProgress', '0%');
            const progressBar = document.getElementById('activeServiceProgressBar');
            if (progressBar) progressBar.style.width = '0%';
            setText('activeServiceAlert', '⏳ Sin servicio activo en este momento');
        }

        const next = data.next_appointment;
        if (next) {
            setText('nextAppointmentTime', fmtHour(next.scheduled_time));
            setText('nextAppointmentClient', next.client_name || 'Cliente');
            setText('nextAppointmentService', next.service_type || 'Servicio');
            setText('nextAppointmentDuration', `⏱️ ${next.estimated_duration || 0} min estimados`);

            const etaEl = document.getElementById('nextAppointmentEta');
            if (etaEl) {
                const mins = Math.max(0, Math.round((new Date(next.scheduled_time) - new Date()) / 60000));
                etaEl.textContent = mins <= 1 ? 'Ahora' : `En ${mins} minutos`;
            }
        }

        const appointmentsList = document.getElementById('appointmentsList');
        if (appointmentsList) {
            const appointments = Array.isArray(data.appointments) ? data.appointments : [];
            if (!appointments.length) {
                appointmentsList.innerHTML = '<div class="appointment-card"><div class="appointment-content"><p class="service-name">No hay citas para hoy.</p></div></div>';
            } else {
                appointmentsList.innerHTML = appointments.map((a) => `
                    <div class="appointment-card ${cardClassForStatus(a.status)}">
                        <div class="appointment-time-badge ${a.status === 'in_progress' ? 'current' : ''}">${fmtHour(a.scheduled_time)}</div>
                        <div class="appointment-content">
                            <div class="appointment-header">
                                <h4>${a.client_name || 'Cliente'}</h4>
                                <span class="status-badge ${statusClassForStatus(a.status)}">${labelStatus(a.status)}</span>
                            </div>
                            <p class="service-name">${a.service_type || 'Servicio'}</p>
                            <div class="appointment-meta">
                                <span>⏱️ ${a.estimated_duration || 0} min</span>
                                <span>💰 ${fmtMoneyFromCents(a.service_price || 0)}</span>
                            </div>
                            <div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">
                                ${a.status !== 'in_progress' && a.status !== 'completed' ? `<button class="btn-start" type="button" onclick="updateAppointmentStatus(${a.id}, 'in_progress')">▶️ Iniciar</button>` : ''}
                                ${a.status !== 'completed' ? `<button class="btn-secondary" type="button" onclick="updateAppointmentStatus(${a.id}, 'completed')">✅ Completar</button>` : ''}
                                ${a.status !== 'cancelled' && a.status !== 'completed' ? `<button class="btn-secondary" type="button" onclick="updateAppointmentStatus(${a.id}, 'cancelled')">❌ Cancelar</button>` : ''}
                            </div>
                        </div>
                    </div>
                `).join('');
            }
        }

        const servicesList = document.getElementById('servicesList');
        if (servicesList) {
            const services = Array.isArray(data.services) ? data.services : [];
            if (!services.length) {
                servicesList.innerHTML = '<div class="service-item"><div class="service-info"><h4>Sin servicios activos</h4><p>Crea servicios desde tu configuración para verlos aquí.</p></div></div>';
            } else {
                servicesList.innerHTML = services.map((s) => `
                    <div class="service-item ${s.category === 'combo' ? 'featured' : ''}">
                        <div class="service-icon">✂️</div>
                        <div class="service-info">
                            <h4>${s.name}</h4>
                            <p>${s.description || 'Servicio personalizado de la barbería'}</p>
                            <div class="service-meta">
                                <span class="tag">${s.category || 'General'}</span>
                                <span>⏱️ ${s.duration_minutes || 0} min</span>
                            </div>
                        </div>
                        <div class="service-price">${fmtMoneyFromCents(s.price_cents || 0)}</div>
                        <button class="btn-icon" type="button">✏️</button>
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

        result.textContent = `✅ Soporte enviado a ${data.sent_to} usuario(s).`;
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

    resultDiv.innerHTML = '<p>Probando conexión...</p>';

    try {
        const response = await fetch(`${API_ROOT}/health`);
        if (response.ok) {
            const data = await response.json();
            resultDiv.innerHTML = `
                <div class="success-message">
                    <h4>✅ Conexión Exitosa</h4>
                    <p>Status: ${data.status}</p>
                    <p>Database: ${data.database}</p>
                </div>
            `;
        }
    } catch (error) {
        resultDiv.innerHTML = `
            <div class="error-message">
                <h4>❌ Error de Conexión</h4>
                <p>No se puede conectar al servidor en ${API_ROOT}</p>
                <p>Verifica que el backend esté corriendo</p>
            </div>
        `;
    }
}

function showTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

    const selectedTab = document.querySelector(`.tab[onclick*="showTab('${tabName}')"]`);
    if (selectedTab) selectedTab.classList.add('active');

    const content = document.getElementById(`${tabName}Tab`);
    if (content) content.style.display = 'block';
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('userEmail');
    accessToken = null;
    currentUser = null;

    document.getElementById('dashboardSection').style.display = 'none';
    document.getElementById('loginSection').style.display = 'flex';
    document.getElementById('userInfo').style.display = 'none';

    document.getElementById('loginEmail').value = '';
    document.getElementById('loginPassword').value = '';

    alert('👋 Sesión cerrada exitosamente');
}

function finishService() {
    const inProgressCard = document.querySelector('#appointmentsList .appointment-card.in-progress');
    if (!inProgressCard) {
        alert('No hay servicio en progreso para finalizar.');
        return;
    }

    const startBtn = inProgressCard.querySelector('button.btn-secondary');
    if (!startBtn) {
        alert('No se encontró cita para finalizar.');
        return;
    }

    const clickHandler = startBtn.getAttribute('onclick') || '';
    const match = clickHandler.match(/updateAppointmentStatus\((\d+),\s*'completed'\)/);
    if (!match) {
        alert('No se pudo identificar la cita activa.');
        return;
    }

    updateAppointmentStatus(Number(match[1]), 'completed');
}

function pauseService() {
    const inProgressCard = document.querySelector('#appointmentsList .appointment-card.in-progress');
    if (!inProgressCard) {
        alert('No hay servicio en progreso para pausar.');
        return;
    }

    const completeBtn = inProgressCard.querySelector("button[onclick*=\"'completed'\"]");
    if (!completeBtn) {
        alert('No se encontró cita en progreso para pausar.');
        return;
    }

    const clickHandler = completeBtn.getAttribute('onclick') || '';
    const match = clickHandler.match(/updateAppointmentStatus\((\d+),\s*'completed'\)/);
    if (!match) {
        alert('No se pudo identificar la cita activa.');
        return;
    }

    updateAppointmentStatus(Number(match[1]), 'confirmed');
}

async function updateAppointmentStatus(appointmentId, status) {
    if (!accessToken) return;
    try {
        const response = await fetch(`${API_ROOT}/api/v1/barber/appointments/${appointmentId}/status`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ status })
        });

        const data = await response.json();
        if (!response.ok) {
            alert(data.detail || 'No se pudo actualizar el estado de la cita');
            return;
        }

        await loadBarberDashboardData();
    } catch (error) {
        console.error('Error updating appointment status:', error);
        alert('Error de conexión actualizando cita');
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
            alert(`❌ ${data.detail || 'Credenciales inválidas'}`);
            return;
        }

        accessToken = data.access_token;
        localStorage.setItem('token', accessToken);
        localStorage.setItem('userEmail', data.user.email);

        currentUser = {
            email: data.user.email,
            name: data.user.full_name,
            role: data.user.role
        };

        const canContinue = await loadBarbershopProfile();
        if (!canContinue) return;

        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('dashboardSection').style.display = 'block';
        document.getElementById('serviceModeTab').style.display = 'block';
        document.getElementById('userInfo').style.display = 'flex';
        document.getElementById('userName').textContent = currentUser.name;

        await loadShareLink();

        const createSlotsBtn = document.getElementById('createSlotsBtn');
        if (createSlotsBtn) createSlotsBtn.onclick = createBarberSlots;

        const slotDate = document.getElementById('slotDate');
        if (slotDate && !slotDate.value) {
            slotDate.value = new Date().toISOString().slice(0, 10);
        }

        await loadBarberDashboardData();

        const welcomeMessage = barbershopProfile
            ? `✅ Bienvenido a ${barbershopProfile.name}`
            : '✅ Login exitoso';
        alert(welcomeMessage);
    } catch (error) {
        console.error(error);
        alert('❌ No fue posible conectar con el backend de autenticación');
    }
});

accessToken = localStorage.getItem('token');
setupLoginSupportPanel();

console.log('🚀 KingFlow Barber Frontend Ready');
console.log('📍 API Base:', API_ROOT);
