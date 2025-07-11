#!/usr/bin/env python3
"""
Keep-alive script for Render free tier to prevent spin down.
This script pings your own service periodically to keep it awake.
"""

import requests
import time
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Your Render service URL (replace with your actual URL)
SERVICE_URL = os.getenv('SERVICE_URL', 'http://localhost:8080')
PING_INTERVAL = 14 * 60  # 14 minutes (before 15-minute timeout)

def ping_service():
    """Ping the service to keep it alive."""
    try:
        response = requests.get(f"{SERVICE_URL}/health", timeout=10)
        if response.status_code == 200:
            logging.info(f"✅ Ping successful - Service is alive")
            return True
        else:
            logging.warning(f"⚠️ Ping returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Ping failed: {e}")
        return False

def main():
    """Main keep-alive loop."""
    logging.info(f"🚀 Starting keep-alive service for {SERVICE_URL}")
    logging.info(f"⏰ Ping interval: {PING_INTERVAL} seconds")
    
    while True:
        try:
            ping_service()
            time.sleep(PING_INTERVAL)
        except KeyboardInterrupt:
            logging.info("🛑 Keep-alive service stopped by user")
            break
        except Exception as e:
            logging.error(f"💥 Unexpected error: {e}")
            time.sleep(60)  # Wait 1 minute before retrying

if __name__ == "__main__":
    main()
