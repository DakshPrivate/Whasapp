from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
import time
import urllib.parse
import os
import threading
from datetime import datetime
import json
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Global variables to track sending status
sending_status = {
    'is_sending': False,
    'status_message': 'Ready to send message',
    'last_sent': None,
    'current_session_id': None,
    'progress': 0
}

# Store session data
active_sessions = {}

def setup_chrome_driver():
    """Setup Chrome driver for Render deployment"""
    chrome_options = Options()
    
    # Essential options for Render
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-ipc-flooding-protection")
    
    # Headless mode (required for Render)
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Memory optimizations
    chrome_options.add_argument("--memory-pressure-off")
    chrome_options.add_argument("--max_old_space_size=4096")
    
    # Disable automation detection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Use webdriver-manager for Chrome installation
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    
    service = Service(ChromeDriverManager().install())
    
    return webdriver.Chrome(service=service, options=chrome_options)

def update_session_status(session_id, status, progress=0, success=None, error=None):
    """Update session status"""
    if session_id in active_sessions:
        active_sessions[session_id].update({
            'status': status,
            'progress': progress,
            'timestamp': datetime.now().isoformat(),
            'success': success,
            'error': error
        })
    
    # Update global status
    global sending_status
    sending_status.update({
        'status_message': status,
        'progress': progress,
        'current_session_id': session_id
    })

def send_whatsapp_message_background(phone_number, message, session_id):
    """Background function to send WhatsApp message"""
    global sending_status
    driver = None
    
    try:
        sending_status['is_sending'] = True
        update_session_status(session_id, 'Initializing...', 10)
        
        # Setup Chrome driver
        driver = setup_chrome_driver()
        update_session_status(session_id, 'Chrome driver setup complete', 20)
        
        # Open WhatsApp Web
        driver.get("https://web.whatsapp.com")
        update_session_status(session_id, 'Opening WhatsApp Web...', 30)
        
        # Wait for WhatsApp Web to load
        wait = WebDriverWait(driver, 60)
        
        try:
            # Wait for the search box to be present (indicates WhatsApp is loaded)
            search_box = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true'][@data-tab='3']")))
            update_session_status(session_id, 'WhatsApp Web loaded successfully', 50)
        except Exception as e:
            update_session_status(session_id, 'WhatsApp Web not loaded. Please scan QR code first.', 30, 
                                success=False, error='WhatsApp Web authentication required')
            return False, "WhatsApp Web not loaded. Please scan QR code first."
        
        time.sleep(2)
        
        # Create WhatsApp message URL with phone number and message
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://web.whatsapp.com/send?phone={phone_number}&text={encoded_message}"
        
        update_session_status(session_id, 'Opening chat...', 60)
        
        # Navigate to the specific chat
        driver.get(whatsapp_url)
        
        # Wait for the message input box to be present
        update_session_status(session_id, 'Waiting for message input...', 70)
        
        try:
            message_input = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true'][@data-tab='10']")))
        except Exception as e:
            # Try alternative selectors
            try:
                message_input = wait.until(EC.presence_of_element_located((By.XPATH, "//div[@contenteditable='true'][@data-lexical-editor='true']")))
            except Exception as e2:
                update_session_status(session_id, 'Message input not found', 70, 
                                    success=False, error='Could not find message input box')
                return False, "Could not find message input box"
        
        # Click on the message input box
        message_input.click()
        time.sleep(1)
        
        update_session_status(session_id, 'Sending message...', 80)
        
        # Send the message by pressing Enter
        message_input.send_keys(Keys.ENTER)
        
        # Wait a bit to ensure message is sent
        time.sleep(3)
        
        update_session_status(session_id, 'Message sent successfully!', 100, 
                            success=True, error=None)
        sending_status['last_sent'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return True, "Message sent successfully!"
        
    except Exception as e:
        error_msg = f"Error occurred: {str(e)}"
        update_session_status(session_id, f'Error: {str(e)}', 0, 
                            success=False, error=error_msg)
        return False, error_msg
        
    finally:
        # Clean up
        if driver:
            driver.quit()
        sending_status['is_sending'] = False
        
        # Clean up session after 5 minutes
        def cleanup_session():
            time.sleep(300)  # 5 minutes
            if session_id in active_sessions:
                del active_sessions[session_id]
        
        threading.Thread(target=cleanup_session, daemon=True).start()

# API Routes for Kotlin App
@app.route('/api/send-message', methods=['POST'])
def api_send_message():
    """API endpoint to send WhatsApp message from Kotlin app"""
    try:
        # Get JSON data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided',
                'session_id': None
            }), 400
        
        phone_number = data.get('phone_number', '').strip()
        message = data.get('message', '').strip()
        
        # Validate inputs
        if not phone_number or not message:
            return jsonify({
                'success': False,
                'error': 'Phone number and message are required',
                'session_id': None
            }), 400
        
        # Check if already sending
        if sending_status['is_sending']:
            return jsonify({
                'success': False,
                'error': 'Another message is currently being sent. Please wait.',
                'session_id': None
            }), 429
        
        # Create session ID
        session_id = str(uuid.uuid4())
        
        # Store session data
        active_sessions[session_id] = {
            'phone_number': phone_number,
            'message': message,
            'status': 'Started',
            'progress': 0,
            'timestamp': datetime.now().isoformat(),
            'success': None,
            'error': None
        }
        
        # Start sending in background thread
        thread = threading.Thread(
            target=send_whatsapp_message_background,
            args=(phone_number, message, session_id),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Message sending started',
            'session_id': session_id,
            'status': 'started'
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}',
            'session_id': None
        }), 500

