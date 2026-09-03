#!/usr/bin/env python3
"""
KingFlow Barber - Startup Script
Inicia backend (FastAPI) y frontend (HTTP server) simultáneamente
"""

import subprocess
import sys
import os
import time
import webbrowser

def print_banner():
    print("""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          👑  KINGFLOW BARBER - STARTUP MANAGER  👑         ║
║                                                            ║
║         Sistema Operativo para Barberías                   ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

def check_mysql():
    """Verifica que MySQL esté corriendo"""
    print("🔍 Verificando MySQL...")
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='kingflow',
            password='kingflow123',
            database='kingflow_barber'
        )
        conn.close()
        print("✅ MySQL está corriendo correctamente")
        return True
    except Exception as e:
        print(f"❌ Error con MySQL: {e}")
        print("⚠️  Asegúrate de que MySQL esté corriendo en Laragon")
        return False

def start_backend():
    """Inicia el servidor FastAPI"""
    print("\n🚀 Iniciando Backend API...")

    backend_cmd = [
        sys.executable,
        "-m", "uvicorn",
        "app.main:app",
        "--reload",
        "--host", "127.0.0.1",
        "--port", "8000"
    ]

    process = subprocess.Popen(
        backend_cmd,
        cwd=os.path.join(os.path.dirname(__file__), '..'),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    print("✅ Backend iniciado en http://127.0.0.1:8000")
    print("📚 Documentación: http://127.0.0.1:8000/docs")

    return process

def start_frontend():
    """Inicia el servidor del frontend"""
    print("\n🌐 Iniciando Frontend Server...")

    frontend_script = os.path.join(os.path.dirname(__file__), 'serve_frontend.py')

    process = subprocess.Popen(
        [sys.executable, frontend_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    print("✅ Frontend iniciado en http://localhost:3000")

    return process

def open_browsers():
    """Abre los navegadores después de un delay"""
    print("\n⏳ Esperando que los servidores se inicien...")
    time.sleep(3)

    print("\n🌐 Abriendo navegadores...")
    webbrowser.open('http://localhost:3000')
    time.sleep(1)
    webbrowser.open('http://127.0.0.1:8000/docs')

def main():
    print_banner()

    # Verificar MySQL
    if not check_mysql():
        print("\n⚠️  Por favor inicia MySQL en Laragon y vuelve a ejecutar este script")
        sys.exit(1)

    print("\n" + "="*60)
    print("  Iniciando KingFlow Barber...")
    print("="*60)

    try:
        # Iniciar backend
        backend_process = start_backend()
        time.sleep(2)

        # Iniciar frontend
        frontend_process = start_frontend()
        time.sleep(1)

        # Abrir navegadores
        open_browsers()

        print("\n" + "="*60)
        print("  ✅ SISTEMA COMPLETAMENTE OPERACIONAL")
        print("="*60)
        print("\n📍 URLs Disponibles:")
        print("   • Frontend:      http://localhost:3000")
        print("   • Backend API:   http://127.0.0.1:8000")
        print("   • API Docs:      http://127.0.0.1:8000/docs")
        print("\n🔐 Credenciales de prueba:")
        print("   • Email:     admin@test.com")
        print("   • Password:  admin123")
        print("\n💡 Presiona Ctrl+C para detener todos los servicios")
        print("="*60)

        # Mantener vivo
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n🛑 Deteniendo servicios...")
            backend_process.terminate()
            frontend_process.terminate()
            print("👋 KingFlow Barber detenido. ¡Hasta pronto!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
