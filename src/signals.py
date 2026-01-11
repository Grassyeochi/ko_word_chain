# src/signals.py
from PyQt6.QtCore import QObject, pyqtSignal

class GameSignals(QObject):
    # 기존 시그널
    word_detected = pyqtSignal(str, str)         
    stream_offline = pyqtSignal()                
    log_request = pyqtSignal(int, str, str, str)
    gui_log_message = pyqtSignal(str)
    
    # [신규] DB 검증 결과를 GUI 스레드로 전달하기 위한 시그널
    # 인자: result_status(str), nickname(str), word(str)
    game_check_result = pyqtSignal(str, str, str)