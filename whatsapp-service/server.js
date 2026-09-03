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

// Configuración
const PORT = 3001;
const app = express();

// Middleware
app.use(cors());
app.use(express.json());

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

    // Manejar mensajes entrantes (opcional, para logs)
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type === 'notify') {
            for (const msg of messages) {
                if (!msg.key.fromMe && msg.message) {
                    const from = msg.key.remoteJid;
                    const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
                    logger.info(`Mensaje recibido de ${from}: ${text}`);
                }
            }
        }
    });
}

/**
 * Formatear número de teléfono para WhatsApp
 */
function formatPhoneNumber(phone) {
    // Remover caracteres no numéricos
    let cleaned = phone.replace(/\D/g, '');

    // Si empieza con '1' y tiene 11 dígitos (USA/Canada), quitar el 1
    if (cleaned.startsWith('1') && cleaned.length === 11) {
        cleaned = cleaned.substring(1);
    }

    // Agregar código de país si no lo tiene (asumiendo República Dominicana)
    if (!cleaned.startsWith('1') && !cleaned.startsWith('809') && !cleaned.startsWith('829') && !cleaned.startsWith('849')) {
        cleaned = '1' + cleaned;
    }

    // Formato final para WhatsApp
    return cleaned + '@s.whatsapp.net';
}

/**
 * Validar que el mensaje no esté vacío
 */
function validateMessage(message) {
    if (!message || message.trim().length === 0) {
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

        // Enviar mensaje
        const result = await sock.sendMessage(jid, { text: message });

        logger.info(`Message sent to ${phone}`);

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
            error: error.message
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

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected'
            });
        }

        const jid = formatPhoneNumber(phone);
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
            error: error.message
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

        if (!isConnected) {
            return res.status(503).json({
                success: false,
                error: 'WhatsApp not connected'
            });
        }

        const jid = formatPhoneNumber(phone);
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
            error: error.message
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
            error: error.message
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
            error: error.message
        });
    }
});

// ==================== INICIALIZAR SERVIDOR ====================

// Iniciar servidor Express
app.listen(PORT, () => {
    console.log('\n╔════════════════════════════════════════════════════════╗');
    console.log('║                                                        ║');
    console.log('║       🚀 KINGFLOW WHATSAPP SERVICE INICIADO 🚀        ║');
    console.log('║                                                        ║');
    console.log('╚════════════════════════════════════════════════════════╝\n');
    console.log(`📍 Servidor corriendo en: http://localhost:${PORT}`);
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

// Conectar a WhatsApp al iniciar
connectToWhatsApp();

// Manejar cierre graceful
process.on('SIGINT', async () => {
    console.log('\n\n🛑 Cerrando servicio...');
    if (sock) {
        await sock.end();
    }
    process.exit(0);
});
