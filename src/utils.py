# src/utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText

# [수정] .env 파일 업데이트 함수 (줄바꿈 안전 처리 추가)
def update_env_variable(key, value):
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        key_found = False
        
        for line in lines:
            # 주석이나 빈 줄은 유지하되, 내용이 있는 줄은 그대로 둠
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
            # [중요] 기존 마지막 줄이 줄바꿈으로 끝나지 않았다면 줄바꿈 추가
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines[-1] += '\n'
            
            # 새 변수 추가
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
    except Exception as e:
        print(f"[시스템] .env 업데이트 실패: {e}")

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