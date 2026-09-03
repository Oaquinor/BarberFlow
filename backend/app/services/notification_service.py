"""
Notification Service for KingFlow Barber
Handles email and SMS/WhatsApp notifications to clients
"""

from typing import Dict, Optional
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.user import User
from app.models.barbershop import Barbershop
from app.core.config import settings


class NotificationService:
    """Service for sending notifications to clients."""

    def __init__(self, db: Session):
        self.db = db

    # ==================== EMAIL NOTIFICATIONS ====================

    def send_appointment_confirmation(
        self,
        appointment: Appointment
    ) -> bool:
        """
        Send confirmation email when appointment is created.

        Args:
            appointment: Appointment instance

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barber = self.db.query(User).filter(User.id == appointment.barber_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.email:
            return False

        subject = f"✅ Cita Confirmada - {barbershop.name}"

        body = self._get_confirmation_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=barbershop.name,
            scheduled_time=appointment.scheduled_time,
            service_type=appointment.service_type,
            estimated_duration=appointment.estimated_duration,
            barbershop_address=barbershop.address or "N/A",
            barbershop_phone=barbershop.phone or "N/A"
        )

        return self._send_email(
            to_email=client.email,
            subject=subject,
            body=body
        )

    def send_appointment_reminder(
        self,
        appointment: Appointment
    ) -> bool:
        """
        Send reminder 24h before appointment.

        Args:
            appointment: Appointment instance

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barber = self.db.query(User).filter(User.id == appointment.barber_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.email:
            return False

        subject = f"⏰ Recordatorio de Cita - {barbershop.name}"

        body = self._get_reminder_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=barbershop.name,
            scheduled_time=appointment.scheduled_time,
            service_type=appointment.service_type,
            barbershop_address=barbershop.address or "N/A"
        )

        return self._send_email(
            to_email=client.email,
            subject=subject,
            body=body
        )

    def send_appointment_cancellation(
        self,
        appointment: Appointment,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send email when appointment is cancelled.

        Args:
            appointment: Appointment instance
            reason: Cancellation reason

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.email:
            return False

        subject = f"❌ Cita Cancelada - {barbershop.name}"

        body = self._get_cancellation_email_template(
            client_name=client.full_name,
            barbershop_name=barbershop.name,
            scheduled_time=appointment.scheduled_time,
            reason=reason or "No especificada"
        )

        return self._send_email(
            to_email=client.email,
            subject=subject,
            body=body
        )

    def send_appointment_completed(
        self,
        appointment: Appointment
    ) -> bool:
        """
        Send thank you email after appointment is completed.

        Args:
            appointment: Appointment instance

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barber = self.db.query(User).filter(User.id == appointment.barber_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.email:
            return False

        subject = f"¡Gracias! - {barbershop.name}"

        body = self._get_completion_email_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=barbershop.name
        )

        return self._send_email(
            to_email=client.email,
            subject=subject,
            body=body
        )

    # ==================== SMS / WHATSAPP NOTIFICATIONS ====================

    def send_whatsapp_confirmation(
        self,
        appointment: Appointment
    ) -> bool:
        """
        Send WhatsApp message for appointment confirmation.

        Uses Twilio WhatsApp API or similar provider.

        Args:
            appointment: Appointment instance

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barber = self.db.query(User).filter(User.id == appointment.barber_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.phone:
            return False

        message = self._get_whatsapp_confirmation_template(
            client_name=client.full_name,
            barber_name=barber.full_name,
            barbershop_name=barbershop.name,
            scheduled_time=appointment.scheduled_time,
            service_type=appointment.service_type,
            barbershop_address=barbershop.address or "N/A"
        )

        return self._send_whatsapp(
            phone=client.phone,
            message=message
        )

    def send_sms_reminder(
        self,
        appointment: Appointment
    ) -> bool:
        """
        Send SMS reminder for appointment.

        Uses Twilio SMS API or similar provider.

        Args:
            appointment: Appointment instance

        Returns:
            bool: True if sent successfully
        """
        client = self.db.query(User).filter(User.id == appointment.client_id).first()
        barbershop = self.db.query(Barbershop).filter(
            Barbershop.id == appointment.barbershop_id
        ).first()

        if not client or not client.phone:
            return False

        message = self._get_sms_reminder_template(
            barbershop_name=barbershop.name,
            scheduled_time=appointment.scheduled_time
        )

        return self._send_sms(
            phone=client.phone,
            message=message
        )

    # ==================== INTERNAL EMAIL SENDER ====================

    def _send_email(
        self,
        to_email: str,
        subject: str,
        body: str
    ) -> bool:
        """
        Internal method to send email via SMTP.

        Args:
            to_email: Recipient email
            subject: Email subject
            body: Email body (HTML)

        Returns:
            bool: True if sent successfully
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = settings.SMTP_FROM_EMAIL
            msg['To'] = to_email
            msg['Subject'] = subject

            # Attach HTML body
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)

            # Send via SMTP
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_TLS:
                    server.starttls()

                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

                server.send_message(msg)

            return True

        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def _send_whatsapp(self, phone: str, message: str) -> bool:
        """
        Send WhatsApp message via Baileys service (FREE & UNLIMITED).

        Uses local Baileys Node.js service running on port 3001.

        Args:
            phone: Phone number (with country code, e.g., +18095555555)
            message: Message text (supports WhatsApp formatting: *bold*, _italic_, ~strikethrough~)

        Returns:
            bool: True if sent successfully
        """
        try:
            import requests

            # Baileys service URL (local Node.js service)
            url = "http://localhost:3001/send"

            # Send request to Baileys service
            response = requests.post(
                url,
                json={
                    "phone": phone,
                    "message": message
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"✅ WhatsApp sent to {phone}")
                    return True
                else:
                    print(f"❌ WhatsApp error: {result.get('error')}")
                    return False
            else:
                print(f"❌ WhatsApp service error: {response.status_code}")
                return False

        except requests.exceptions.ConnectionError:
            print(f"⚠️  WhatsApp service not running. Start with: cd whatsapp-service && npm start")
            return False
        except Exception as e:
            print(f"❌ Error sending WhatsApp: {e}")
            return False

    def _send_sms(self, phone: str, message: str) -> bool:
        """
        Send SMS via Twilio or similar.

        Args:
            phone: Phone number (with country code)
            message: Message text

        Returns:
            bool: True if sent successfully
        """
        try:
            # TODO: Implement Twilio SMS API
            # from twilio.rest import Client
            # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            # message = client.messages.create(
            #     from_=settings.TWILIO_PHONE_NUMBER,
            #     to=phone,
            #     body=message
            # )

            print(f"SMS would be sent to {phone}: {message}")
            return True

        except Exception as e:
            print(f"Error sending SMS: {e}")
            return False

    # ==================== EMAIL TEMPLATES ====================

    def _get_confirmation_email_template(
        self,
        client_name: str,
        barber_name: str,
        barbershop_name: str,
        scheduled_time: datetime,
        service_type: str,
        estimated_duration: int,
        barbershop_address: str,
        barbershop_phone: str
    ) -> str:
        """Get HTML template for appointment confirmation email."""

        formatted_date = scheduled_time.strftime("%A, %d de %B de %Y")
        formatted_time = scheduled_time.strftime("%I:%M %p")

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .info-box {{ background: white; padding: 20px; margin: 20px 0; border-left: 4px solid #667eea; border-radius: 5px; }}
        .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👑 {barbershop_name}</h1>
            <h2>✅ Cita Confirmada</h2>
        </div>
        <div class="content">
            <p>Hola <strong>{client_name}</strong>,</p>

            <p>Tu cita ha sido confirmada exitosamente. ¡Esperamos verte pronto!</p>

            <div class="info-box">
                <h3>📅 Detalles de tu Cita:</h3>
                <p><strong>Fecha:</strong> {formatted_date}</p>
                <p><strong>Hora:</strong> {formatted_time}</p>
                <p><strong>Barbero:</strong> {barber_name}</p>
                <p><strong>Servicio:</strong> {service_type}</p>
                <p><strong>Duración estimada:</strong> {estimated_duration} minutos</p>
            </div>

            <div class="info-box">
                <h3>📍 Ubicación:</h3>
                <p><strong>{barbershop_name}</strong></p>
                <p>{barbershop_address}</p>
                <p>📞 {barbershop_phone}</p>
            </div>

            <p><strong>⏰ Importante:</strong> Por favor llega 5-10 minutos antes de tu cita.</p>

            <p>Si necesitas cancelar o reprogramar, contáctanos lo antes posible.</p>

            <div class="footer">
                <p>Gracias por confiar en {barbershop_name}</p>
                <p>Este es un email automático. Por favor no respondas a este mensaje.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    def _get_reminder_email_template(
        self,
        client_name: str,
        barber_name: str,
        barbershop_name: str,
        scheduled_time: datetime,
        service_type: str,
        barbershop_address: str
    ) -> str:
        """Get HTML template for appointment reminder email."""

        formatted_time = scheduled_time.strftime("%I:%M %p")
        formatted_date = scheduled_time.strftime("%A, %d de %B")

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .reminder-box {{ background: #fff3cd; padding: 20px; margin: 20px 0; border-left: 4px solid #f59e0b; border-radius: 5px; text-align: center; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⏰ Recordatorio de Cita</h1>
        </div>
        <div class="content">
            <p>Hola <strong>{client_name}</strong>,</p>

            <div class="reminder-box">
                <h2>Tu cita es MAÑANA</h2>
                <p style="font-size: 24px; margin: 10px 0;"><strong>{formatted_time}</strong></p>
                <p>{formatted_date}</p>
            </div>

            <p><strong>Barbero:</strong> {barber_name}</p>
            <p><strong>Servicio:</strong> {service_type}</p>
            <p><strong>Lugar:</strong> {barbershop_name}</p>
            <p>{barbershop_address}</p>

            <p>¡Te esperamos! 👋</p>

            <div class="footer">
                <p>{barbershop_name}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    def _get_cancellation_email_template(
        self,
        client_name: str,
        barbershop_name: str,
        scheduled_time: datetime,
        reason: str
    ) -> str:
        """Get HTML template for appointment cancellation email."""

        formatted_time = scheduled_time.strftime("%I:%M %p, %d de %B")

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #dc3545; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>❌ Cita Cancelada</h1>
        </div>
        <div class="content">
            <p>Hola <strong>{client_name}</strong>,</p>

            <p>Tu cita del <strong>{formatted_time}</strong> ha sido cancelada.</p>

            <p><strong>Motivo:</strong> {reason}</p>

            <p>Si deseas reagendar, contáctanos o reserva una nueva cita en nuestra app.</p>

            <p>¡Esperamos verte pronto!</p>

            <div class="footer">
                <p>{barbershop_name}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    def _get_completion_email_template(
        self,
        client_name: str,
        barber_name: str,
        barbershop_name: str
    ) -> str:
        """Get HTML template for appointment completion email."""

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
        .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✅ ¡Gracias por tu visita!</h1>
        </div>
        <div class="content">
            <p>Hola <strong>{client_name}</strong>,</p>

            <p>Esperamos que hayas disfrutado tu servicio con <strong>{barber_name}</strong>.</p>

            <p>Tu opinión es muy importante para nosotros. Si tienes un momento, nos encantaría que nos dejaras una reseña.</p>

            <p>¡Esperamos verte pronto para tu próxima cita!</p>

            <div class="footer">
                <p>Gracias por confiar en {barbershop_name}</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

    # ==================== SMS / WHATSAPP TEMPLATES ====================

    def _get_whatsapp_confirmation_template(
        self,
        client_name: str,
        barber_name: str,
        barbershop_name: str,
        scheduled_time: datetime,
        service_type: str,
        barbershop_address: str
    ) -> str:
        """Get WhatsApp message template for confirmation."""

        formatted_time = scheduled_time.strftime("%I:%M %p, %d de %B")

        return f"""
👑 *{barbershop_name}*

✅ *Cita Confirmada*

Hola {client_name},

📅 *Fecha y Hora:* {formatted_time}
✂️ *Servicio:* {service_type}
👤 *Barbero:* {barber_name}
📍 *Dirección:* {barbershop_address}

⏰ Por favor llega 5-10 minutos antes.

¡Te esperamos! 👋
"""

    def _get_sms_reminder_template(
        self,
        barbershop_name: str,
        scheduled_time: datetime
    ) -> str:
        """Get SMS message template for reminder."""

        formatted_time = scheduled_time.strftime("%I:%M %p")

        return f"""
⏰ Recordatorio: Tu cita en {barbershop_name} es MAÑANA a las {formatted_time}. ¡Te esperamos!
"""
