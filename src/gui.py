# src/gui.py

import sys
import os
import time
import re
import asyncio
import threading
from datetime import timedelta
import math # [추가] 올림 계산을 위해 추가

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QInputDialog, QSizePolicy, QMessageBox,
                             QPushButton, QTextEdit, QLineEdit)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# 분리된 모듈 임포트
from .signals import GameSignals
from .database import DatabaseManager
from .network import ChzzkMonitor
from .utils import apply_dueum_rule, send_alert_email

# [PyInstaller 호환용] 리소스 경로 함수
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# [새로운 클래스] 콘솔 창
class ConsoleWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Console")
        self.resize(400, 300)
        self.setStyleSheet("background-color: black; color: white; font-family: Consolas;")

        layout = QVBoxLayout()
        
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setStyleSheet("border: 1px solid #555;")
        
        self.input_line = QLineEdit()
        self.input_line.setStyleSheet("border: 1px solid #555; padding: 5px;")
        self.input_line.returnPressed.connect(self.process_command)
        
        layout.addWidget(self.output_area)
        layout.addWidget(self.input_line)
        self.setLayout(layout)
    
    def process_command(self):
        cmd = self.input_line.text().strip()
        if cmd:
            self.output_area.append(f"> {cmd}")
            # 여기에 실제 명령어 처리 로직을 추가할 수 있습니다.
            self.output_area.append(f"[시스템] 알 수 없는 명령어입니다: {cmd}")
            self.input_line.clear()

