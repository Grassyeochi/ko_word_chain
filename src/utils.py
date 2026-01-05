# src/utils.py
import re
import os
import smtplib
from email.mime.text import MIMEText

def apply_dueum_rule(char):
    """
    두음법칙 적용 로직 (확장판)
    입력된 한 글자(char)에 대해 가능한 모든 시작 글자 리스트를 반환
    예: '름' -> ['름', '늠', '음']
    """
    if not re.match(r'[가-힣]', char):
        return [char]

    base_code = ord(char) - 44032
    chosung_idx = base_code // 588
    jungsung_idx = (base_code % 588) // 28
    jongsung_idx = base_code % 28

    # 'ㄹ'이 'ㅇ'으로 변하는 모음들 (야, 여, 요, 유, 이, 예, 얘 등)
    y_sounds = [2, 3, 6, 7, 12, 17, 20] 
    # 'ㄹ'이 'ㄴ'과 'ㅇ' 모두 허용되는 모음 (ㅡ) - 사용자 요청
    dual_sounds = [18] 

    variations = [char] # 원본 단어 포함 (예: 름)
    
    # 변환될 초성 인덱스들을 담을 리스트
    target_chosungs = []

    if chosung_idx == 5: # 초성 'ㄹ'
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) # -> 'ㅇ' (량->양)
        elif jungsung_idx in dual_sounds:
            # [수정] 'ㅡ' 모음일 경우 'ㄴ'과 'ㅇ' 둘 다 추가
            target_chosungs.append(2)  # -> 'ㄴ' (름->늠)
            target_chosungs.append(11) # -> 'ㅇ' (름->음)
        else:
            target_chosungs.append(2)  # -> 'ㄴ' (로->노)
            
    elif chosung_idx == 2: # 초성 'ㄴ'
        if jungsung_idx in y_sounds:
            target_chosungs.append(11) # -> 'ㅇ' (녀->여)

    # 계산된 초성들로 글자 생성 및 추가
    for new_chosung in target_chosungs:
        new_char_code = 44032 + (new_chosung * 588) + (jungsung_idx * 28) + jongsung_idx
        new_char = chr(new_char_code)
        if new_char not in variations:
            variations.append(new_char)
    
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