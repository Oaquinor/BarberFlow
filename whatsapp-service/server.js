/**
 * KingFlow Barber - WhatsApp Service using Baileys
 * 
 * Este servicio mantiene una conexión permanente con WhatsApp
 * y expone una API REST para enviar mensajes desde FastAPI.
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const express = require('express');
const cors = require('cors');
const qrcode = require('qrcode-terminal');
const pino = require('pino');
const crypto = require('crypto');

// Configuración
const PORT = 3001;
const HOST = process.env.WHATSAPP_BIND_HOST || '127.0.0.1';
const API_TOKEN = process.env.WHATSAPP_API_TOKEN || '';
const app = express();

// Middleware
const allowedOrigins = (process.env.WHATSAPP_CORS_ORIGINS || '').split(',').map(value => value.trim()).filter(Boolean);
app.use(cors({
    origin(origin, callback) {
        if (!origin || allowedOrigins.includes(origin)) return callback(null, true);
        return callback(null, false);
    }
}));
// Keep payloads bounded; message validation runs after JSON parsing.
app.use(express.json({ limit: '16kb' }));

function requireApiToken(req, res, next) {
    if (!API_TOKEN) {
        return res.status(503).json({ success: false, error: 'WhatsApp API token is not configured' });
    }
    const match = /^Bearer\s+(.+)$/i.exec(req.get('authorization') || '');
    const supplied = Buffer.from(match?.[1] || '');
    const expected = Buffer.from(API_TOKEN);
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(supplied, expected)) {
        return res.status(401).json({ success: false, error: 'Unauthorized' });
    }
    return next();
}

app.use(['/send', '/send-formatted', '/send-image', '/check', '/info', '/disconnect'], requireApiToken);

// Logger
const logger = pino({ level: 'info' });

// Estado de la conexión
let sock = null;
let isConnected = false;
let qrCodeGenerated = false;

/**
 * Conectar a WhatsApp usando Baileys
 */
async function connectToWhatsApp() {
    // Cargar estado de autenticación (o crear uno nuevo)
    const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');

    // Obtener última versión de Baileys
    const { version, isLatest } = await fetchLatestBaileysVersion();
    logger.info(`Using WA v${version.join('.')}, isLatest: ${isLatest}`);

    // Crear socket de WhatsApp
    sock = makeWASocket({
        version,
        logger: pino({ level: 'silent' }), // Silenciar logs internos de Baileys
        printQRInTerminal: false, // Vamos a manejar el QR nosotros
        auth: state,
        browser: ['KingFlow Barber', 'Chrome', '10.0.0'], // Identificación del cliente
        defaultQueryTimeoutMs: undefined,
    });

    // Guardar credenciales cuando cambien
    sock.ev.on('creds.update', saveCreds);

    // Manejar cambios de conexión
    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        // Mostrar QR code si es necesario
        if (qr) {
            qrCodeGenerated = true;
            console.log('\n╔════════════════════════════════════════════════════════╗');
            console.log('║                                                        ║');
            console.log('║     📱 ESCANEA ESTE QR CON TU WHATSAPP 📱            ║');
            console.log('║                                                        ║');
            console.log('╚════════════════════════════════════════════════════════╝\n');
            qrcode.generate(qr, { small: true });
            console.log('\n✅ Después de escanear, la sesión quedará guardada');
            console.log('⏱️  No necesitarás escanear de nuevo la próxima vez\n');
        }

        // Conexión abierta
        if (connection === 'open') {
            isConnected = true;
            qrCodeGenerated = false;
            console.log('\n╔════════════════════════════════════════════════════════╗');
            console.log('║                                                        ║');
            console.log('║          ✅ WHATSAPP CONECTADO EXITOSAMENTE ✅        ║');
            console.log('║                                                        ║');
            console.log('╚════════════════════════════════════════════════════════╝\n');
            logger.info('WhatsApp connected successfully');
        }

        // Conexión cerrada
        if (connection === 'close') {
            isConnected = false;
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;

            console.log('\n⚠️  Conexión cerrada:', lastDisconnect?.error?.message);

            if (shouldReconnect) {
                console.log('🔄 Reconectando automáticamente en 5 segundos...\n');
                setTimeout(() => connectToWhatsApp(), 5000);
            } else {
                console.log('❌ Sesión cerrada. Necesitas escanear el QR de nuevo.\n');
                console.log('💡 Reinicia el servicio con: npm start\n');
            }
        }
    });

}

