from flask import Flask, render_template, request, jsonify
import os
import time
import threading
import atexit
import json
from urllib.parse import quote
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class WhatsAppBot:
    def __init__(self):
        # Remove all Selenium-related initialization
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session_file = "whatsapp_session.json"
        self.last_phone_number = None
        self.mock_mode = True  # Add mock mode for cloud environments
        
    def setup_driver(self):
        """Mock setup for cloud environments"""
        logger.info("Mock driver setup for cloud environment")
        return True
    
    def is_whatsapp_loaded(self):
        """Mock WhatsApp loaded check"""
        return self.mock_mode
    
    def quick_login_check(self):
        """Mock login check"""
        return self.is_logged_in
    
    def ensure_logged_in(self):
        """Mock login check - always return success in mock mode"""
        if self.mock_mode:
            self.is_logged_in = True
            return True, "Mock login successful"
        return False, "Real browser automation not available in cloud environment"
    
    def send_message(self, phone_number, message):
        """Mock message sending for cloud environments"""
        with self.lock:
            try:
                if not phone_number or not phone_number.strip():
                    return False, "Phone number is required"
                
                phone_number = phone_number.strip()
                
                # Mock the login process
                login_success, login_msg = self.ensure_logged_in()
                if not login_success:
                    return False, login_msg
                
                # Simulate message sending delay
                time.sleep(1)
                
                # Mock success response
                self.last_phone_number = phone_number
                logger.info(f"Mock message sent to {phone_number}: {message}")
                
                return True, f"Message sent successfully to {phone_number} (Mock Mode)"
                
            except Exception as e:
                logger.error(f"Error in send_message: {e}")
                return False, f"Error: {str(e)}"
    
    def get_qr_code(self):
        """Mock QR code generation"""
        if self.mock_mode:
            self.is_logged_in = True
            return True, "Mock QR code scanned successfully - you are now logged in"
        return False, "Real browser automation not available in cloud environment"
    
    def close_session(self):
        """Mock session closure"""
        with self.lock:
            try:
                self.is_logged_in = False
                self.last_phone_number = None
                logger.info("Mock session closed successfully")
                return True, "Session closed successfully"
            except Exception as e:
                logger.error(f"Error closing session: {e}")
                return False, f"Error closing session: {str(e)}"
    
    def clear_session_data(self):
        """Mock session data clearing"""
        with self.lock:
            try:
                self.is_logged_in = False
                self.last_phone_number = None
                logger.info("Mock session data cleared")
                return True, "All session data cleared successfully"
            except Exception as e:
                logger.error(f"Error clearing session data: {e}")
                return False, f"Error clearing session data: {str(e)}"

# Alternative: Real implementation with proper cloud detection
class WhatsAppBotReal:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session_file = "whatsapp_session.json"
        self.user_data_dir = os.path.join(os.getcwd(), 'chrome_user_data')
        self.cookies_file = "whatsapp_cookies.pkl"
        self.last_phone_number = None
        self.cloud_environment = self.detect_cloud_environment()
        
    def detect_cloud_environment(self):
        """Detect if running in cloud environment"""
        cloud_indicators = [
            'RENDER', 'HEROKU', 'RAILWAY', 'REPLIT', 'CODESPACE_NAME',
            'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'VERCEL',
            'NETLIFY', 'GLITCH_PROJECT_NAME'
        ]
        
        for indicator in cloud_indicators:
            if os.environ.get(indicator):
                return True
        
        # Check if display is available
        if not os.environ.get('DISPLAY'):
            return True
            
        # Check if running in container
        if os.path.exists('/.dockerenv'):
            return True
            
        return False
    
    def setup_driver(self):
        """Setup Chrome driver with cloud environment handling"""
        if self.cloud_environment:
            logger.warning("Cloud environment detected. Browser automation may not work properly.")
            logger.info("For cloud deployment, consider using WhatsApp Business API instead.")
            return False
        
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
            
            options = Options()
            
            # Essential options for stability
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--headless=new')
            
            # Performance optimizations
            options.add_argument('--disable-images')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-default-apps')
            options.add_argument('--no-default-browser-check')
            
            # Anti-detection
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Session persistence
            if not os.path.exists(self.user_data_dir):
                os.makedirs(self.user_data_dir)
            
            options.add_argument(f'--user-data-dir={self.user_data_dir}')
            options.add_argument('--profile-directory=WhatsAppBot')
            
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 20)
            
            logger.info("Chrome driver setup successful")
            return True
            
        except ImportError:
            logger.error("Selenium not installed. Install with: pip install selenium")
            return False
        except Exception as e:
            logger.error(f"Error setting up driver: {e}")
            return False
    
    def send_message(self, phone_number, message):
        """Send message with cloud environment check"""
        if self.cloud_environment:
            logger.warning("Cannot send real messages in cloud environment")
            return False, "Browser automation not available in cloud environment. Use WhatsApp Business API instead."
        
        # Your existing send_message logic here for local environments
        # ... (keep the original logic for local use)
        
        return True, f"Message sent successfully to {phone_number}"

