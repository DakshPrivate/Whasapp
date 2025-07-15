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
import base64
from io import BytesIO

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
        self.last_phone_number = None
        self.cloud_environment = self.detect_cloud_environment()
        
    def detect_cloud_environment(self):
        """Detect if running in cloud environment"""
        cloud_indicators = [
            'RENDER', 'HEROKU', 'RAILWAY', 'REPLIT', 'CODESPACE_NAME',
            'GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'VERCEL',
            'NETLIFY', 'GLITCH_PROJECT_NAME', 'COLAB_GPU'
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
        """Setup Chrome driver with proper cloud/local detection"""
        try:
            # Import selenium modules
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains
            import pickle
            
        except ImportError as e:
            logger.error(f"Selenium not installed: {e}")
            return False
        
        options = Options()
        
        # Essential options for stability
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--window-size=1920,1080')
        
        # Force headless mode in cloud environments
        if self.cloud_environment:
            options.add_argument('--headless=new')
            logger.info("Running in cloud mode (headless)")
        else:
            logger.info("Running in local mode (with display)")
        
        # Performance optimizations
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-default-apps')
        options.add_argument('--no-default-browser-check')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-sync')
        options.add_argument('--disable-web-security')
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
        
        # User agent
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Import WebDriverWait here after driver is created
            from selenium.webdriver.support.ui import WebDriverWait
            wait_time = 30 if self.cloud_environment else 15
            self.wait = WebDriverWait(self.driver, wait_time)
            
            # Set page load timeout
            self.driver.set_page_load_timeout(60)
            
            # Load saved cookies if they exist
            self.load_cookies()
            
            logger.info("Chrome driver setup successful")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up driver: {e}")
            return False
    
    def save_cookies(self):
        """Save cookies to maintain session"""
        try:
            import pickle
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
            import pickle
            if os.path.exists(self.cookies_file) and self.driver:
                self.driver.get("https://web.whatsapp.com")
                time.sleep(2)
                
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
            from selenium.webdriver.common.by import By
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
            from selenium.webdriver.common.by import By
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
            if not self.is_driver_alive():
                logger.info("Driver not alive, restarting...")
                if not self.restart_driver():
                    return False, "Failed to restart browser driver"
            
            if not self.driver:
                if not self.setup_driver():
                    return False, "Failed to setup Chrome driver"
            
            try:
                current_url = self.driver.current_url if self.driver else ""
            except Exception as url_error:
                logger.warning(f"Could not get current URL: {url_error}")
                current_url = ""
            
            if "web.whatsapp.com" in current_url:
                if self.quick_login_check():
                    self.is_logged_in = True
                    return True, "Already logged in"
            
            if "web.whatsapp.com" not in current_url:
                logger.info("Navigating to WhatsApp Web...")
                try:
                    self.driver.get("https://web.whatsapp.com")
                    time.sleep(5)
                except Exception as nav_error:
                    logger.error(f"Navigation error: {nav_error}")
                    return False, f"Navigation error: {str(nav_error)}"
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Logged in successfully"
            
            # Check for QR code
            from selenium.webdriver.common.by import By
            qr_present = False
            qr_selectors = [
                "[data-testid='qr-code']",
                "canvas[role='img']",
                "canvas"
            ]
            
            for selector in qr_selectors:
                try:
                    if self.driver.find_elements(By.CSS_SELECTOR, selector):
                        qr_present = True
                        break
                except:
                    continue
            
            if qr_present:
                return False, "Please scan QR code to login"
            
            return False, "Login status unclear"
            
        except Exception as e:
            logger.error(f"Error in ensure_logged_in: {e}")
            return False, f"Login error: {str(e)}"
    
    def capture_qr_code(self):
        """Capture QR code as base64 image"""
        try:
            from selenium.webdriver.common.by import By
            from PIL import Image
            
            qr_selectors = [
                "[data-testid='qr-code']",
                "canvas[role='img']",
                "canvas"
            ]
            
            qr_element = None
            for selector in qr_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and elements[0].is_displayed():
                        qr_element = elements[0]
                        break
                except:
                    continue
            
            if qr_element:
                # Get the QR code element location and size
                location = qr_element.location
                size = qr_element.size
                
                # Take a screenshot of the entire page
                screenshot = self.driver.get_screenshot_as_png()
                
                # Open the screenshot with PIL
                image = Image.open(BytesIO(screenshot))
                
                # Calculate the crop area
                left = location['x']
                top = location['y']
                right = location['x'] + size['width']
                bottom = location['y'] + size['height']
                
                # Crop the QR code area
                qr_image = image.crop((left, top, right, bottom))
                
                # Convert to base64
                buffered = BytesIO()
                qr_image.save(buffered, format="PNG")
                qr_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                
                return True, qr_base64
            
            return False, "QR code element not found"
            
        except Exception as e:
            logger.error(f"Error capturing QR code: {e}")
            return False, f"Error capturing QR code: {str(e)}"
    
    def send_message(self, phone_number, message):
        """Send WhatsApp message with real functionality"""
        with self.lock:
            try:
                if not phone_number or not phone_number.strip():
                    return False, "Phone number is required"
                
                phone_number = phone_number.strip()
                
                # Import required modules
                from selenium.webdriver.common.by import By
                from selenium.webdriver.common.keys import Keys
                from selenium.webdriver.common.action_chains import ActionChains
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                if not self.is_driver_alive():
                    logger.info("Driver not alive, restarting...")
                    if not self.restart_driver():
                        return False, "Failed to restart browser driver"
                
                login_success, login_msg = self.ensure_logged_in()
                if not login_success:
                    return False, login_msg
                
                # Clean and encode the message and phone number
                clean_number = phone_number.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                encoded_message = quote(message)
                api_url = f"https://web.whatsapp.com/send?phone={clean_number}&text={encoded_message}"
                
                logger.info(f"Navigating to: {api_url}")
                
                try:
                    self.driver.get(api_url)
                    time.sleep(5)
                except Exception as nav_error:
                    logger.error(f"Navigation error: {nav_error}")
                    return False, f"Navigation error: {str(nav_error)}"
                
                # Check if we're still logged in
                if not self.quick_login_check():
                    return False, "Lost login session - please login again"
                
                # Wait for page to load
                time.sleep(3)
                
                # Enhanced send button detection
                send_button_selectors = [
                    "[data-testid='send']",
                    "[data-icon='send']",
                    "button[data-testid='send']",
                    "span[data-testid='send']",
                    "button[aria-label='Send']",
                    "span[data-icon='send']",
                    "button[title='Send']"
                ]
                
                send_button = None
                for selector in send_button_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            send_button = elements[0]
                            if send_button.is_displayed() and send_button.is_enabled():
                                break
                    except:
                        continue
                
                if send_button:
                    try:
                        # Try JavaScript click first
                        self.driver.execute_script("arguments[0].click();", send_button)
                        time.sleep(2)
                        
                        self.last_phone_number = phone_number
                        self.save_cookies()
                        logger.info(f"Message sent successfully to {phone_number}")
                        return True, f"Message sent successfully to {phone_number}"
                        
                    except Exception as click_error:
                        logger.error(f"Error clicking send button: {click_error}")
                
                # Fallback: keyboard method
                message_input_selectors = [
                    "[data-testid='conversation-compose-box-input']",
                    "div[contenteditable='true'][data-tab='10']",
                    "[data-testid='compose-box-input']"
                ]
                
                message_input = None
                for selector in message_input_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            message_input = elements[0]
                            if message_input.is_displayed() and message_input.is_enabled():
                                break
                    except:
                        continue
                
                if message_input:
                    try:
                        message_input.clear()
                        message_input.click()
                        time.sleep(1)
                        message_input.send_keys(message)
                        time.sleep(1)
                        message_input.send_keys(Keys.ENTER)
                        time.sleep(2)
                        
                        self.last_phone_number = phone_number
                        self.save_cookies()
                        logger.info(f"Message sent via keyboard to {phone_number}")
                        return True, f"Message sent successfully to {phone_number}"
                        
                    except Exception as input_error:
                        logger.error(f"Error with message input: {input_error}")
                        return False, f"Could not send message: {str(input_error)}"
                
                return False, "Could not find message input or send button"
                
            except Exception as e:
                logger.error(f"Error in send_message: {e}")
                return False, f"Error: {str(e)}"
    
    def is_driver_alive(self):
        """Check if driver is still alive and responsive"""
        try:
            if not self.driver:
                return False
            self.driver.current_url
            return True
        except:
            return False
    
    def restart_driver(self):
        """Restart the driver after a crash"""
        try:
            logger.info("Restarting driver...")
            
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                
            self.driver = None
            self.wait = None
            self.is_logged_in = False
            
            if self.setup_driver():
                logger.info("Driver restarted successfully")
                return True
            else:
                logger.error("Failed to restart driver")
                return False
                
        except Exception as e:
            logger.error(f"Error restarting driver: {e}")
            return False
    
    def get_qr_code(self):
        """Get QR code for login with image capture"""
        try:
            from selenium.webdriver.common.by import By
            
            if not self.is_driver_alive():
                if not self.restart_driver():
                    return False, "Failed to restart browser driver", None
            
            if not self.driver:
                if not self.setup_driver():
                    return False, "Failed to setup driver", None
            
            logger.info("Loading WhatsApp Web...")
            
            try:
                self.driver.get("https://web.whatsapp.com")
                time.sleep(5)
            except Exception as nav_error:
                logger.error(f"Navigation error: {nav_error}")
                return False, f"Failed to navigate to WhatsApp Web: {str(nav_error)}", None
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Already logged in - no QR code needed", None
            
            # Check for QR code
            qr_found = False
            qr_selectors = [
                "[data-testid='qr-code']",
                "canvas[role='img']",
                "canvas"
            ]
            
            # Wait for QR code
            max_wait = 20
            wait_interval = 1
            elapsed = 0
            
            while elapsed < max_wait and not qr_found:
                for selector in qr_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and elements[0].is_displayed():
                            logger.info(f"QR code found with selector: {selector}")
                            qr_found = True
                            break
                    except:
                        continue
                
                if not qr_found:
                    time.sleep(wait_interval)
                    elapsed += wait_interval
            
            if qr_found:
                # Capture QR code image
                success, qr_image_data = self.capture_qr_code()
                if success:
                    return True, "QR code captured successfully", qr_image_data
                else:
                    return True, "QR code is ready for scanning. Please scan it with your phone.", None
            
            return False, "Could not find QR code. Please try again.", None
                
        except Exception as e:
            logger.error(f"Error in get_qr_code: {e}")
            return False, f"Error getting QR code: {str(e)}", None
    
    def check_login_status(self):
        """Check current login status"""
        try:
            if not self.is_driver_alive():
                return False, "Driver not active"
            
            if self.quick_login_check():
                self.is_logged_in = True
                return True, "Logged in successfully"
            else:
                return False, "Not logged in"
                
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False, f"Error: {str(e)}"
    
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
                    logger.info("Session closed successfully")
                    return True, "Session closed successfully"
                else:
                    return True, "No active session to close"
            except Exception as e:
                logger.error(f"Error closing session: {e}")
                return False, f"Error closing session: {str(e)}"

# Global bot instance
bot = WhatsAppBot()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/setup_qr', methods=['POST'])
def setup_qr():
    try:
        success, message, qr_image = bot.get_qr_code()
        
        if success:
            response_data = {
                'status': 'success',
                'message': message
            }
            
            # Include QR code image if available
            if qr_image:
                response_data['qr_image'] = qr_image
            
            return jsonify(response_data)
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

@app.route('/check_login', methods=['GET'])
def check_login():
    try:
        success, message = bot.check_login_status()
        
        return jsonify({
            'status': 'success' if success else 'error',
            'message': message,
            'logged_in': success
        })
        
    except Exception as e:
        logger.error(f"Check login route error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}',
            'logged_in': False
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
    print("Make sure you have installed: pip install selenium pillow")
    print("And Chrome browser is installed on your system")
    print("Server will be available at: http://localhost:5000")
    
    # For cloud hosting, use environment variables
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