/**
 * Formatear número de teléfono para WhatsApp
 */
function formatPhoneNumber(phone) {
    if (typeof phone !== 'string' || !/^\+?[\d\s().-]+$/.test(phone.trim())) return null;
    let cleaned = phone.replace(/\D/g, '');
    // A ten digit number is in the NANP; retain/add its country code for the WhatsApp JID.
    if (cleaned.length === 10) cleaned = `1${cleaned}`;
    if (cleaned.length < 8 || cleaned.length > 15) return null;
    return cleaned + '@s.whatsapp.net';
}

/**
 * Validar que el mensaje no esté vacío
 */
function validateMessage(message) {
    if (typeof message !== 'string' || message.trim().length === 0) {
        return { valid: false, error: 'Message cannot be empty' };
    }
    if (message.length > 4096) {
        return { valid: false, error: 'Message too long (max 4096 characters)' };
    }
    return { valid: true };
}

// ==================== REST API ENDPOINTS ====================

/**
 * Health check
 */
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        connected: isConnected,
        waiting_qr: qrCodeGenerated,
        timestamp: new Date().toISOString()
    });
});

/**
 * Enviar mensaje de WhatsApp
 * 
 * POST /send
 * Body: { phone: "+18095555555", message: "Hola!" }
 */
app.post('/send', async (req, res) => {
    try {
        const { phone, message } = req.body;

        // Validaciones
        if (!phone) {
            return res.status(400).json({
                success: false,
                error: 'Phone number is required'
            });
        }

        const validation = validateMessage(message);
        if (!validation.valid) {
            return res.status(400).json({
                success: false,
                error: validation.error
            });
        }

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected',
                waiting_qr: qrCodeGenerated
            });
        }

        // Formatear número
        const jid = formatPhoneNumber(phone);
        if (!jid) return res.status(400).json({ success: false, error: 'Invalid phone number' });

        // Enviar mensaje
        const result = await sock.sendMessage(jid, { text: message });

        logger.info({ recipient_suffix: jid.slice(0, -'@s.whatsapp.net'.length).slice(-4) }, 'WhatsApp message sent');

        res.json({
            success: true,
            message: 'Message sent successfully',
            messageId: result.key.id,
            timestamp: new Date().toISOString()
        });

    } catch (error) {
        logger.error('Error sending message:', error);
        res.status(500).json({
            success: false,
            error: 'Unable to send message'
        });
    }
});

/**
 * Enviar mensaje con formato (negritas, cursivas, etc.)
 * 
 * POST /send-formatted
 * Body: { phone: "+18095555555", message: "*Texto en negrita*\n_Texto en cursiva_" }
 */
app.post('/send-formatted', async (req, res) => {
    try {
        const { phone, message } = req.body;

        if (!phone || !message) {
            return res.status(400).json({
                success: false,
                error: 'Phone and message are required'
            });
        }

        const validation = validateMessage(message);
        if (!validation.valid) {
            return res.status(400).json({ success: false, error: validation.error });
        }

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected'
            });
        }

        const jid = formatPhoneNumber(phone);
        if (!jid) return res.status(400).json({ success: false, error: 'Invalid phone number' });
        const result = await sock.sendMessage(jid, { text: message });

        res.json({
            success: true,
            message: 'Formatted message sent successfully',
            messageId: result.key.id
        });

    } catch (error) {
        logger.error('Error sending formatted message:', error);
        res.status(500).json({
            success: false,
            error: 'Unable to send formatted message'
        });
    }
});

/**
 * Enviar mensaje con imagen
 * 
 * POST /send-image
 * Body: { phone: "+18095555555", imageUrl: "https://...", caption: "Texto" }
 */
