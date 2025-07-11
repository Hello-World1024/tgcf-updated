#!/usr/bin/env python3
"""
Simple health check script that adds a health endpoint to Streamlit
"""
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            health_data = {
                "status": "healthy",
                "timestamp": time.time(),
                "service": "tgcf-streamlit"
            }
            
            self.wfile.write(json.dumps(health_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging

def start_health_server():
    """Start health check server on a separate thread"""
    server = HTTPServer(('0.0.0.0', 8081), HealthHandler)
    server.serve_forever()

def main():
    """Start health server in background"""
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    # Keep the main thread alive
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