@app.route('/api/status/<session_id>', methods=['GET'])
def api_get_status(session_id):
    """API endpoint to get message sending status"""
    try:
        if session_id not in active_sessions:
            return jsonify({
                'success': False,
                'error': 'Session not found',
                'session_id': session_id
            }), 404
        
        session_data = active_sessions[session_id]
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'phone_number': session_data['phone_number'],
            'message': session_data['message'],
            'status': session_data['status'],
            'progress': session_data['progress'],
            'timestamp': session_data['timestamp'],
            'is_complete': session_data['success'] is not None,
            'is_success': session_data['success'],
            'error': session_data['error']
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}',
            'session_id': session_id
        }), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'is_sending': sending_status['is_sending']
    }), 200

# Web Interface Routes (keeping existing functionality)
@app.route('/')
def index():
    """Main page with the form"""
    return render_template('index.html')

@app.route('/send', methods=['POST'])
def send_message():
    """Handle message sending request from web interface"""
    try:
        # Get form data
        phone_number = request.form.get('phone_number', '').strip()
        message = request.form.get('message', '').strip()
        
        # Validate inputs
        if not phone_number or not message:
            return jsonify({
                'success': False,
                'error': 'Please enter both phone number and message'
            })
        
        # Check if already sending
        if sending_status['is_sending']:
            return jsonify({
                'success': False,
                'error': 'Another message is currently being sent. Please wait.'
            })
        
        # Create session ID
        session_id = str(uuid.uuid4())
        
        # Store session data
        active_sessions[session_id] = {
            'phone_number': phone_number,
            'message': message,
            'status': 'Started',
            'progress': 0,
            'timestamp': datetime.now().isoformat(),
            'success': None,
            'error': None
        }
        
        # Start sending in background thread
        thread = threading.Thread(
            target=send_whatsapp_message_background,
            args=(phone_number, message, session_id),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Message sending started. Please wait...',
            'session_id': session_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        })

@app.route('/status')
def get_status():
    """Get current sending status for web interface"""
    return jsonify(sending_status)

@app.route('/setup')
def setup_page():
    """Setup page with instructions"""
    return render_template('setup.html')

