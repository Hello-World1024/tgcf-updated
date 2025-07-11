#!/usr/bin/env python3
"""
Simple health check server for Render deployment.
Runs on port 8080 alongside Streamlit to provide health endpoint.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import logging
import time
from datetime import datetime

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            health_data = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "tgcf",
                "uptime": time.time() - start_time
            }
            
            self.wfile.write(json.dumps(health_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def start_health_server(port=8081):
    """Start the health check server."""
    global start_time
    start_time = time.time()
    
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logging.info(f"🏥 Health server started on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_health_server()
