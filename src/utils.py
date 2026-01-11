# src/utils.py
import re
import os
import smtplib
import threading
from email.mime.text import MIMEText
from datetime import datetime

# [신규] 파일 접근 경합 방지용 락
file_lock = threading.Lock()

def update_env_variable(key, value):
    env_path = ".env"
    
    # [수정] 파일 I/O 전체를 Lock으로 보호
    with file_lock:
        if not os.path.exists(env_path):
            try:
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"{key}={value}\n")
            except Exception as e:
                print(f"[시스템] .env 생성 실패: {e}")
            return

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            key_found = False
            
            for line in lines:
                if line.strip().startswith("#") or not line.strip():
                    new_lines.append(line)
                    continue
                
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        new_lines.append(f"{key}={value}\n")
                        key_found = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            if not key_found:
                if new_lines and not new_lines[-1].endswith('\n'):
                    new_lines[-1] += '\n'
                new_lines.append(f"{key}={value}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
                
        except Exception as e:
            print(f"[시스템] .env 업데이트 실패: {e}")

# ... (이하 기존 함수들은 동일) ...

def log_unknown_word(word):
    file_path = "unknown_words.txt"
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"{word}\n")
    except Exception as e:
        print(f"[오류] 없는 단어 기록 실패: {e}")

def handle_violation_alert(nickname, word):
    record_file = "violation_users.txt"
    if os.path.exists(record_file):
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                sent_users = [line.strip() for line in f.readlines()]
                if nickname in sent_users:
                    return False
        except Exception:
            pass

    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        return False

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        msg = MIMEText(f"다음 사용자가 부적절한 단어를 사용했습니다.\n\n"
                       f"- 닉네임: {nickname}\n"
                       f"- 입력 단어: {word}\n"
                       f"- 감지 시간: {current_time}\n")
        
        msg['Subject'] = f"[경고] 부적절한 단어 사용 감지 ({nickname})"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        try:
            with open(record_file, "a", encoding="utf-8") as f:
                f.write(f"{nickname}\n")
        except:
            pass
        return True
    except Exception as e:
        print(f"[오류] 경고 메일 발송 실패: {e}")
        return False

def send_crash_report_email(error_log):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        print("[Utils] 메일 설정 누락으로 크래시 리포트 발송 실패")
        return False

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        msg = MIMEText(f"프로그램이 치명적인 오류로 인해 비정상 종료되었습니다.\n\n"
                       f"- 발생 시간: {current_time}\n"
                       f"- 오류 내용:\n{error_log}")
        
        msg['Subject'] = "[긴급] 프로그램 비정상 종료 (Crash Report)"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        print("[시스템] 관리자에게 크래시 리포트 메일을 발송했습니다.")
        return True
    except Exception as e:
        print(f"[오류] 크래시 리포트 발송 실패: {e}")
        return False

class ProfanityFilter:
    def __init__(self, filepath="bad_words.txt"):
        self.bad_words = set()
        self.filepath = filepath
        self.load_words()

    def load_words(self):
        if not os.path.exists(self.filepath):
            try:
                with open(self.filepath, "w", encoding="utf-8") as f:
                    pass 
            except:
                pass
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word:
                        self.bad_words.add(word)
            print(f"[시스템] 금지어 리스트 로드 완료 ({len(self.bad_words)}개)")
        except Exception as e:
            print(f"[오류] 금지어 로드 실패: {e}")

    def check(self, text):
        text_clean = text.replace(" ", "")
        for bad in self.bad_words:
            if bad in text_clean:
                return True, bad
        return False, None

def apply_dueum_rule(char):
    if not re.match(r'[가-힣]', char):
        return [char]

    base_code = ord(char) - 44032
    chosung_idx = base_code // 588
    jungsung_idx = (base_code % 588) // 28
    jongsung_idx = base_code % 28

    y_sounds = [2, 3, 6, 7, 12, 17, 20] 
    dual_sounds = [18] 

    variations = [char]
    target_chosungs = []

    if chosung_idx == 5: 
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) 
        elif jungsung_idx in dual_sounds:
            target_chosungs.append(2) 
            target_chosungs.append(11) 
        else:
            target_chosungs.append(2) 
            
    elif chosung_idx == 2: 
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) 

    for new_chosung in target_chosungs:
        new_char_code = 44032 + (new_chosung * 588) + (jungsung_idx * 28) + jongsung_idx
        new_char = chr(new_char_code)
        if new_char not in variations:
            variations.append(new_char)
    
    return variations

def send_alert_email(current_word):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        print("[Utils] 메일 설정 누락으로 발송 취소")
        return False, "설정 누락"

    try:
        msg = MIMEText(f"현재 단어 '{current_word}'(으)로 게임이 1시간 이상 멈춰있습니다.\n확인해주세요.")
        msg['Subject'] = "[알림] 끝말잇기 게임 1시간 경과"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        return True, "발송 성공"
    except Exception as e:
        return False, str(e)