class ChzzkGameGUI(QWidget):
    def __init__(self):
        super().__init__()
        # 1. 신호 및 매니저 초기화
        self.signals = GameSignals()
        self.monitor = ChzzkMonitor(self.signals)
        self.db_manager = DatabaseManager()
        
        # 2. 게임 상태 변수
        self.start_time = time.time()
        self.last_change_time = time.time()
        self.current_word_text = ""
        
        self.input_locked = False        # 1초 쿨타임용
        self.email_sent_flag = False     # 이메일 중복 발송 방지
        self.console_window = None       # 콘솔 창 참조

        # 3. 초기화 작업 수행
        self.init_audio()
        self.init_ui()
        self.setup_connections()
        
        # 4. 시작 단어 입력 받기
        self.ask_starting_word()
        
        # 5. 타이머 시작 (1초마다 갱신)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        self.timer.start(1000)

        # 6. 비동기 모니터링 시작
        asyncio.get_event_loop().create_task(self.monitor.run())

    def init_audio(self):
        """오디오 플레이어 설정 및 리소스 로드"""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # PyInstaller 호환 경로 적용
        sound_filename = "sound-effect(currect).mp3"
        sound_path = resource_path(sound_filename)
        
        if os.path.exists(sound_path):
            self.player.setSource(QUrl.fromLocalFile(sound_path))
            self.audio_output.setVolume(1.0)
        else:
            print(f"[오류] 효과음 파일을 찾을 수 없습니다: {sound_path}")
            self.async_log_system(5, "Audio", f"효과음 파일 없음: {sound_path}")

    def init_ui(self):
        """UI 레이아웃 구성"""
        self.setWindowTitle("치지직 한국어 끝말잇기")
        self.resize(1000, 650)
        self.setStyleSheet("background-color: black; color: white;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 20)
        main_layout.setSpacing(20)

        # === 상단 레이아웃 ===
        top_layout = QHBoxLayout()
        
        self.title_label = QLabel("한국어 끝말잇기")
        self.title_label.setFont(QFont("NanumBarunGothic", 40, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        top_right_layout = QVBoxLayout()
        
        lbl_rt_title = QLabel("프로그램 런 타임")
        lbl_rt_title.setStyleSheet("background-color: #333; padding: 5px; font-weight: bold;")
        lbl_rt_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_runtime = QLabel("00:00:00")
        self.lbl_runtime.setStyleSheet("border: 1px solid white; padding: 5px;")
        self.lbl_runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_elapsed_title = QLabel("현재 단어 경과 시간")
        lbl_elapsed_title.setStyleSheet("background-color: #333; padding: 5px; margin-top: 5px; font-weight: bold;")
        lbl_elapsed_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_word_elapsed = QLabel("00:00:00")
        self.lbl_word_elapsed.setStyleSheet("border: 1px solid white; padding: 5px;")
        self.lbl_word_elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_word_elapsed.setFont(QFont("NanumBarunGothic", 12))

        top_right_layout.addWidget(lbl_rt_title)
        top_right_layout.addWidget(self.lbl_runtime)
        top_right_layout.addWidget(lbl_elapsed_title)
        top_right_layout.addWidget(self.lbl_word_elapsed)
        
        top_layout.addWidget(self.title_label, stretch=7)
        top_layout.addLayout(top_right_layout, stretch=3)

        # === 하단 레이아웃 ===
        bottom_layout = QHBoxLayout()

        # 1. 좌측 하단: 게임 사용자 로그 + CONSOLE 버튼
        left_bottom_layout = QVBoxLayout()
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("border: 2px solid white; color: #AAAAAA; font-family: NanumBarunGothic; font-size: 12px;")
        self.log_display.setPlaceholderText("게임 사용자 로그가 여기에 표시됩니다...")
        
        self.btn_console = QPushButton("CONSOLE")
        self.btn_console.setFixedHeight(40)
        self.btn_console.setFont(QFont("NanumBarunGothic", 12, QFont.Weight.Bold))
        self.btn_console.setStyleSheet("""
            QPushButton {
                border: 2px solid white;
                background-color: #333;
                color: white;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        self.btn_console.clicked.connect(self.open_console)
        
        left_bottom_layout.addWidget(self.log_display)
        left_bottom_layout.addWidget(self.btn_console)

        # 2. 우측 하단: 정답자 + 게임 표시 영역
        right_bottom_layout = QVBoxLayout()
        
        self.lbl_last_winner = QLabel("현재 단어를 맞춘 사람: -")
        self.lbl_last_winner.setFixedHeight(30)
        self.lbl_last_winner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_last_winner.setStyleSheet("background-color: #222; color: #EEEEEE; font-size: 14px; border: 1px solid #555;")

        game_display_layout = QVBoxLayout()
        game_display_layout.setContentsMargins(20, 0, 0, 0)
        game_display_layout.setSpacing(0)

        lbl_cw_title = QLabel("현재 단어")
        lbl_cw_title.setFont(QFont("NanumBarunGothic", 20))
        lbl_cw_title.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        lbl_cw_title.setStyleSheet("color: #AAAAAA; margin-bottom: 0px;")

        self.lbl_current_word = QLabel("...")
        self.lbl_current_word.setFont(QFont("NanumBarunGothic", 90, QFont.Weight.Bold))
        self.lbl_current_word.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)
        self.lbl_current_word.setStyleSheet("color: white; margin-top: 0px;") 
        # [중요] 단어가 길어질 때 줄바꿈을 코드에서 제어하므로 WordWrap은 True로 두되, setText에서 \n을 활용함
        self.lbl_current_word.setWordWrap(True)
        self.lbl_current_word.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self.lbl_next_hint = QLabel("게임 준비 중...")
        self.lbl_next_hint.setFont(QFont("NanumBarunGothic", 18))
        self.lbl_next_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_next_hint.setStyleSheet("color: #888888; margin-top: 20px;")

        game_display_layout.addWidget(lbl_cw_title, stretch=1)
        game_display_layout.addWidget(self.lbl_current_word, stretch=6)
        game_display_layout.addWidget(self.lbl_next_hint, stretch=2)

        right_bottom_layout.addWidget(self.lbl_last_winner)
        right_bottom_layout.addLayout(game_display_layout)

        bottom_layout.addLayout(left_bottom_layout, stretch=3)
        bottom_layout.addLayout(right_bottom_layout, stretch=7)

        main_layout.addLayout(top_layout, stretch=2)
        main_layout.addLayout(bottom_layout, stretch=8)

        # 3. 크레딧
        lbl_credits = QLabel("이름없는존재 제작\nMade by Nameless_Anonymous\nducldpdy@naver.com")
        lbl_credits.setFont(QFont("NanumBarunGothic", 10))
        lbl_credits.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        lbl_credits.setStyleSheet("color: #777777; margin-top: 10px;")
        
        main_layout.addWidget(lbl_credits)

        self.setLayout(main_layout)

    def open_console(self):
        """콘솔 창 열기"""
        if self.console_window is None:
            self.console_window = ConsoleWindow()
        self.console_window.show()

    def log_message(self, message):
        """게임 사용자 로그에 메시지 추가"""
        self.log_display.append(message)
        scrollbar = self.log_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def set_responsive_text(self, text):
        """
        [수정됨] 글자 수에 따라 폰트 크기와 줄바꿈을 동적으로 조절
        - 최대 80글자, 최대 6줄(5번 줄바꿈) 지원
        """
        length = len(text)
        font = self.lbl_current_word.font()
        
        # 기본값 (짧은 단어)
        num_lines = 1
        new_size = 90

        # 길이별 구간 설정 (요구사항: 최대 6줄)
        if length > 50:       # 51~80자 -> 6줄
            num_lines = 6
            new_size = 25     # 아주 긴 단어는 폰트 대폭 축소
        elif length > 30:     # 31~50자 -> 5줄
            num_lines = 5
            new_size = 35
        elif length > 20:     # 21~30자 -> 4줄
            num_lines = 4
            new_size = 45
        elif length > 12:     # 13~20자 -> 3줄
            num_lines = 3
            new_size = 60
        elif length > 6:      # 7~12자  -> 2줄
            num_lines = 2
            new_size = 75
        else:                 # 1~6자   -> 1줄
            num_lines = 1
            new_size = 90

        # 줄바꿈(\n) 삽입 로직
        if num_lines > 1:
            # 텍스트를 균등하게 나누기 위해 청크(chunk) 크기 계산 (올림 처리)
            # 예: 80글자 / 6줄 = 13.33 -> 14글자씩 자름
            chunk_size = math.ceil(length / num_lines)
            
            chunks = []
            for i in range(0, length, chunk_size):
                chunks.append(text[i:i+chunk_size])
            
            formatted_text = "\n".join(chunks)
        else:
            formatted_text = text

        font.setPointSize(new_size)
        self.lbl_current_word.setFont(font)
        self.lbl_current_word.setText(formatted_text)

    def ask_starting_word(self):
        text, ok = QInputDialog.getText(self, '게임 설정', '시작 단어를 입력하세요:')
        if ok and text and re.fullmatch(r'[가-힣]+', text.strip()):
            start_word = text.strip()
        else:
            start_word = "시작"

        self.current_word_text = start_word
        self.set_responsive_text(start_word)
        self.last_change_time = time.time()
        self.async_log_system(1, "Game", f"게임 시작 (시작 단어: {start_word})")
        
        self.update_hint(start_word[-1])
        self.log_message(f"[시스템] 게임 시작! 시작 단어: {start_word}")

    def setup_connections(self):
        self.signals.word_detected.connect(self.handle_new_word)
        self.signals.stream_offline.connect(self.handle_stream_offline)
        self.signals.log_request.connect(self.async_log_system)

    def handle_stream_offline(self):
        self.async_log_system(10, "Game", "방송 오프라인 감지로 종료")
        QMessageBox.critical(self, "연결 실패", "현재 방송이 시작되지 않았습니다.\n방송을 켠 후 다시 실행해주세요.")
        sys.exit()

    def update_runtime(self):
        now = time.time()
        total_elapsed = int(now - self.start_time)
        self.lbl_runtime.setText(str(timedelta(seconds=total_elapsed)))
        
        word_elapsed_time = now - self.last_change_time
        word_elapsed_int = int(word_elapsed_time)
        self.lbl_word_elapsed.setText(str(timedelta(seconds=word_elapsed_int)))

        # 1시간(3600초) 초과 시 메일 발송
        if word_elapsed_time > 3600 and not self.email_sent_flag:
            self.email_sent_flag = True  # 중복 발송 방지
            self.async_log_system(6, "Game", "1시간 경과, 메일 발송 시도")
            threading.Thread(target=self.thread_send_mail).start()

    def thread_send_mail(self):
        success, msg = send_alert_email(self.current_word_text)
        if success:
            print("[시스템] 메일 발송 성공")
            self.async_log_system(1, "Mail", "알림 메일 발송 성공")
        else:
            print(f"[오류] 메일 발송 실패: {msg}")
            self.async_log_system(8, "Mail", "메일 발송 실패", msg)

    def update_hint(self, last_char):
        valid_starts = apply_dueum_rule(last_char)
        hint_str = ", ".join([f"!{c}..." for c in valid_starts])
        self.lbl_next_hint.setText(f"다음 글자: '{last_char}' (가능: {hint_str})")
        
    def unlock_input(self):
        self.input_locked = False

    def async_log_system(self, level, source, message, trace=None):
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self.db_manager.log_system, level, source, message, trace)

    def async_log_history(self, nickname, input_word, previous_word, status, reason=None):
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self.db_manager.log_history, nickname, input_word, previous_word, status, reason)
    
    def play_success_sound(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        self.player.play()

    def handle_new_word(self, nickname, word):
        if self.input_locked: return
        if len(word) < 1: return

        if not re.fullmatch(r'[가-힣]+', word):
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "한글 아님")
            self.log_message(f"[실패] {nickname}: {word} (한글 아님)")
            return

        if self.current_word_text:
            last_char = self.current_word_text[-1]
            first_char = word[0]
            valid_starts = apply_dueum_rule(last_char)
            
            if first_char not in valid_starts:
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "끝말잇기 규칙 위반")
                self.log_message(f"[실패] {nickname}: {word} (초성 불일치)")
                return

        is_success_db = self.db_manager.check_and_use_word(word, nickname)

        if is_success_db:
            self.input_locked = True
            QTimer.singleShot(1000, self.unlock_input)
            self.play_success_sound()
            self.async_log_history(nickname, word, self.current_word_text, "Success")

            self.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {nickname}")
            self.log_message(f"[성공] {nickname}: {word}")

            self.current_word_text = word
            self.set_responsive_text(word)
            self.last_change_time = time.time()
            self.email_sent_flag = False 
            
            self.update_runtime()
            self.update_hint(word[-1])
        else:
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "이미 사용된 단어 또는 DB 없음")
            self.log_message(f"[실패] {nickname}: {word} (이미 사용됨/DB 없음)")
            print(f"[게임] '{word}' - 유효하지 않거나 이미 사용된 단어입니다.")