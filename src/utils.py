# src/utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText

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

    if chosung_idx == 5: # ㄹ
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) # ㅇ
        elif jungsung_idx in dual_sounds:
            target_chosungs.append(2)  # ㄴ
            target_chosungs.append(11) # ㅇ
        else:
            target_chosungs.append(2)  # ㄴ
            
    elif chosung_idx == 2: # ㄴ
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) # ㅇ

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