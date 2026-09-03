#!/usr/bin/env python3
"""
Simple HTTP server to serve the frontend
"""
import http.server
import socketserver
import os

PORT = 3000
DIRECTORY = "../frontend"

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        print(f"")
        print(f"🌐 ===============================================")
        print(f"   KingFlow Barber - Frontend Server")
        print(f"🌐 ===============================================")
        print(f"")
        print(f"📍 Frontend: http://localhost:{PORT}")
        print(f"📍 API:      http://localhost:8000")
        print(f"📚 Docs:     http://localhost:8000/docs")
        print(f"")
        print(f"✅ Servidor frontend corriendo...")
        print(f"   Presiona Ctrl+C para detener")
        print(f"")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Servidor detenido")
