# src/signals.py
from PyQt6.QtCore import QObject, pyqtSignal

class GameSignals(QObject):
    # 네트워크 -> GUI: 채팅 감지 (플랫폼, 닉네임, 단어)
    word_detected = pyqtSignal(str, str, str)         
    
    # 네트워크 -> GUI: 방송 종료/끊김 감지 (플랫폼)
    stream_offline = pyqtSignal(str)                
    
    # 네트워크 -> GUI: 방송 연결 성공 (플랫폼)
    stream_connected = pyqtSignal(str)
    
    # 시스템 -> DB: DB 로그 저장 요청
    log_request = pyqtSignal(int, str, str, str)
    
    # 시스템 -> GUI: 화면 로그 텍스트 출력
    gui_log_message = pyqtSignal(str)
    
    # DB 백그라운드 스레드 -> GUI: 단어 검증 결과 리턴
    # (결과상태, 플랫폼, 닉네임, 입력단어, 게임종료여부)
    game_check_result = pyqtSignal(str, str, str, str, bool)