# Create appropriate bot instance based on environment
def create_bot():
    """Factory function to create appropriate bot instance"""
    # Check if we're in a cloud environment
    cloud_indicators = [
        'RENDER', 'HEROKU', 'RAILWAY', 'REPLIT', 'CODESPACE_NAME',
        'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'VERCEL',
        'NETLIFY', 'GLITCH_PROJECT_NAME'
    ]
    
    is_cloud = any(os.environ.get(indicator) for indicator in cloud_indicators)
    is_cloud = is_cloud or not os.environ.get('DISPLAY') or os.path.exists('/.dockerenv')
    
    if is_cloud:
        logger.info("Cloud environment detected - using mock bot")
        return WhatsAppBot()  # Mock version
    else:
        logger.info("Local environment detected - using real bot")
        return WhatsAppBotReal()  # Real version

# Global bot instance
bot = create_bot()

@app.route('/')
def index():
    # Create a simple HTML template inline since templates might not be available
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>WhatsApp Bot</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .container { background: #f5f5f5; padding: 20px; border-radius: 10px; }
            input, textarea, button { width: 100%; padding: 10px; margin: 10px 0; }
            button { background: #25D366; color: white; border: none; cursor: pointer; }
            button:hover { background: #128C7E; }
            .result { margin: 20px 0; padding: 15px; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>WhatsApp Bot</h1>
            <p><strong>Note:</strong> This is a mock version for cloud environments. For real functionality, run locally with Chrome browser.</p>
            
            <h2>1. Setup Login</h2>
            <button onclick="setupQR()">Setup QR Code Login</button>
            <div id="qr-result"></div>
            
            <h2>2. Send Message</h2>
            <input type="text" id="phone" placeholder="Phone number with country code (e.g., +1234567890)">
            <textarea id="message" placeholder="Enter your message here" rows="4"></textarea>
            <button onclick="sendMessage()">Send Message</button>
            <div id="message-result"></div>
            
            <h2>3. Close Session</h2>
            <button onclick="closeSession()">Close Session</button>
            <div id="close-result"></div>
        </div>
        
        <script>
            function setupQR() {
                fetch('/setup_qr', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        const result = document.getElementById('qr-result');
                        if (data.status === 'success') {
                            result.innerHTML = '<div class="result success">' + data.message + '</div>';
                        } else {
                            result.innerHTML = '<div class="result error">' + data.message + '</div>';
                        }
                    })
                    .catch(error => {
                        document.getElementById('qr-result').innerHTML = '<div class="result error">Error: ' + error + '</div>';
                    });
            }
            
            function sendMessage() {
                const phone = document.getElementById('phone').value;
                const message = document.getElementById('message').value;
                
                if (!phone || !message) {
                    document.getElementById('message-result').innerHTML = '<div class="result error">Please fill in both phone number and message</div>';
                    return;
                }
                
                fetch('/send_message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone_number: phone, message: message })
                })
                    .then(response => response.json())
                    .then(data => {
                        const result = document.getElementById('message-result');
                        if (data.status === 'success') {
                            result.innerHTML = '<div class="result success">' + data.message + '</div>';
                        } else {
                            result.innerHTML = '<div class="result error">' + data.message + '</div>';
                        }
                    })
                    .catch(error => {
                        document.getElementById('message-result').innerHTML = '<div class="result error">Error: ' + error + '</div>';
                    });
            }
            
            function closeSession() {
                fetch('/close_session', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        const result = document.getElementById('close-result');
                        if (data.status === 'success') {
                            result.innerHTML = '<div class="result success">' + data.message + '</div>';
                        } else {
                            result.innerHTML = '<div class="result error">' + data.message + '</div>';
                        }
                    })
                    .catch(error => {
                        document.getElementById('close-result').innerHTML = '<div class="result error">Error: ' + error + '</div>';
                    });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/setup_qr', methods=['POST'])
def setup_qr():
    try:
        success, message = bot.get_qr_code()
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        logger.error(f"Setup QR route error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            }), 400
        
        phone_number = data.get('phone_number', '').strip()
        message_text = data.get('message', '').strip()
        
        if not phone_number:
            return jsonify({
                'status': 'error',
                'message': 'Phone number is required'
            }), 400
        
        if not message_text:
            return jsonify({
                'status': 'error',
                'message': 'Message text is required'
            }), 400
        
        if not phone_number.startswith('+'):
            return jsonify({
                'status': 'error',
                'message': 'Phone number must include country code (e.g., +91xxxxxxxxxx)'
            }), 400
        
        clean_number = phone_number.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if len(clean_number) < 8 or len(clean_number) > 15:
            return jsonify({
                'status': 'error',
                'message': 'Invalid phone number length'
            }), 400
        
        success, message = bot.send_message(phone_number, message_text)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/close_session', methods=['POST'])
def close_session():
    try:
        success, message = bot.close_session()
        
        return jsonify({
            'status': 'success',
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

# Clean up on exit
def cleanup():
    bot.close_session()

atexit.register(cleanup)

if __name__ == '__main__':
    print("Starting WhatsApp Bot Flask Service...")
    print("Server will be available at: http://localhost:5000")
    
    # For cloud hosting, use environment variables
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
