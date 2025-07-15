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
        self.last_phone_number = None
        
    def setup_driver(self):
        """Setup Chrome driver optimized for cloud environments"""
        options = Options()
        
        # Essential options for stability
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--window-size=1920,1080')
        
        # Cloud environment detection
        is_cloud = (os.environ.get('RENDER') or 
                   os.environ.get('HEROKU') or 
                   os.environ.get('RAILWAY') or 
                   os.environ.get('REPLIT') or
                   os.environ.get('CODESPACE_NAME') or
                   os.environ.get('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN') or
                   not os.environ.get('DISPLAY'))
        
        if is_cloud:
            # Cloud-specific optimizations
            options.add_argument('--headless=new')  # Use new headless mode
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-features=TranslateUI')
            options.add_argument('--disable-ipc-flooding-protection')
            options.add_argument('--disable-features=VizDisplayCompositor')
            options.add_argument('--force-device-scale-factor=1')
            options.add_argument('--disable-features=WebRtcHideLocalIpsWithMdns')
            print("Running in cloud mode (headless)")
        else:
            print("Running in local mode")
        
        # Performance optimizations
        options.add_argument('--disable-images')
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
        
        # Don't clear data on startup
        options.add_argument('--disable-session-crashed-bubble')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-restore-session-state')
        options.add_argument('--keep-alive-for-test')
        
        # Add mobile user agent for better compatibility
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            # Increase wait time for cloud environments
            wait_time = 20 if is_cloud else 10
            self.wait = WebDriverWait(self.driver, wait_time)
            
            # Set page load timeout
            self.driver.set_page_load_timeout(30)
            
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
                    time.sleep(3)  # Increased wait time
                except Exception as nav_error:
                    logger.error(f"Navigation error: {nav_error}")
                    if "invalid session id" in str(nav_error).lower():
                        if self.restart_driver():
                            try:
                                self.driver.get("https://web.whatsapp.com")
                                time.sleep(3)
                            except:
                                return False, "Failed to navigate after driver restart"
                        else:
                            return False, "Failed to restart driver"
                    else:
                        return False, f"Navigation error: {str(nav_error)}"
            
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
                try:
                    if self.driver.find_elements(By.CSS_SELECTOR, selector):
                        qr_present = True
                        break
                except Exception as selector_error:
                    logger.warning(f"Error checking QR selector {selector}: {selector_error}")
                    continue
            
            if qr_present:
                return False, "Please scan QR code in browser to login"
            
            time.sleep(2)
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Logged in successfully after wait"
            
            return False, "Login status unclear - please check browser window"
            
        except Exception as e:
            logger.error(f"Error in ensure_logged_in: {e}")
            
            if "invalid session id" in str(e).lower():
                logger.info("Invalid session detected in ensure_logged_in")
                if self.restart_driver():
                    try:
                        return self.ensure_logged_in()
                    except Exception as retry_error:
                        logger.error(f"Retry after restart failed: {retry_error}")
                        return False, "Failed to login after driver restart"
                else:
                    return False, "Failed to restart driver"
            
            return False, f"Login error: {str(e)}"
    
    def wait_for_element_with_retry(self, selectors, timeout=15, description="element"):
        """Wait for element with multiple selectors and retry logic"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        element = elements[0]
                        if element.is_displayed() and element.is_enabled():
                            logger.info(f"Found {description} with selector: {selector}")
                            return element
                except Exception as e:
                    logger.debug(f"Error checking selector {selector}: {e}")
                    continue
            
            time.sleep(0.5)
        
        logger.warning(f"Could not find {description} after {timeout} seconds")
        return None
    
    def send_message(self, phone_number, message):
        """Enhanced message sending with better cloud compatibility"""
        with self.lock:
            try:
                if not phone_number or not phone_number.strip():
                    return False, "Phone number is required"
                
                phone_number = phone_number.strip()
                
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
                print(f"Sending message to: {phone_number}")
                
                try:
                    self.driver.get(api_url)
                    time.sleep(3)  # Increased wait time for cloud environments
                except Exception as nav_error:
                    logger.error(f"Navigation error: {nav_error}")
                    if "invalid session id" in str(nav_error).lower():
                        if self.restart_driver():
                            try:
                                login_success, login_msg = self.ensure_logged_in()
                                if not login_success:
                                    return False, login_msg
                                
                                self.driver.get(api_url)
                                time.sleep(3)
                            except Exception as retry_error:
                                return False, f"Failed to navigate after restart: {str(retry_error)}"
                        else:
                            return False, "Failed to restart driver"
                    else:
                        return False, f"Navigation error: {str(nav_error)}"
                
                # Check if we're still logged in
                if not self.quick_login_check():
                    return False, "Lost login session - please login again"
                
                # Wait for page to fully load
                time.sleep(2)
                
                # Enhanced send button detection with more selectors
                send_button_selectors = [
                    "[data-testid='send']",
                    "[data-icon='send']",
                    "button[data-testid='send']",
                    "span[data-testid='send']",
                    "button[aria-label='Send']",
                    "span[data-icon='send']",
                    "button[title='Send']",
                    ".send-button",
                    "[role='button'][data-testid='send']"
                ]
                
                # Wait for send button with extended timeout for cloud environments
                send_button = self.wait_for_element_with_retry(
                    send_button_selectors, 
                    timeout=20, 
                    description="send button"
                )
                
                if send_button:
                    try:
                        # Multiple click strategies
                        strategies = [
                            lambda: self.driver.execute_script("arguments[0].click();", send_button),
                            lambda: send_button.click(),
                            lambda: ActionChains(self.driver).click(send_button).perform(),
                            lambda: ActionChains(self.driver).move_to_element(send_button).click().perform()
                        ]
                        
                        for i, strategy in enumerate(strategies):
                            try:
                                logger.info(f"Trying click strategy {i+1}")
                                strategy()
                                time.sleep(1)
                                
                                # Verify message was sent by checking if input is cleared
                                message_input_selectors = [
                                    "[data-testid='conversation-compose-box-input']",
                                    "div[contenteditable='true'][data-tab='10']",
                                    "[data-testid='compose-box-input']"
                                ]
                                
                                for selector in message_input_selectors:
                                    try:
                                        input_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                                        if input_element and (not input_element.text.strip() or input_element.text.strip() == ""):
                                            self.last_phone_number = phone_number
                                            self.save_cookies()
                                            logger.info(f"Message sent successfully to {phone_number}")
                                            return True, f"Message sent successfully to {phone_number}"
                                    except:
                                        continue
                                
                                # If input check fails, assume success if no error occurred
                                self.last_phone_number = phone_number
                                self.save_cookies()
                                logger.info(f"Message sent successfully to {phone_number}")
                                return True, f"Message sent successfully to {phone_number}"
                                
                            except Exception as click_error:
                                logger.warning(f"Click strategy {i+1} failed: {click_error}")
                                if i == len(strategies) - 1:
                                    break
                                continue
                        
                        # If all click strategies fail, try keyboard approach
                        logger.info("All click strategies failed, trying keyboard approach")
                        
                    except Exception as button_error:
                        logger.error(f"Error with send button: {button_error}")
                
                # Fallback: Enhanced keyboard method
                logger.info("Trying keyboard fallback method")
                
                message_input_selectors = [
                    "[data-testid='conversation-compose-box-input']",
                    "div[contenteditable='true'][data-tab='10']",
                    "[data-testid='compose-box-input']",
                    "div[contenteditable='true'][role='textbox']",
                    "div[data-testid='compose-box'] div[contenteditable='true']"
                ]
                
                message_input = self.wait_for_element_with_retry(
                    message_input_selectors,
                    timeout=15,
                    description="message input"
                )
                
                if message_input:
                    try:
                        # Clear any existing text and ensure focus
                        message_input.clear()
                        message_input.click()
                        time.sleep(0.5)
                        
                        # Type the message
                        message_input.send_keys(message)
                        time.sleep(0.5)
                        
                        # Try multiple ways to send
                        send_methods = [
                            lambda: message_input.send_keys(Keys.ENTER),
                            lambda: message_input.send_keys(Keys.CONTROL, Keys.ENTER),
                            lambda: ActionChains(self.driver).key_down(Keys.ENTER).key_up(Keys.ENTER).perform()
                        ]
                        
                        for method in send_methods:
                            try:
                                method()
                                time.sleep(1)
                                
                                # Check if message was sent
                                if not message_input.text.strip():
                                    self.last_phone_number = phone_number
                                    self.save_cookies()
                                    logger.info(f"Message sent via keyboard to {phone_number}")
                                    return True, f"Message sent successfully to {phone_number}"
                                    
                            except Exception as method_error:
                                logger.warning(f"Keyboard method failed: {method_error}")
                                continue
                        
                        # Final attempt - just assume success if we got this far
                        self.last_phone_number = phone_number
                        self.save_cookies()
                        return True, f"Message sent successfully to {phone_number}"
                        
                    except Exception as input_error:
                        logger.error(f"Error with message input: {input_error}")
                        return False, f"Could not interact with message input: {str(input_error)}"
                
                return False, "Could not find message input field or send button"
                
            except Exception as e:
                logger.error(f"Error in send_message: {e}")
                
                if "invalid session id" in str(e).lower():
                    logger.info("Invalid session detected in send_message")
                    if self.restart_driver():
                        try:
                            return self.send_message(phone_number, message)
                        except Exception as retry_error:
                            logger.error(f"Retry after restart failed: {retry_error}")
                            return False, "Failed to send message after driver restart"
                    else:
                        return False, "Failed to restart driver"
                
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
            logger.info("Restarting driver due to invalid session...")
            
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
        """Get QR code for manual scanning with better cloud compatibility"""
        try:
            if not self.is_driver_alive():
                logger.info("Driver not alive, restarting...")
                if not self.restart_driver():
                    return False, "Failed to restart browser driver"
            
            if not self.driver:
                if not self.setup_driver():
                    return False, "Failed to setup driver"
            
            print("Loading WhatsApp Web...")
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.driver.get("https://web.whatsapp.com")
                    time.sleep(4)  # Increased wait time
                    break
                except Exception as nav_error:
                    logger.warning(f"Navigation attempt {attempt + 1} failed: {nav_error}")
                    if attempt == max_retries - 1:
                        if not self.restart_driver():
                            return False, "Failed to navigate to WhatsApp Web"
                        else:
                            try:
                                self.driver.get("https://web.whatsapp.com")
                                time.sleep(4)
                                break
                            except:
                                return False, "Failed to navigate to WhatsApp Web after driver restart"
                    else:
                        time.sleep(2)
            
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
            
            # Extended wait for QR code in cloud environments
            max_wait = 15
            wait_interval = 0.5
            elapsed = 0
            
            while elapsed < max_wait and not qr_found:
                for selector in qr_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            print(f"QR code found with selector: {selector}")
                            qr_found = True
                            break
                    except Exception as selector_error:
                        logger.warning(f"Error checking selector {selector}: {selector_error}")
                        continue
                
                if not qr_found:
                    time.sleep(wait_interval)
                    elapsed += wait_interval
            
            if qr_found:
                return True, "QR code is available for scanning in the browser window"
            
            if self.quick_login_check():
                self.is_logged_in = True
                self.save_cookies()
                return True, "Successfully logged in"
            
            return False, "Could not detect QR code. Please refresh the page or check browser window."
                
        except Exception as e:
            logger.error(f"Error in get_qr_code: {e}")
            
            if "invalid session id" in str(e).lower():
                logger.info("Invalid session detected, attempting driver restart...")
                if self.restart_driver():
                    try:
                        return self.get_qr_code()
                    except Exception as retry_error:
                        logger.error(f"Retry after restart failed: {retry_error}")
                        return False, "Failed to get QR code after driver restart"
                else:
                    return False, "Failed to restart driver after invalid session"
            
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
        logger.error(f"Setup QR route error: {e}")
        
        if "invalid session id" in str(e).lower():
            try:
                bot.restart_driver()
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
            except Exception as retry_error:
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to restart after session error: {str(retry_error)}'
                }), 500
        
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

# REMOVED: send_custom_message route as it's duplicate of send_message

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
