# src/utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText

def apply_dueum_rule(char):
    """
    두음법칙 적용 로직
    입력된 한 글자(char)에 대해 가능한 시작 글자 리스트를 반환
    """
    if not re.match(r'[가-힣]', char):
        return [char]

    base_code = ord(char) - 44032
    chosung_idx = base_code // 588
    jungsung_idx = (base_code % 588) // 28
    jongsung_idx = base_code % 28

    y_sounds = [2, 3, 6, 7, 12, 17, 20] 
    variations = [char]
    new_chosung = -1

    if chosung_idx == 5: # ㄹ
        if jungsung_idx in y_sounds:
            new_chosung = 11 # ㅇ
        else:
            new_chosung = 2  # ㄴ
    elif chosung_idx == 2: # ㄴ
        if jungsung_idx in y_sounds:
            new_chosung = 11 # ㅇ

    if new_chosung != -1:
        new_char_code = 44032 + (new_chosung * 588) + (jungsung_idx * 28) + jongsung_idx
        variations.append(chr(new_char_code))
    
    return variations

def send_alert_email(current_word):
    """
    타임아웃 알림 메일 발송 로직 (네이버 권장 465 SSL)
    """
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

        # 네이버 등 보안 메일은 SMTP_SSL (포트 465) 사용
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender, password)
            server.send_message(msg)
        
        return True, "발송 성공"
    except Exception as e:
        return False, str(e)