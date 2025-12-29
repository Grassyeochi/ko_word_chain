# src/signals.py
from PyQt6.QtCore import QObject, pyqtSignal

class GameSignals(QObject):
    """
    GUI와 네트워크, 기타 로직 간의 통신을 담당하는 신호 클래스
    """
    word_detected = pyqtSignal(str, str)         # 닉네임, 단어
    stream_offline = pyqtSignal()                # 방송 오프라인 감지
    log_request = pyqtSignal(int, str, str, str) # 로그 레벨, 소스, 메시지, 트레이스