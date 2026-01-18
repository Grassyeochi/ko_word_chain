# src/signals.py
from PyQt6.QtCore import QObject, pyqtSignal

class GameSignals(QObject):
    # 네트워크 -> GUI: 채팅 감지 (플랫폼, 닉네임, 단어)
    word_detected = pyqtSignal(str, str, str)         
    
    # 네트워크 -> GUI: 방송 종료 감지 (신호 보낸 플랫폼 이름)
    stream_offline = pyqtSignal(str)                
    
    # 네트워크 -> GUI: 방송 연결 성공 (신호 보낸 플랫폼 이름)
    stream_connected = pyqtSignal(str)
    
    # 시스템 -> DB: 로그 저장 요청
    log_request = pyqtSignal(int, str, str, str)
    
    # 시스템 -> GUI: 화면 로그 출력
    gui_log_message = pyqtSignal(str)
    
    # 백그라운드 스레드 -> GUI: 단어 검증 결과 (플랫폼 추가)
    # 인자: result_status(str), platform(str), nickname(str), word(str), is_game_over(bool)
    game_check_result = pyqtSignal(str, str, str, str, bool)