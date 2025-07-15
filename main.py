from flask import Flask, render_template, request, jsonify
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import threading
import atexit
import json
from urllib.parse import quote
import logging
import sys
import pickle
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class WhatsAppBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.is_logged_in = False
        self.lock = threading.Lock()
        self.session_file = "whatsapp_session.json"
        self.user_data_dir = os.path.join(os.getcwd(), 'chrome_user_data')
        self.cookies_file = "whatsapp_cookies.pkl"
        self.last_phone_number = None  # Track last used number
        
    def setup_driver(self):
        """Setup Chrome driver optimized for speed and session persistence"""
        options = Options()
        
        # Essential options for stability
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--window-size=1920,1080')
        
        # SPEED OPTIMIZATIONS
        options.add_argument('--disable-images')
        # options.add_argument('--disable-javascript')  # Commented out as WhatsApp needs JS
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-features=TranslateUI')
        options.add_argument('--disable-default-apps')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-sync')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        
        # Check if running in cloud environment
        is_cloud = os.environ.get('RENDER') or os.environ.get('HEROKU') or os.environ.get('RAILWAY')
        
        if is_cloud:
            # Cloud-specific options
            options.add_argument('--headless')
            print("Running in cloud mode (headless)")
        else:
            # Local development - show browser window
            print("Running in local mode (with browser window)")
        
        # Performance optimizations
        options.add_argument('--aggressive-cache-discard')
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=4096')
        
        # Anti-detection
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Session persistence
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
        
        options.add_argument(f'--user-data-dir={self.user_data_dir}')
        options.add_argument('--profile-directory=WhatsAppBot')
        
        # Don't clear data on startup
        options.add_argument('--disable-session-crashed-bubble')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-restore-session-state')
        
        # Add flags to preserve session
        options.add_argument('--keep-alive-for-test')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            # Reduce wait time for faster operations
            self.wait = WebDriverWait(self.driver, 10)
            
            # Load saved cookies if they exist
            self.load_cookies()
            
            logger.info("Chrome driver setup successful")
            return True
        except Exception as e:
            logger.error(f"Error setting up driver: {e}")
            print(f"Error setting up driver: {e}")
            return False
    
    def save_cookies(self):
        """Save cookies to maintain session"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookies_file, 'wb') as f:
                    pickle.dump(cookies, f)
                logger.info("Cookies saved successfully")
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")
    
    def load_cookies(self):
        """Load saved cookies"""
        try:
            if os.path.exists(self.cookies_file) and self.driver:
                # First navigate to WhatsApp domain
                self.driver.get("https://web.whatsapp.com")
                time.sleep(1)
                
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)
                
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        logger.warning(f"Could not add cookie: {e}")
                
                logger.info("Cookies loaded successfully")
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
    
    def is_whatsapp_loaded(self):
        """Check if WhatsApp is loaded and ready"""
        try:
            indicators = [
                "[data-testid='side']",
                "#side",
                "div[data-testid='chat-list']",
                "header[data-testid='chatlist-header']",
                "[data-testid='chat-list-search']"
            ]
            
            for indicator in indicators:
                if self.driver.find_elements(By.CSS_SELECTOR, indicator):
                    return True
            return False
        except:
            return False
    
    def quick_login_check(self):
        """Enhanced login status check"""
        try:
            current_url = self.driver.current_url
            if "web.whatsapp.com" in current_url:
                logged_in_indicators = [
                    "[data-testid='side']",
                    "[data-testid='chat-list']",
                    "div[data-testid='chatlist-header']",
                    "#side",
                    "div[role='textbox']"
                ]
                
                for indicator in logged_in_indicators:
                    if self.driver.find_elements(By.CSS_SELECTOR, indicator):
                        return True
                
                qr_indicators = [
                    "[data-testid='qr-code']",
                    "canvas[role='img']",
                    "canvas"
                ]
                
                for qr_indicator in qr_indicators:
                    if self.driver.find_elements(By.CSS_SELECTOR, qr_indicator):
                        return False
                
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error in quick_login_check: {e}")
            return False
    
    def ensure_logged_in(self):
        """Ensure we're logged in with better session handling"""
        try:
            if not self.driver:
                if not self.setup_driver():
                    return False, "Failed to setup Chrome driver"
            
            current_url = self.driver.current_url if self.driver else ""
            
            if "web.whatsapp.com" in current_url:
                if self.quick_login_check():
                    self.is_logged_in = True
                    return True, "Already logged in"
            
            if "web.whatsapp.com" not in current_url:
                logger.info("Navigating to WhatsApp Web...")
                self.driver.get("https://web.whatsapp.com")
                time.sleep(2)
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Logged in successfully"
            
            qr_present = False
            qr_selectors = [
                "[data-testid='qr-code']",
                "canvas[role='img']",
                "canvas"
            ]
            
            for selector in qr_selectors:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    qr_present = True
                    break
            
            if qr_present:
                return False, "Please scan QR code in browser to login"
            
            time.sleep(1)
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Logged in successfully after wait"
            
            return False, "Login status unclear - please check browser window"
            
        except Exception as e:
            logger.error(f"Error in ensure_logged_in: {e}")
            return False, f"Login error: {str(e)}"
    
    def send_message(self, phone_number, message):
        """FIXED: Main message sending method with proper phone number handling"""
        with self.lock:
            try:
                # Validate phone number first
                if not phone_number or not phone_number.strip():
                    return False, "Phone number is required"
                
                phone_number = phone_number.strip()
                
                # Ensure we have a driver and are logged in
                login_success, login_msg = self.ensure_logged_in()
                
                if not login_success:
                    return False, login_msg
                
                # ALWAYS use the API URL method to ensure we go to the correct chat
                clean_number = phone_number.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                encoded_message = quote(message)
                api_url = f"https://web.whatsapp.com/send?phone={clean_number}&text={encoded_message}"
                
                logger.info(f"Navigating to: {api_url}")
                print(f"Sending message to: {phone_number}")
                print(f"Clean number: {clean_number}")
                print(f"URL: {api_url}")
                
                # Navigate to the specific chat
                self.driver.get(api_url)
                time.sleep(2)  # Wait for page to load
                
                # Check if we're still logged in
                if not self.quick_login_check():
                    return False, "Lost login session - please login again"
                
                # Wait for the message to be populated in the input field
                time.sleep(1)
                
                # Try to find and click the send button
                send_button = None
                send_selectors = [
                    "[data-testid='send']",
                    "[data-icon='send']",
                    "button[data-testid='send']",
                    "span[data-testid='send']"
                ]
                
                # Wait for send button to be available
                max_wait = 8
                wait_interval = 0.5
                elapsed = 0
                
                while elapsed < max_wait and not send_button:
                    for selector in send_selectors:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and elements[0].is_enabled():
                            send_button = elements[0]
                            break
                    
                    if not send_button:
                        time.sleep(wait_interval)
                        elapsed += wait_interval
                
                if send_button:
                    # Use JavaScript click for reliability
                    self.driver.execute_script("arguments[0].click();", send_button)
                    time.sleep(0.5)
                    
                    # Update last used number
                    self.last_phone_number = phone_number
                    
                    # Save cookies after successful message
                    self.save_cookies()
                    
                    logger.info(f"Message sent successfully to {phone_number}")
                    return True, f"Message sent successfully to {phone_number}"
                
                # Fallback: Try using Enter key
                try:
                    # Find message input and send with Enter
                    message_input_selectors = [
                        "[data-testid='conversation-compose-box-input']",
                        "div[contenteditable='true'][data-tab='10']",
                        "[data-testid='compose-box-input']"
                    ]
                    
                    for selector in message_input_selectors:
                        try:
                            message_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                            if message_input:
                                message_input.click()
                                time.sleep(0.2)
                                message_input.send_keys(Keys.ENTER)
                                time.sleep(0.5)
                                
                                self.last_phone_number = phone_number
                                self.save_cookies()
                                
                                logger.info(f"Message sent via Enter key to {phone_number}")
                                return True, f"Message sent successfully to {phone_number}"
                        except:
                            continue
                    
                    return False, "Could not send message - send button not found and Enter key failed"
                    
                except Exception as fallback_error:
                    logger.error(f"Fallback method failed: {fallback_error}")
                    return False, f"Could not send message: {str(fallback_error)}"
                
            except Exception as e:
                logger.error(f"Error in send_message: {e}")
                return False, f"Error: {str(e)}"
    
    def get_qr_code(self):
        """Get QR code for manual scanning with better detection"""
        try:
            if not self.driver:
                if not self.setup_driver():
                    return False, "Failed to setup driver"
            
            print("Loading WhatsApp Web...")
            self.driver.get("https://web.whatsapp.com")
            time.sleep(3)
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Already logged in - no QR code needed"
            
            qr_found = False
            qr_selectors = [
                "[data-testid='qr-code']",
                "canvas[role='img']",
                "canvas",
                "div[data-ref]",
                ".qr-code"
            ]
            
            for selector in qr_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"QR code found with selector: {selector}")
                    qr_found = True
                    break
            
            if not qr_found:
                time.sleep(2)
                for selector in qr_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        print(f"QR code found with selector: {selector}")
                        qr_found = True
                        break
            
            if qr_found:
                return True, "QR code is available for scanning in the browser window"
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Successfully logged in"
            
            return False, "Could not detect QR code. Please refresh the page or check browser window."
                
        except Exception as e:
            logger.error(f"Error in get_qr_code: {e}")
            return False, f"Error getting QR code: {str(e)}"
    
    def close_session(self):
        """Close browser session"""
        with self.lock:
            try:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
                    self.wait = None
                    self.is_logged_in = False
                    self.last_phone_number = None
                    print("Session closed successfully (cookies preserved)")
                    return True, "Session closed successfully"
                else:
                    return True, "No active session to close"
            except Exception as e:
                logger.error(f"Error closing session: {e}")
                return False, f"Error closing session: {str(e)}"
    
    def clear_session_data(self):
        """Clear all session data including cookies and user data"""
        with self.lock:
            try:
                if self.driver:
                    self.driver.quit()
                    self.driver = None
                    self.wait = None
                    self.is_logged_in = False
                    self.last_phone_number = None
                
                if os.path.exists(self.cookies_file):
                    os.remove(self.cookies_file)
                
                import shutil
                if os.path.exists(self.user_data_dir):
                    shutil.rmtree(self.user_data_dir, ignore_errors=True)
                
                print("All session data cleared")
                return True, "All session data cleared successfully"
            except Exception as e:
                logger.error(f"Error clearing session data: {e}")
                return False, f"Error clearing session data: {str(e)}"

# Global bot instance
bot = WhatsAppBot()

# REMOVED: Default phone number and message (they were causing the issue)
# These should only be used for testing, not as fallbacks

@app.route('/')
def index():
    return render_template('index.html')

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
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        # Get data from request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            }), 400
        
        # FIXED: No fallback to hardcoded numbers
        phone_number = data.get('phone_number', '').strip()
        message_text = data.get('message', '').strip()
        
        # Validate inputs
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
        
        # Validate phone number format
        if not phone_number.startswith('+'):
            return jsonify({
                'status': 'error',
                'message': 'Phone number must include country code (e.g., +91xxxxxxxxxx)'
            }), 400
        
        # Validate phone number length
        clean_number = phone_number.replace('+', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if len(clean_number) < 8 or len(clean_number) > 15:
            return jsonify({
                'status': 'error',
                'message': 'Invalid phone number length'
            }), 400
        
        # Send message
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
