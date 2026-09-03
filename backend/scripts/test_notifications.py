#!/usr/bin/env python3
"""
Script de prueba para el sistema de notificaciones
Permite probar emails sin configurar SMTP real
"""

from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_email_preview(subject: str, body: str):
    """Print email preview in console."""
    print("\n" + "="*70)
    print(f"📧 EMAIL PREVIEW")
    print("="*70)
    print(f"Subject: {subject}")
    print("-"*70)
    print(body[:500] + "..." if len(body) > 500 else body)
    print("="*70 + "\n")


def test_confirmation_email():
    """Test confirmation email template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)  # No DB needed for template test

    html = service._get_confirmation_email_template(
        client_name="Juan Pérez",
        barber_name="Carlos Martínez",
        barbershop_name="Elite Barber Shop",
        scheduled_time=datetime.now() + timedelta(days=1),
        service_type="Corte + Barba Premium",
        estimated_duration=30,
        barbershop_address="Calle Principal #123, Santo Domingo",
        barbershop_phone="809-555-5555"
    )

    print_email_preview(
        subject="✅ Cita Confirmada - Elite Barber Shop",
        body=html
    )

    # Save to file for browser preview
    with open("preview_confirmation.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Email de confirmación guardado en: preview_confirmation.html")
    print("   Abre este archivo en tu navegador para ver el diseño completo")


def test_reminder_email():
    """Test reminder email template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)

    html = service._get_reminder_email_template(
        client_name="Juan Pérez",
        barber_name="Carlos Martínez",
        barbershop_name="Elite Barber Shop",
        scheduled_time=datetime.now() + timedelta(days=1),
        service_type="Corte + Barba Premium",
        barbershop_address="Calle Principal #123, Santo Domingo"
    )

    print_email_preview(
        subject="⏰ Recordatorio de Cita - Elite Barber Shop",
        body=html
    )

    with open("preview_reminder.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Email de recordatorio guardado en: preview_reminder.html")


def test_cancellation_email():
    """Test cancellation email template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)

    html = service._get_cancellation_email_template(
        client_name="Juan Pérez",
        barbershop_name="Elite Barber Shop",
        scheduled_time=datetime.now() + timedelta(days=1),
        reason="Cliente solicitó reprogramar"
    )

    print_email_preview(
        subject="❌ Cita Cancelada - Elite Barber Shop",
        body=html
    )

    with open("preview_cancellation.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Email de cancelación guardado en: preview_cancellation.html")


def test_completion_email():
    """Test completion email template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)

    html = service._get_completion_email_template(
        client_name="Juan Pérez",
        barber_name="Carlos Martínez",
        barbershop_name="Elite Barber Shop"
    )

    print_email_preview(
        subject="¡Gracias! - Elite Barber Shop",
        body=html
    )

    with open("preview_completion.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Email de agradecimiento guardado en: preview_completion.html")


def test_whatsapp_template():
    """Test WhatsApp message template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)

    message = service._get_whatsapp_confirmation_template(
        client_name="Juan Pérez",
        barber_name="Carlos Martínez",
        barbershop_name="Elite Barber Shop",
        scheduled_time=datetime.now() + timedelta(days=1),
        service_type="Corte + Barba Premium",
        barbershop_address="Calle Principal #123, Santo Domingo"
    )

    print("\n" + "="*70)
    print(f"💬 WHATSAPP MESSAGE PREVIEW")
    print("="*70)
    print(message)
    print("="*70 + "\n")


def test_sms_template():
    """Test SMS message template."""
    from app.services.notification_service import NotificationService

    service = NotificationService(None)

    message = service._get_sms_reminder_template(
        barbershop_name="Elite Barber Shop",
        scheduled_time=datetime.now() + timedelta(days=1)
    )

    print("\n" + "="*70)
    print(f"📱 SMS MESSAGE PREVIEW")
    print("="*70)
    print(message)
    print(f"Caracteres: {len(message)}/160")
    print("="*70 + "\n")


def main():
    """Run all notification tests."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║     🧪 PRUEBA DE SISTEMA DE NOTIFICACIONES 🧪            ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print("\n")

    try:
        print("📧 Probando templates de EMAIL...")
        test_confirmation_email()
        test_reminder_email()
        test_cancellation_email()
        test_completion_email()

        print("\n💬 Probando templates de WHATSAPP...")
        test_whatsapp_template()

        print("\n📱 Probando templates de SMS...")
        test_sms_template()

        print("\n✅ ¡Todas las pruebas completadas!")
        print("\n📁 Archivos HTML generados:")
        print("   - preview_confirmation.html")
        print("   - preview_reminder.html")
        print("   - preview_cancellation.html")
        print("   - preview_completion.html")
        print("\n🌐 Abre estos archivos en tu navegador para ver el diseño completo\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