app.post('/send-image', async (req, res) => {
    try {
        const { phone, imageUrl, caption } = req.body;

        if (!phone || !imageUrl) {
            return res.status(400).json({
                success: false,
                error: 'Phone and imageUrl are required'
            });
        }

        let image;
        try {
            image = new URL(imageUrl);
        } catch (_) {
            return res.status(400).json({ success: false, error: 'Invalid image URL' });
        }
        if (!['http:', 'https:'].includes(image.protocol)) {
            return res.status(400).json({ success: false, error: 'Image URL must use HTTP or HTTPS' });
        }

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected'
            });
        }

        const jid = formatPhoneNumber(phone);
        if (!jid) return res.status(400).json({ success: false, error: 'Invalid phone number' });
        const result = await sock.sendMessage(jid, {
            image: { url: imageUrl },
            caption: caption || ''
        });

        res.json({
            success: true,
            message: 'Image sent successfully',
            messageId: result.key.id
        });

    } catch (error) {
        logger.error('Error sending image:', error);
        res.status(500).json({
            success: false,
            error: 'Unable to send image'
        });
    }
});

/**
 * Verificar si un número tiene WhatsApp
 * 
 * GET /check/:phone
 */
app.get('/check/:phone', async (req, res) => {
    try {
        const { phone } = req.params;

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected'
            });
        }

        const jid = formatPhoneNumber(phone);
        if (!jid) return res.status(400).json({ success: false, error: 'Invalid phone number' });
        const [result] = await sock.onWhatsApp(jid);

        res.json({
            success: true,
            exists: !!result,
            jid: result?.jid || null
        });

    } catch (error) {
        logger.error('Error checking number:', error);
        res.status(500).json({
            success: false,
            error: 'Unable to check number'
        });
    }
});

/**
 * Obtener información de la conexión
 * 
 * GET /info
 */
app.get('/info', (req, res) => {
    if (!isConnected || !sock) {
        return res.json({
            connected: false,
            waiting_qr: qrCodeGenerated
        });
    }

    res.json({
        connected: true,
        user: sock.user,
        platform: 'baileys',
        version: '1.0.0'
    });
});

/**
 * Desconectar WhatsApp (útil para mantenimiento)
 * 
 * POST /disconnect
 */
app.post('/disconnect', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
            isConnected = false;
            res.json({
                success: true,
                message: 'Disconnected successfully'
            });
        } else {
            res.json({
                success: false,
                message: 'Not connected'
            });
        }
    } catch (error) {
        res.status(500).json({
            success: false,
            error: 'Unable to disconnect WhatsApp'
        });
    }
});

// Keep parser failures bounded and JSON-shaped without exposing stack traces.
app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);
    const tooLarge = error?.type === 'entity.too.large';
    return res.status(tooLarge ? 413 : 400).json({
        success: false,
        error: tooLarge ? 'Request body too large' : 'Invalid request body'
    });
});

// ==================== INICIALIZAR SERVIDOR ====================

function startServer() {
  app.listen(PORT, HOST, () => {
    console.log('\n╔════════════════════════════════════════════════════════╗');
    console.log('║                                                        ║');
    console.log('║       🚀 KINGFLOW WHATSAPP SERVICE INICIADO 🚀        ║');
    console.log('║                                                        ║');
    console.log('╚════════════════════════════════════════════════════════╝\n');
    console.log(`📍 Servidor corriendo en: http://${HOST}:${PORT}`);
    if (!API_TOKEN) logger.warn('WHATSAPP_API_TOKEN is not configured; protected API endpoints are disabled');
    console.log(`📊 Health check: http://localhost:${PORT}/health`);
    console.log(`📚 Endpoints disponibles:`);
    console.log(`   POST /send - Enviar mensaje`);
    console.log(`   POST /send-formatted - Enviar con formato`);
    console.log(`   POST /send-image - Enviar imagen`);
    console.log(`   GET  /check/:phone - Verificar número`);
    console.log(`   GET  /info - Info de conexión`);
    console.log(`   POST /disconnect - Desconectar\n`);
    console.log('⏳ Conectando a WhatsApp...\n');
  });

  // Connect only for the real service process; tests can import pure helpers safely.
  connectToWhatsApp();
}

if (require.main === module) startServer();

if (require.main === module) process.on('SIGINT', async () => {
    console.log('\n\n🛑 Cerrando servicio...');
    if (sock) {
        await sock.end();
    }
    process.exit(0);
});

module.exports = { app, formatPhoneNumber, requireApiToken, validateMessage };
