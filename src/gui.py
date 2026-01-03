# src/gui.py
import sys
import os
import time
import re
import asyncio
import threading
import math
import unicodedata  # [추가] 자소 분리 방지용
from datetime import timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QInputDialog, QSizePolicy, QMessageBox,
                             QPushButton, QTextEdit, QLineEdit, QStackedWidget)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QCloseEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from .signals import GameSignals
from .database import DatabaseManager
from .network import ChzzkMonitor
from .utils import apply_dueum_rule, send_alert_email
from .commands import CommandManager

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- 콘솔 윈도우 ---
class ConsoleWindow(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setWindowTitle("Console")
        self.resize(500, 400)
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
    
    def log(self, text):
        self.output_area.append(text)
        self.output_area.verticalScrollBar().setValue(self.output_area.verticalScrollBar().maximum())

    def process_command(self):
        cmd_full = self.input_line.text().strip()
        self.input_line.clear()
        if not cmd_full: return

        self.log(f"> {cmd_full}")
        result_msg = self.main_window.command_manager.execute(cmd_full)
        if result_msg:
            self.log(result_msg)

# --- 게임 종료 화면 위젯 ---
class GameOverWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black; color: white;")
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        self.lbl_title = QLabel("게임 종료")
        self.lbl_title.setFont(QFont("NanumBarunGothic", 60, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_subtitle = QLabel("더 이상 사용할 수 있는 단어가 없습니다.")
        self.lbl_subtitle.setFont(QFont("NanumBarunGothic", 20))
        self.lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_subtitle.setStyleSheet("color: #CCCCCC;")
        self.lbl_last_word = QLabel("최종 단어 : -")
        self.lbl_last_winner = QLabel("최종 단어를 사용한 시청자 : -")
        self.lbl_word_count = QLabel("제시된 단어 수 : 0")
        stats_font = QFont("NanumBarunGothic", 18)
        self.lbl_last_word.setFont(stats_font)
        self.lbl_last_winner.setFont(stats_font)
        self.lbl_word_count.setFont(stats_font)
        self.lbl_last_word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_last_winner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_word_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown = QLabel("10초 후에 다시 시작합니다....")
        self.lbl_countdown.setFont(QFont("NanumBarunGothic", 14))
        self.lbl_countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown.setStyleSheet("color: #888888; margin-top: 30px;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_subtitle)
        layout.addWidget(self.lbl_last_word)
        layout.addWidget(self.lbl_last_winner)
        layout.addWidget(self.lbl_word_count)
        layout.addWidget(self.lbl_countdown)
        self.setLayout(layout)

    def set_stats(self, word, nickname, count):
        self.lbl_last_word.setText(f"최종 단어 : {word}")
        self.lbl_last_winner.setText(f"최종 단어를 사용한 시청자 : {nickname}")
        self.lbl_word_count.setText(f"제시된 단어 수 : {count}")

    def update_countdown(self, seconds):
        self.lbl_countdown.setText(f"{seconds}초 후에 다시 시작합니다....")

# --- 메인 게임 GUI ---
class ChzzkGameGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = GameSignals()
        self.monitor = ChzzkMonitor(self.signals)
        self.db_manager = DatabaseManager()
        self.command_manager = CommandManager(self)
        
        self.start_time = time.time()
        self.last_change_time = time.time()
        self.current_word_text = ""
        
        self.input_locked = False
        self.email_sent_flag = False
        self.console_window = None
        self.answer_check_enabled = True

        self.restart_timer = QTimer(self)
        self.restart_timer.timeout.connect(self.tick_restart_countdown)
        self.countdown_val = 10

        self.init_audio()
        self.init_ui()
        self.setup_connections()
        
        self.ask_starting_word()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        self.timer.start(1000)

        asyncio.get_event_loop().create_task(self.monitor.run())

    def closeEvent(self, event: QCloseEvent):
        self.db_manager.export_all_data_to_csv()
        event.accept()

    def init_audio(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        sound_filename = "sound-effect(currect).mp3"
        sound_path = resource_path(sound_filename)
        if os.path.exists(sound_path):
            self.player.setSource(QUrl.fromLocalFile(sound_path))
            self.audio_output.setVolume(1.0)
        else:
            self.async_log_system(5, "Audio", f"효과음 파일 없음: {sound_path}")

    def init_ui(self):
        self.setWindowTitle("치지직 한국어 끝말잇기")
        self.resize(1000, 650)
        
        self.main_layout_container = QVBoxLayout(self)
        self.main_layout_container.setContentsMargins(0,0,0,0)
        
        self.stacked_widget = QStackedWidget()
        self.game_widget = QWidget()
        self.game_widget.setStyleSheet("background-color: black; color: white;")
        self.setup_game_layout(self.game_widget)
        self.game_over_widget = GameOverWidget()
        
        self.stacked_widget.addWidget(self.game_widget)
        self.stacked_widget.addWidget(self.game_over_widget)
        
        self.main_layout_container.addWidget(self.stacked_widget)
        
    def setup_game_layout(self, parent_widget):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 20)
        main_layout.setSpacing(20)

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

        bottom_layout = QHBoxLayout()
        left_bottom_layout = QVBoxLayout()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("border: 2px solid white; color: #AAAAAA; font-family: NanumBarunGothic; font-size: 12px;")
        self.btn_console = QPushButton("CONSOLE")
        self.btn_console.setFixedHeight(40)
        self.btn_console.setFont(QFont("NanumBarunGothic", 12, QFont.Weight.Bold))
        self.btn_console.setStyleSheet("QPushButton { border: 2px solid white; background-color: #333; color: white; } QPushButton:hover { background-color: #555; }")
        self.btn_console.clicked.connect(self.open_console)
        left_bottom_layout.addWidget(self.log_display)
        left_bottom_layout.addWidget(self.btn_console)

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
        self.lbl_current_word.setWordWrap(True)
        self.lbl_current_word.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        
        self.lbl_pause_status = QLabel("⛔ 정답 입력 중지됨 ⛔")
        self.lbl_pause_status.setFont(QFont("NanumBarunGothic", 30, QFont.Weight.Bold))
        self.lbl_pause_status.setStyleSheet("color: #FF4444; margin-top: 10px; margin-bottom: 10px;")
        self.lbl_pause_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pause_status.hide()

        self.lbl_next_hint = QLabel("게임 준비 중...")
        self.lbl_next_hint.setFont(QFont("NanumBarunGothic", 18))
        self.lbl_next_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_next_hint.setStyleSheet("color: #888888; margin-top: 20px;")
        
        game_display_layout.addWidget(lbl_cw_title, stretch=1)
        game_display_layout.addWidget(self.lbl_current_word, stretch=6)
        game_display_layout.addWidget(self.lbl_pause_status, stretch=1)
        game_display_layout.addWidget(self.lbl_next_hint, stretch=2)
        
        right_bottom_layout.addWidget(self.lbl_last_winner)
        right_bottom_layout.addLayout(game_display_layout)

        bottom_layout.addLayout(left_bottom_layout, stretch=3)
        bottom_layout.addLayout(right_bottom_layout, stretch=7)
        main_layout.addLayout(top_layout, stretch=2)
        main_layout.addLayout(bottom_layout, stretch=8)

        lbl_credits = QLabel("이름없는존재 제작\nMade by Nameless_Anonymous\nducldpdy@naver.com")
        lbl_credits.setFont(QFont("NanumBarunGothic", 10))
        lbl_credits.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        lbl_credits.setStyleSheet("color: #777777; margin-top: 10px;")
        main_layout.addWidget(lbl_credits)
        parent_widget.setLayout(main_layout)

    def open_console(self):
        if self.console_window is None:
            self.console_window = ConsoleWindow(self)
        self.console_window.show()

    def log_message(self, message):
        self.log_display.append(message)
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    def set_responsive_text(self, text):
        length = len(text)
        font = self.lbl_current_word.font()
        num_lines = 1
        new_size = 90
        if length > 50:
            num_lines = 6
            new_size = 25
        elif length > 30:
            num_lines = 5
            new_size = 35
        elif length > 20:
            num_lines = 4
            new_size = 45
        elif length > 12:
            num_lines = 3
            new_size = 60
        elif length > 6:
            num_lines = 2
            new_size = 75
        else:
            num_lines = 1
            new_size = 90

        if num_lines > 1:
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
        self.start_game_logic(start_word)

    def start_game_logic(self, start_word):
        self.current_word_text = start_word
        self.set_responsive_text(start_word)
        self.last_change_time = time.time()
        self.lbl_last_winner.setText("현재 단어를 맞춘 사람: -")
        self.log_display.clear()
        
        self.answer_check_enabled = True
        self.lbl_pause_status.hide()
        
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
        word_elapsed = now - self.last_change_time
        self.lbl_word_elapsed.setText(str(timedelta(seconds=int(word_elapsed))))

        if word_elapsed > 3600 and not self.email_sent_flag:
            self.email_sent_flag = True
            self.async_log_system(6, "Game", "1시간 경과, 메일 발송 시도")
            threading.Thread(target=self.thread_send_mail).start()

    def thread_send_mail(self):
        success, msg = send_alert_email(self.current_word_text)
        if success:
            self.async_log_system(1, "Mail", "알림 메일 발송 성공")
        else:
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
        if self.stacked_widget.currentIndex() == 1: return
        if not self.answer_check_enabled: return

        # [수정] 유니코드 정규화
        word = unicodedata.normalize('NFC', word)

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

        # [수정] 결과 상태 문자열 반환 (success, not_found, used, forbidden, error)
        result_status = self.db_manager.check_and_use_word(word, nickname)

        if result_status == "success":
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

            next_start_char_list = apply_dueum_rule(word[-1])
            any_word_left = False
            for char in next_start_char_list:
                if not self.db_manager.check_remaining_words(char):
                    any_word_left = True
                    break
            
            if not any_word_left:
                self.log_message(f"[시스템] 더 이상 이을 단어가 없습니다. 게임 종료!")
                self.process_game_over(word, nickname)

        elif result_status == "not_found":
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "사전에 없는 단어")
            self.log_message(f"[실패] {nickname}: {word} (단어장에 없는 단어 입니다)")
            
        elif result_status == "used":
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "이미 사용됨")
            self.log_message(f"[실패] {nickname}: {word} (이미 사용된 단어 입니다)")
            
        elif result_status == "forbidden":
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "한방단어")
            self.log_message(f"[실패] {nickname}: {word} (한방단어 입니다)")
            
        else:
            # DB 에러 등
            self.log_message(f"[오류] DB 연결 문제로 확인 불가: {word}")

    def process_game_over(self, last_word, last_winner):
        self.db_manager.export_all_data_to_csv()
        count = self.db_manager.get_used_word_count()
        self.game_over_widget.set_stats(last_word, last_winner, count)
        self.stacked_widget.setCurrentIndex(1)
        self.countdown_val = 10
        self.game_over_widget.update_countdown(self.countdown_val)
        self.restart_timer.start(1000)

    def tick_restart_countdown(self):
        self.countdown_val -= 1
        self.game_over_widget.update_countdown(self.countdown_val)
        if self.countdown_val <= 0:
            self.restart_timer.stop()
            self.restart_game_auto()

    def restart_game_auto(self):
        self.db_manager.reset_all_tables()
        start_word = self.db_manager.get_random_start_word()
        self.start_game_logic(start_word)
        self.stacked_widget.setCurrentIndex(0)