# 🌐 KingFlow Barber - Frontend

**Interfaz web para el sistema operativo de barberías**

---

## 🚀 Inicio Rápido

### **Opción 1: Servidor Python (Recomendado)**

```bash
cd backend
python scripts/serve_frontend.py
```

Luego abre: **http://localhost:3000**

### **Opción 2: Abrir directamente**

Abre el archivo `index.html` en tu navegador:
```
file:///C:/Users/Laptop%20(Martinez)/source/repos/BarberFlow/frontend/index.html
```

---

## 🔐 Credenciales de Prueba

**Email:** `admin@test.com`  
**Contraseña:** `admin123`

> Estas credenciales están pre-cargadas en el formulario de login

---

## 📋 Funcionalidades

### ✅ Implementadas

1. **🔐 Autenticación**
   - Login con JWT
   - Almacenamiento de token
   - Logout

2. **🔥 Modo Servicio**
   - Test de conexión con API
   - Vista de servicio activo (próximamente)

3. **📅 Citas**
   - Lista de citas del día (próximamente)
   - Inicio de servicio desde cita

4. **📊 Rendimiento**
   - Dashboard con métricas diarias
   - Citas completadas
   - Ingresos del día
   - Eficiencia de tiempo
   - Racha de días trabajados

5. **🎮 Logros**
   - Grid de logros disponibles
   - Progreso y puntos
   - Logros desbloqueados

---

## 🏗️ Estructura de Archivos

```
frontend/
├── index.html          # Página principal
├── css/
│   └── styles.css      # Estilos completos
└── js/
    └── main.js         # Lógica de la aplicación
```

---

## 🔌 Conectividad con API

El frontend se conecta a la API en:
- **Base URL:** `http://127.0.0.1:8000`
- **Endpoints usados:**
  - `POST /api/v1/auth/login` - Autenticación
  - `GET /health` - Verificar servidor
  - `GET /api/v1/achievements/` - Obtener logros
  - `GET /api/v1/service-mode/active` - Servicio activo
  - `GET /api/v1/performance/daily/{barber_id}` - Métricas

---

## 🎨 Diseño

### Paleta de Colores
- **Primario:** `#667eea` → `#764ba2` (Gradient)
- **Éxito:** `#4ade80`
- **Error:** `#ef4444`
- **Advertencia:** `#f59e0b`
- **Neutral:** `#6c757d`

### Componentes
- ✅ Cards responsivos
- ✅ Formularios con validación
- ✅ Tabs de navegación
- ✅ Stats grid (métricas)
- ✅ Achievement cards
- ✅ Notificaciones toast

---

## 🔧 Desarrollo

### Requisitos
- Python 3.8+ (para servidor)
- Navegador moderno (Chrome, Firefox, Edge)
- Backend corriendo en puerto 8000

### Scripts Útiles

**Iniciar backend:**
```bash
cd backend
uvicorn app.main:app --reload
```

**Iniciar frontend:**
```bash
cd backend
python scripts/serve_frontend.py
```

**Abrir en navegador:**
```bash
start http://localhost:3000
```

---

## 📱 Responsive Design

El frontend es completamente responsive:
- ✅ Desktop (1400px+)
- ✅ Tablet (768px - 1399px)
- ✅ Mobile (< 768px)

---

## 🐛 Troubleshooting

### ❌ No se conecta a la API

1. Verifica que el backend esté corriendo:
   ```bash
   curl http://127.0.0.1:8000/health
   ```

2. Revisa la consola del navegador (F12)

3. Verifica que MySQL esté corriendo en Laragon

### ❌ Login no funciona

1. Verifica credenciales: `admin@test.com` / `admin123`
2. Revisa que el usuario exista en la base de datos
3. Verifica logs del backend

### ❌ CORS errors

Usa el servidor Python en lugar de abrir el HTML directamente:
```bash
python scripts/serve_frontend.py
```

---

## 🚧 Próximas Funcionalidades

- [ ] Timer en vivo para servicio activo
- [ ] Notificaciones push
- [ ] Gráficos de rendimiento (Chart.js)
- [ ] Calendario interactivo
- [ ] Chat interno
- [ ] Modo oscuro
- [ ] PWA (Progressive Web App)
- [ ] Notificaciones de navegador

---

## 📚 Tecnologías Usadas

- **HTML5** - Estructura
- **CSS3** - Estilos (Flexbox, Grid, Animations)
- **JavaScript ES6+** - Lógica
- **Fetch API** - Comunicación con backend
- **LocalStorage** - Almacenamiento de token

---

## 📄 Licencia

Parte del proyecto KingFlow Barber - Sistema Operativo para Barberías

---

**Última actualización:** 2024-05-30
