# src/utils.py
import re
import os
import smtplib
import threading
from email.mime.text import MIMEText
from datetime import datetime

file_lock = threading.Lock()

def update_env_variable(key, value):
    env_path = ".env"
    
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
                new_lines.append(f"{key}={value}\n")

            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            print(f"[시스템] .env 업데이트 중 오류: {e}")

def apply_dueum_rule(char):
    rules = {
        '라': ['라', '나'], '락': ['락', '낙'], '란': ['란', '난'], '랄': ['랄', '날'], '람': ['람', '남'], '랍': ['랍', '납'], '랑': ['랑', '낭'],
        '래': ['래', '내'], '랭': ['랭', '냉'],
        '냑': ['냑', '약'], '략': ['략', '약'], '냥': ['냥', '양'], '량': ['량', '양'],
        '녀': ['녀', '여'], '려': ['려', '여'], '녁': ['녁', '역'], '력': ['력', '역'], '년': ['년', '연'], '련': ['련', '연'], '녈': ['녈', '열'], '렬': ['렬', '열'], '념': ['념', '염'], '렴': ['렴', '염'], '렵': ['렵', '엽'], '령': ['령', '영'], '녕': ['녕', '영'],
        '로': ['로', '노'], '록': ['록', '녹'], '론': ['론', '논'], '롱': ['롱', '농'],
        '뢰': ['뢰', '뇌'],
        '뇨': ['뇨', '요'], '료': ['료', '요'],
        '루': ['루', '누'],
        '뉴': ['뉴', '유'], '류': ['류', '유'], '륙': ['륙', '육'], '륜': ['륜', '윤'], '률': ['률', '율'], '륭': ['륭', '융'],
        '르': ['르', '느'], '륵': ['륵', '늑'], '른': ['른', '는'], '름': ['름', '늠'], '릉': ['릉', '능'],
        '니': ['니', '이'], '리': ['리', '이'], '린': ['린', '인'], '림': ['림', '임'], '립': ['립', '입']
    }
    return rules.get(char, [char])

def send_alert_email(current_word, last_user):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        return False, "설정 누락"

    try:
        body_text = f"현재 진행 중인 단어: {current_word}\n마지막 정답자: {last_user if last_user else '없음'}"
        msg = MIMEText(body_text)
        msg['Subject'] = "[알림] 끝말잇기 시스템 정각 리포트"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        return True, "발송 성공"
    except Exception as e:
        return False, str(e)

def send_rare_word_email(word, nickname):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        return False, "설정 누락"

    try:
        body_text = f"시청자 '{nickname}'님이 희귀 끝단어 '{word}'을(를) 입력했습니다."
        msg = MIMEText(body_text)
        msg['Subject'] = "[알림] 희귀 끝단어 감지"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        return True, "발송 성공"
    except Exception as e:
        return False, str(e)

def send_game_start_email(start_word, start_user):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver):
        return False, "설정 누락"

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        winner_text = start_user if start_user else "없음"
        
        body_text = f"현재 시간 {current_time} 에 {winner_text} 이/가 {start_word} (으)로 게임을 시작했습니다."
        msg = MIMEText(body_text)
        msg['Subject'] = "[알림] 시스템 게임 시작"
        msg['From'] = sender
        msg['To'] = receiver

        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        return True, "발송 성공"
    except Exception as e:
        return False, str(e)

def send_crash_report_email(error_msg):
    smtp_server = os.getenv("MAIL_SERVER", "smtp.naver.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))
    sender = os.getenv("MAIL_SENDER")
    password = os.getenv("MAIL_PASSWORD")
    receiver = os.getenv("MAIL_RECEIVER")

    if not (sender and password and receiver): return False
    try:
        msg = MIMEText(f"치명적 오류 발생:\n\n{error_msg}")
        msg['Subject'] = "[CRITICAL] 끝말잇기 시스템 크래시 리포트"
        msg['From'] = sender
        msg['To'] = receiver
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
        return True
    except: return False

def handle_violation_alert(nickname, word):
    # 위반 내역 자체 처리 로직
    pass

class ProfanityFilter:
    def __init__(self):
        self.bad_words = set()
        self._load_words()

    def _load_words(self):
        try:
            import sys
            base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(".")
            path = os.path.join(base_path, "bad_words.txt")
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    self.bad_words = {line.strip() for line in f if line.strip()}
        except Exception: pass

    def check(self, word):
        for bw in self.bad_words:
            if bw in word: return True, bw
        return False, None