# Error Handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Create the HTML template files (keeping existing templates)
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Message Sender</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #25D366, #128C7E);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 100%;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .header h1 {
            color: #25D366;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            color: #666;
            font-size: 1.1em;
        }
        
        .api-info {
            background: #f0f8ff;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #25D366;
        }
        
        .api-info h3 {
            color: #25D366;
            margin-bottom: 10px;
        }
        
        .api-info code {
            background: #e8e8e8;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 600;
        }
        
        input[type="text"], textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
            transition: border-color 0.3s ease;
        }
        
        input[type="text"]:focus, textarea:focus {
            outline: none;
            border-color: #25D366;
        }
        
        textarea {
            height: 100px;
            resize: vertical;
        }
        
        .send-btn {
            width: 100%;
            padding: 15px;
            background: #25D366;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .send-btn:hover {
            background: #128C7E;
        }
        
        .send-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            font-weight: 600;
        }
        
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .status.info {
            background: #cce7ff;
            color: #004085;
            border: 1px solid #b8daff;
        }
        
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e0e0e0;
            border-radius: 10px;
            overflow: hidden;
            margin-top: 10px;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #25D366, #128C7E);
            transition: width 0.3s ease;
        }
        
        .loading {
            display: none;
            text-align: center;
            margin-top: 20px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #25D366;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .setup-link {
            text-align: center;
            margin-top: 20px;
        }
        
        .setup-link a {
            color: #25D366;
            text-decoration: none;
            font-weight: 600;
        }
        
        .setup-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📱 WhatsApp Sender</h1>
            <p>Send messages instantly via WhatsApp Web</p>
        </div>
        
        <div class="api-info">
            <h3>🔗 API Endpoints</h3>
            <p><strong>Send Message:</strong> <code>POST /api/send-message</code></p>
            <p><strong>Check Status:</strong> <code>GET /api/status/{session_id}</code></p>
            <p><strong>Health Check:</strong> <code>GET /api/health</code></p>
        </div>
        
        <form id="messageForm">
            <div class="form-group">
                <label for="phone_number">Phone Number (with country code):</label>
                <input type="text" id="phone_number" name="phone_number" 
                       placeholder="+911234567890" value="+911234567890" required>
            </div>
            
            <div class="form-group">
                <label for="message">Message:</label>
                <textarea id="message" name="message" 
                          placeholder="Enter your message here..." required>Hello from my bot!</textarea>
            </div>
            
            <button type="submit" class="send-btn" id="sendBtn">Send Message</button>
        </form>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Sending message...</p>
        </div>
        
        <div id="status" class="status" style="display: none;">
            <div id="statusText"></div>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill" style="width: 0%"></div>
            </div>
        </div>
        
        <div class="setup-link">
            <a href="/setup">Need help with setup?</a>
        </div>
    </div>

    <script>
        let currentSessionId = null;
        
        const form = document.getElementById('messageForm');
        const sendBtn = document.getElementById('sendBtn');
        const loading = document.getElementById('loading');
        const statusDiv = document.getElementById('status');
        const statusText = document.getElementById('statusText');
        const progressFill = document.getElementById('progressFill');
        
        // Check status periodically
        function checkStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    if (data.is_sending) {
                        sendBtn.disabled = true;
                        sendBtn.textContent = 'Sending...';
                        loading.style.display = 'block';
                        showStatus(data.status_message, 'info', data.progress || 0);
                    } else {
                        sendBtn.disabled = false;
                        sendBtn.textContent = 'Send Message';
                        loading.style.display = 'none';
                        
                        if (data.status_message.includes('successfully')) {
                            showStatus(data.status_message, 'success', 100);
                        } else if (data.status_message.includes('Error')) {
                            showStatus(data.status_message, 'error', 0);
                        } else if (data.status_message !== 'Ready to send message') {
                            showStatus(data.status_message, 'info', data.progress || 0);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error checking status:', error);
                });
        }
        
        function showStatus(message, type, progress = 0) {
            statusText.textContent = message;
            statusDiv.className = `status ${type}`;
            statusDiv.style.display = 'block';
            progressFill.style.width = `${progress}%`;
        }
        
        // Check status every 2 seconds
        setInterval(checkStatus, 2000);
        
        // Handle form submission
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(form);
            
            fetch('/send', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    currentSessionId = data.session_id;
                    showStatus(data.message, 'info', 0);
                } else {
                    showStatus(data.error, 'error', 0);
                }
            })
            .catch(error => {
                showStatus('Network error occurred', 'error', 0);
            });
        });
        
        // Initial status check
        checkStatus();
    </script>
