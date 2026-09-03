#!/usr/bin/env python3
"""
Script para crear archivos del frontend de KingFlow Barber
"""

import os

# HTML principal
html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KingFlow Barber - Sistema Operativo para Barberías</title>
    <link rel="stylesheet" href="css/styles.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo">
                <h1>👑 KingFlow Barber</h1>
                <p class="subtitle">Sistema Operativo para Barberías</p>
            </div>
            <div class="user-info" id="userInfo" style="display: none;">
                <span id="userName"></span>
                <button onclick="logout()" class="btn-secondary">Cerrar Sesión</button>
            </div>
        </header>

        <div id="loginSection" class="auth-section">
            <div class="auth-card">
                <h2>🔐 Iniciar Sesión</h2>
                <form id="loginForm">
                    <div class="form-group">
                        <label>Email</label>
                        <input type="email" id="loginEmail" required placeholder="admin@test.com" value="admin@test.com">
                    </div>
                    <div class="form-group">
                        <label>Contraseña</label>
                        <input type="password" id="loginPassword" required placeholder="••••••••" value="admin123">
                    </div>
                    <button type="submit" class="btn-primary">Entrar</button>
                </form>
                <div class="test-credentials">
                    <p>💡 <strong>Credenciales de prueba:</strong></p>
                    <p>Email: admin@test.com</p>
                    <p>Contraseña: admin123</p>
                </div>
            </div>
        </div>

        <div id="dashboardSection" style="display: none;">
            <nav class="tabs">
                <button class="tab active" onclick="showTab('serviceMode')">🔥 Modo Servicio</button>
                <button class="tab" onclick="showTab('appointments')">📅 Citas</button>
                <button class="tab" onclick="showTab('performance')">📊 Rendimiento</button>
                <button class="tab" onclick="showTab('achievements')">🎮 Logros</button>
            </nav>

            <div id="serviceModeTab" class="tab-content">
                <h2>🔥 Modo En Servicio</h2>
                <div class="info-card">
                    <h3>✅ Conectado a API</h3>
                    <p>El sistema está listo para conectarse al backend</p>
                    <p class="api-url">API: http://127.0.0.1:8000</p>
                    <button onclick="testConnection()" class="btn-primary">Probar Conexión</button>
                </div>
                <div id="connectionResult" style="margin-top: 20px;"></div>
            </div>

            <div id="appointmentsTab" class="tab-content" style="display: none;">
                <h2>📅 Mis Citas</h2>
                <div class="info-card">
                    <p>Lista de citas se cargará desde la API</p>
                </div>
            </div>

            <div id="performanceTab" class="tab-content" style="display: none;">
                <h2>📊 Mi Rendimiento</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-icon">📅</div>
                        <div class="stat-value">0</div>
                        <div class="stat-label">Citas Hoy</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">💰</div>
                        <div class="stat-value">$0</div>
                        <div class="stat-label">Ingresos</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">⚡</div>
                        <div class="stat-value">0%</div>
                        <div class="stat-label">Eficiencia</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-icon">🔥</div>
                        <div class="stat-value">0</div>
                        <div class="stat-label">Racha</div>
                    </div>
                </div>
            </div>

            <div id="achievementsTab" class="tab-content" style="display: none;">
                <h2>🎮 Mis Logros</h2>
                <div class="achievements-grid" id="achievementsGrid">
                    <p class="loading">Cargando logros...</p>
                </div>
            </div>
        </div>
    </div>

    <script src="js/main.js"></script>
</body>
</html>
"""

# CSS
css_content = """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    padding: 20px;
}

.container {
    max-width: 1400px;
    margin: 0 auto;
}

.header {
    background: white;
    padding: 20px 30px;
    border-radius: 15px;
    margin-bottom: 30px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.logo h1 {
    color: #667eea;
    font-size: 2em;
}

.subtitle {
    color: #666;
    font-size: 0.9em;
    margin-top: 5px;
}

.auth-section {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 60vh;
}

.auth-card {
    background: white;
    padding: 40px;
    border-radius: 15px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.2);
    width: 100%;
    max-width: 450px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group label {
    display: block;
    margin-bottom: 8px;
    color: #333;
    font-weight: 600;
}

.form-group input {
    width: 100%;
    padding: 12px;
    border: 2px solid #e0e0e0;
    border-radius: 8px;
    font-size: 14px;
    transition: all 0.3s;
}

.form-group input:focus {
    outline: none;
    border-color: #667eea;
}

.btn-primary {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.2s;
}

.btn-primary:hover {
    transform: translateY(-2px);
}

.btn-secondary {
    padding: 10px 20px;
    background: #6c757d;
    color: white;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
}

.test-credentials {
    margin-top: 20px;
    padding: 15px;
    background: #fff3cd;
    border-radius: 8px;
    font-size: 14px;
    color: #856404;
}

.test-credentials p {
    margin: 5px 0;
}

#dashboardSection {
    background: white;
    border-radius: 15px;
    padding: 30px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}

.tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 30px;
    border-bottom: 2px solid #e0e0e0;
    padding-bottom: 0;
    flex-wrap: wrap;
}

.tab {
    padding: 12px 24px;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    color: #666;
    transition: all 0.3s;
}

.tab.active {
    color: #667eea;
    border-bottom-color: #667eea;
}

.tab-content {
    display: none;
}

.tab-content h2 {
    color: #333;
    margin-bottom: 25px;
    font-size: 1.8em;
}

.info-card {
    background: #f8f9fa;
    padding: 30px;
    border-radius: 12px;
    text-align: center;
    color: #666;
}

.info-card h3 {
    color: #333;
    margin-bottom: 15px;
}

.api-url {
    color: #667eea;
    font-weight: 600;
    margin: 15px 0;
}

.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 25px;
    border-radius: 12px;
    text-align: center;
}

.stat-icon {
    font-size: 2.5em;
    margin-bottom: 10px;
}

.stat-value {
    font-size: 2.5em;
    font-weight: 700;
    margin: 10px 0;
}

.stat-label {
    font-size: 0.9em;
    opacity: 0.9;
}

.achievements-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 20px;
}

.achievement-card {
    background: #f8f9fa;
    padding: 20px;
    border-radius: 12px;
    text-align: center;
    transition: all 0.3s;
}

.achievement-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
}

.loading {
    text-align: center;
    padding: 40px;
    color: #999;
    font-style: italic;
}

.success-message {
    background: #d4edda;
    color: #155724;
    padding: 15px;
    border-radius: 8px;
    margin-top: 15px;
}

.error-message {
    background: #f8d7da;
    color: #721c24;
    padding: 15px;
    border-radius: 8px;
    margin-top: 15px;
}
"""

# JavaScript
js_content = """const API_BASE = 'http://127.0.0.1:8000';
let currentUser = null;

// Login
document.getElementById('loginForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('token', data.access_token);
            currentUser = data;

            document.getElementById('loginSection').style.display = 'none';
            document.getElementById('dashboardSection').style.display = 'block';
            document.getElementById('serviceModeTab').style.display = 'block';

            loadAchievements();
            showNotification('✅ Login exitoso!', 'success');
        } else {
            showNotification('❌ Credenciales incorrectas', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        showNotification('⚠️ No se puede conectar al servidor. ¿Está corriendo?', 'error');
    }
});

// Test connection
async function testConnection() {
    const resultDiv = document.getElementById('connectionResult');
    resultDiv.innerHTML = '<p>Probando conexión...</p>';

    try {
        const response = await fetch(`${API_BASE}/health`);
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
                <p>No se puede conectar al servidor en ${API_BASE}</p>
                <p>Verifica que el backend esté corriendo</p>
            </div>
        `;
    }
}

// Load achievements
async function loadAchievements() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const response = await fetch(`${API_BASE}/api/v1/achievements/`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const achievements = await response.json();
            displayAchievements(achievements);
        }
    } catch (error) {
        console.error('Error loading achievements:', error);
    }
}

// Display achievements
function displayAchievements(achievements) {
    const grid = document.getElementById('achievementsGrid');
    grid.innerHTML = achievements.map(achievement => `
        <div class="achievement-card">
            <div class="achievement-icon">${achievement.icon}</div>
            <h4>${achievement.name}</h4>
            <p>${achievement.description}</p>
            <p><strong>${achievement.points}</strong> puntos</p>
        </div>
    `).join('');
}

// Tab navigation
function showTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');

    event.target.classList.add('active');
    document.getElementById(tabName + 'Tab').style.display = 'block';
}

// Logout
function logout() {
    localStorage.removeItem('token');
    currentUser = null;
    document.getElementById('dashboardSection').style.display = 'none';
    document.getElementById('loginSection').style.display = 'block';
    showNotification('👋 Sesión cerrada', 'success');
}

// Notifications
function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = type === 'success' ? 'success-message' : 'error-message';
    notification.textContent = message;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '1000';
    notification.style.minWidth = '300px';

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Initialize
console.log('🚀 KingFlow Barber Frontend Ready');
console.log('📍 API Base:', API_BASE);
"""

# Crear archivos
frontend_dir = os.path.join('..', 'frontend')
os.makedirs(os.path.join(frontend_dir, 'css'), exist_ok=True)
os.makedirs(os.path.join(frontend_dir, 'js'), exist_ok=True)

with open(os.path.join(frontend_dir, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(html_content)

with open(os.path.join(frontend_dir, 'css', 'styles.css'), 'w', encoding='utf-8') as f:
    f.write(css_content)

with open(os.path.join(frontend_dir, 'js', 'main.js'), 'w', encoding='utf-8') as f:
    f.write(js_content)

print("✅ Frontend creado exitosamente!")
print("📁 Archivos:")
print("   - frontend/index.html")
print("   - frontend/css/styles.css")
print("   - frontend/js/main.js")
print("")
print("🌐 Abre: file:///C:/Users/Laptop%20(Martinez)/source/repos/BarberFlow/frontend/index.html")
