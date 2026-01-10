# src/signals.py
from PyQt6.QtCore import QObject, pyqtSignal

class GameSignals(QObject):
    word_detected = pyqtSignal(str, str)         
    stream_offline = pyqtSignal()                
    log_request = pyqtSignal(int, str, str, str)
    gui_log_message = pyqtSignal(str)