</body>
</html>''')
    
    # Create setup template
    with open('templates/setup.html', 'w', encoding='utf-8') as f:
        f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setup - WhatsApp Message Sender</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #25D366, #128C7E);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            max-width: 1000px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .header h1 {
            color: #25D366;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .setup-content {
            line-height: 1.6;
            color: #333;
        }
        
        .step {
            margin-bottom: 30px;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 10px;
            border-left: 4px solid #25D366;
        }
        
        .step h3 {
            color: #25D366;
            margin-bottom: 10px;
        }
        
        .api-section {
            background: #f0f8ff;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid #25D366;
        }
        
        .api-section h3 {
            color: #25D366;
            margin-bottom: 15px;
        }
        
        .code {
            background: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            margin: 10px 0;
            overflow-x: auto;
        }
        
        .json-example {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            overflow-x: auto;
        }
        
        .back-link {
            text-align: center;
            margin-top: 30px;
        }
        
        .back-link a {
            color: #25D366;
            text-decoration: none;
            font-weight: 600;
            font-size: 18px;
        }
        
        .back-link a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔧 Setup Instructions</h1>
            <p>Complete setup guide for WhatsApp API Server</p>
        </div>
        
        <div class="setup-content">
            <div class="step">
                <h3>Step 1: Install Required Dependencies</h3>
                <p>Install the required Python packages:</p>
                <div class="code">pip install flask flask-cors selenium</div>
            </div>
            
            <div class="step">
                <h3>Step 2: Install ChromeDriver</h3>
                <p>Download ChromeDriver from <a href="https://chromedriver.chromium.org/" target="_blank">https://chromedriver.chromium.org/</a> and add it to your PATH, or install via:</p>
                <div class="code">pip install chromedriver-autoinstaller</div>
            </div>
            
            <div class="step">
                <h3>Step 3: First Time Setup</h3>
                <p>On your first run, you'll need to:</p>
                <ul>
                    <li>Run the Flask app</li>
                    <li>Try to send a message (it will open Chrome)</li>
                    <li>Scan the QR code in WhatsApp Web</li>
                    <li>After that, all subsequent runs will be in headless mode</li>
                </ul>
            </div>
            
            <div class="api-section">
                <h3>📡 API Endpoints for Kotlin App</h3>
                
                <h4>1. Send Message</h4>
                <div class="code">POST http://your-server-ip:5000/api/send-message</div>
                <p><strong>Request Body (JSON):</strong></p>
                <div class="json-example">{
    "phone_number": "+911234567890",
    "message": "Hello from my Kotlin app!"
}</div>
                <p><strong>Response:</strong></p>
                <div class="json-example">{
    "success": true,
    "message": "Message sending started",
    "session_id": "uuid-here",
    "status": "started"
}</div>
                
                <h4>2. Check Status</h4>
                <div class="code">GET http://your-server-ip:5000/api/status/{session_id}</div>
                <p><strong>Response:</strong></p>
                <div class="json-example">{
    "success": true,
    "session_id": "uuid-here",
    "phone_number": "+911234567890",
    "message": "Hello from my Kotlin app!",
    "status": "Message sent successfully!",
    "progress": 100,
    "timestamp": "2024-01-01T12:00:00",
    "is_complete": true,
    "is_success": true,
    "error": null
}</div>
                
                <h4>3. Health Check</h4>
                <div class="code">GET http://your-server-ip:5000/api/health</div>
                <p><strong>Response:</strong></p>
                <div class="json-example">{
    "success": true,
    "status": "healthy",
    "timestamp": "2024-01-01T12:00:00",
    "is_sending": false
}</div>
            </div>
            
            <div class="step">
                <h3>Step 4: Run the Application</h3>
                <p>Save the code as <code>app.py</code> and run:</p>
                <div class="code">python app.py</div>
                <p>The server will start on <code>http://0.0.0.0:5000</code></p>
            </div>
            
            <div class="step">
                <h3>Step 5: Kotlin App Integration</h3>
                <p>In your Kotlin app, you can use libraries like Retrofit or OkHttp to make API calls:</p>
                <div class="code">
// Example using Retrofit
val retrofit = Retrofit.Builder()
    .baseUrl("http://your-server-ip:5000/")
    .addConverterFactory(GsonConverterFactory.create())
    .build()

val apiService = retrofit.create(WhatsAppApiService::class.java)

// Send message
val request = SendMessageRequest("+911234567890", message)
                </div>
            </div>
            
            <div class="step">
                <h3>🔧 Troubleshooting</h3>
                <ul>
                    <li><strong>Chrome not found:</strong> Make sure Chrome is installed and ChromeDriver is in PATH</li>
                    <li><strong>WhatsApp not loading:</strong> Check your internet connection and try again</li>
                    <li><strong>QR Code issues:</strong> Delete the whatsapp_profile folder and scan QR code again</li>
                    <li><strong>Message not sending:</strong> Check if the phone number is valid and has WhatsApp</li>
                </ul>
            </div>
            
            <div class="step">
                <h3>📱 Kotlin App Example</h3>
                <p>Here's a complete example for your Kotlin app:</p>
                <div class="code">
// Data classes
data class SendMessageRequest(
    val phone_number: String,
    val message: String
)

data class SendMessageResponse(
    val success: Boolean,
    val message: String,
    val session_id: String?,
    val status: String?
)

data class StatusResponse(
    val success: Boolean,
    val session_id: String?,
    val phone_number: String?,
    val message: String?,
    val status: String?,
    val progress: Int?,
    val timestamp: String?,
    val is_complete: Boolean?,
    val is_success: Boolean?,
    val error: String?
)

// API Interface
interface WhatsAppApiService {
    @POST("api/send-message")
    suspend fun sendMessage(@Body request: SendMessageRequest): Response<SendMessageResponse>
    
    @GET("api/status/{sessionId}")
    suspend fun getStatus(@Path("sessionId") sessionId: String): Response<StatusResponse>
    
    @GET("api/health")
    suspend fun healthCheck(): Response<Map<String, Any>>
}

// Usage in Activity/Fragment
class MainActivity : AppCompatActivity() {
    private lateinit var apiService: WhatsAppApiService
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // Initialize Retrofit
        val retrofit = Retrofit.Builder()
            .baseUrl("http://YOUR_SERVER_IP:5000/")
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            
        apiService = retrofit.create(WhatsAppApiService::class.java)
        
        // Example: Send message
        sendWhatsAppMessage("+911234567890", "Hello from Kotlin!")
    }
    
    private fun sendWhatsAppMessage(phoneNumber: String, message: String) {
        lifecycleScope.launch {
            try {
                val request = SendMessageRequest(phoneNumber, message)
                val response = apiService.sendMessage(request)
                
                if (response.isSuccessful) {
                    val result = response.body()
                    if (result?.success == true) {
                        Toast.makeText(this@MainActivity, "Message sending started", Toast.LENGTH_SHORT).show()
                        result.session_id?.let { sessionId ->
                            trackMessageStatus(sessionId)
                        }
                    } else {
                        Toast.makeText(this@MainActivity, "Failed: ${result?.message}", Toast.LENGTH_LONG).show()
                    }
                } else {
                    Toast.makeText(this@MainActivity, "HTTP Error: ${response.code()}", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Network Error: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }
    
    private fun trackMessageStatus(sessionId: String) {
        lifecycleScope.launch {
            var isComplete = false
            while (!isComplete) {
                try {
                    val response = apiService.getStatus(sessionId)
                    if (response.isSuccessful) {
                        val status = response.body()
                        if (status?.success == true) {
                            // Update UI with progress
                            runOnUiThread {
                                updateProgressUI(status.status, status.progress ?: 0)
                            }
                            
                            if (status.is_complete == true) {
                                isComplete = true
                                runOnUiThread {
                                    if (status.is_success == true) {
                                        Toast.makeText(this@MainActivity, "Message sent successfully!", Toast.LENGTH_LONG).show()
                                    } else {
                                        Toast.makeText(this@MainActivity, "Failed: ${status.error}", Toast.LENGTH_LONG).show()
                                    }
                                }
                            }
                        }
                    }
                    delay(2000) // Check every 2 seconds
                } catch (e: Exception) {
                    break
                }
            }
        }
    }
    
    private fun updateProgressUI(status: String?, progress: Int) {
        // Update your progress bar and status text here
        // Example:
        // progressBar.progress = progress
        // statusTextView.text = status
    }
}

// Add to build.gradle (app level)
dependencies {
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.squareup.retrofit2:converter-gson:2.9.0'
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.6.4'
    implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.6.2'
}

// Add to AndroidManifest.xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
                </div>
            </div>
            
            <div class="step">
                <h3>🌐 Network Configuration</h3>
                <p>Make sure your server is accessible from your Android device:</p>
                <ul>
                    <li>If testing locally, use your computer's IP address (not localhost)</li>
                    <li>Make sure port 5000 is not blocked by firewall</li>
                    <li>For production, deploy to a cloud server (AWS, Google Cloud, etc.)</li>
                </ul>
                <div class="code">
# Find your IP address
# Windows: ipconfig
# Mac/Linux: ifconfig or ip addr show
# Then use: http://192.168.1.100:5000/ (replace with your IP)
                </div>
            </div>
        </div>
        
        <div class="back-link">
            <a href="/">← Back to Message Sender</a>
        </div>
    </div>
</body>
</html>''')
    
    print("WhatsApp API Server is ready!")
    print("========================================")
    print("🌐 Web Interface: http://0.0.0.0:5000")
    print("📱 API Endpoints:")
    print("   • POST /api/send-message")
    print("   • GET /api/status/{session_id}")
    print("   • GET /api/health")
    print("========================================")
    print("🔧 Setup: Visit http://0.0.0.0:5000/setup for complete instructions")
    print("📋 First time? You'll need to scan QR code in WhatsApp Web")
    print("========================================")
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)