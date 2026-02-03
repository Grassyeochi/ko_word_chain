# src/gui.py
import sys
import os
import time
import re
import asyncio
import threading
import math
import unicodedata
import traceback 
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QSizePolicy, QMessageBox, QGridLayout,
                             QPushButton, QTextEdit, QLineEdit, QStackedWidget,
                             QDialog, QProgressBar, QApplication)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, QRect
from PyQt6.QtGui import QFont, QCloseEvent, QFontMetrics
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from .signals import GameSignals
from .database import DatabaseManager
from .network import ChzzkMonitor, YouTubeMonitor
from .utils import apply_dueum_rule, send_alert_email, ProfanityFilter, update_env_variable, log_unknown_word, handle_violation_alert, send_crash_report_email
from .commands import CommandManager

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print("[CRITICAL] 치명적인 오류 발생!")
    print(error_msg)
    if not issubclass(exctype, SystemExit):
        send_crash_report_email(error_msg)
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

# --- 0. 종료 알림 다이얼로그 ---
class ShutdownDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setStyleSheet("""
            QDialog { background-color: #222222; border: 2px solid #555555; border-radius: 10px; }
            QLabel { color: white; font-family: 'NanumBarunGothic'; }
        """)
        self.resize(300, 100)
        self.setModal(True)
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title = QLabel("프로그램 종료 중...")
        self.lbl_title.setFont(QFont("NanumBarunGothic", 14, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status = QLabel("대기 중...")
        self.lbl_status.setFont(QFont("NanumBarunGothic", 10))
        self.lbl_status.setStyleSheet("color: #AAAAAA; margin-top: 5px;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_status)
        self.setLayout(layout)

    def set_status(self, text):
        self.lbl_status.setText(text)
        QApplication.processEvents()

# --- 1. 시스템 사전 점검 다이얼로그 ---
class StartupCheckDialog(QDialog):
    check_finished_signal = pyqtSignal(bool, str, bool, str, bool, str, bool, str)

    def __init__(self, chzzk_monitor, youtube_monitor, db_manager):
        super().__init__()
        self.setWindowTitle("시스템 사전 점검")
        self.resize(600, 300)
        self.chzzk = chzzk_monitor
        self.youtube = youtube_monitor
        self.db = db_manager
        
        self.use_chzzk = False
        self.use_youtube = False
        
        self.check_finished_signal.connect(self._on_check_finished)

        layout = QVBoxLayout()
        
        self.lbl_chzzk = QLabel("치지직 확인 중...")
        self.lbl_chzzk.setFont(QFont("NanumBarunGothic", 12))
        layout.addWidget(self.lbl_chzzk)

        self.lbl_yt = QLabel("유튜브 확인 중...")
        self.lbl_yt.setFont(QFont("NanumBarunGothic", 12))
        layout.addWidget(self.lbl_yt)
        
        self.lbl_db = QLabel("DB 연결 확인 중...")
        self.lbl_db.setFont(QFont("NanumBarunGothic", 12))
        layout.addWidget(self.lbl_db)

        self.lbl_env = QLabel("환경변수(날짜) 확인 중...")
        self.lbl_env.setFont(QFont("NanumBarunGothic", 12))
        layout.addWidget(self.lbl_env)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        
        btn_layout = QHBoxLayout()
        self.btn_retry = QPushButton("다시 검사")
        self.btn_retry.clicked.connect(self.run_checks)
        
        self.btn_next = QPushButton("다음 단계로")
        self.btn_next.clicked.connect(self.accept)
        self.btn_next.setEnabled(False) 
        
        btn_layout.addWidget(self.btn_retry)
        btn_layout.addWidget(self.btn_next)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        QTimer.singleShot(100, self.run_checks)

    def run_checks(self):
        self.progress.setRange(0, 0)
        self.btn_next.setEnabled(False)
        self.lbl_chzzk.setText("치지직 확인 중...")
        self.lbl_yt.setText("유튜브 확인 중...")
        self.lbl_db.setText("DB 연결 확인 중...")
        self.lbl_env.setText("환경변수(날짜) 확인 중...")
        for lbl in [self.lbl_chzzk, self.lbl_yt, self.lbl_db, self.lbl_env]:
            lbl.setStyleSheet("color: black;")
        threading.Thread(target=self._check_logic_thread, daemon=True).start()

    def _check_logic_thread(self):
        chzzk_ok, chzzk_msg = self.chzzk.check_live_status_sync()
        yt_ok, yt_msg = self.youtube.check_live_status_sync()
        is_db_ok, msg_db = self.db.test_db_integrity()
        is_env_ok = False
        env_msg = ""
        env_date_str = os.getenv("db_reset_time")
        if not env_date_str:
            env_msg = "환경변수(db_reset_time) 없음"
        else:
            try:
                env_dt = datetime.strptime(env_date_str, "%Y.%m.%d %H:%M:%S")
                now = datetime.now()
                if env_dt > now: env_msg = f"미래 날짜 감지 ({env_date_str})"
                else:
                    env_msg = f"날짜 정상 ({env_date_str})"
                    is_env_ok = True
            except ValueError:
                env_msg = f"날짜 형식 오류 ({env_date_str})"
        self.check_finished_signal.emit(chzzk_ok, chzzk_msg, yt_ok, yt_msg, is_db_ok, msg_db, is_env_ok, env_msg)

    def _on_check_finished(self, chzzk_ok, chzzk_msg, yt_ok, yt_msg, is_db_ok, msg_db, is_env_ok, env_msg):
        style_ok = "color: green; font-weight: bold;"
        style_no = "color: red; font-weight: bold;"
        
        if chzzk_ok:
            self.lbl_chzzk.setText(f"✔ 치지직: {chzzk_msg}")
            self.lbl_chzzk.setStyleSheet(style_ok)
            self.use_chzzk = True
        else:
            self.lbl_chzzk.setText(f"❌ 치지직: {chzzk_msg}")
            self.lbl_chzzk.setStyleSheet(style_no)
            self.use_chzzk = False

        if yt_ok:
            self.lbl_yt.setText(f"✔ 유튜브: {yt_msg}")
            self.lbl_yt.setStyleSheet(style_ok)
            self.use_youtube = True
        else:
            self.lbl_yt.setText(f"❌ 유튜브: {yt_msg}")
            self.lbl_yt.setStyleSheet(style_no)
            self.use_youtube = False

        if is_db_ok:
            self.lbl_db.setText(f"✔ DB 상태: {msg_db}")
            self.lbl_db.setStyleSheet(style_ok)
        else:
            self.lbl_db.setText(f"❌ DB 상태: {msg_db}")
            self.lbl_db.setStyleSheet(style_no)

        if is_env_ok:
            self.lbl_env.setText(f"✔ {env_msg}")
            self.lbl_env.setStyleSheet(style_ok)
        else:
            self.lbl_env.setText(f"❌ {env_msg}")
            self.lbl_env.setStyleSheet(style_no)

        self.progress.setRange(0, 100)
        self.progress.setValue(100)

        if is_db_ok and is_env_ok and (self.use_chzzk or self.use_youtube):
            self.btn_next.setEnabled(True)

# --- 2. 시작 단어 설정 다이얼로그 ---
class StartWordOptionDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("시작 단어 설정")
        self.resize(350, 250)
        self.selected_mode = None 
        self.input_text = ""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        lbl_info = QLabel("게임을 시작할 단어를 선택하세요.")
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_info)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("직접 입력 (비워두면 '시작')")
        layout.addWidget(self.input_edit)
        self.btn_ok = QPushButton("OK (입력값으로 시작)")
        self.btn_ok.clicked.connect(self.on_ok)
        layout.addWidget(self.btn_ok)
        self.btn_random = QPushButton("무작위 단어 (DB)")
        self.btn_random.clicked.connect(self.on_random)
        layout.addWidget(self.btn_random)
        self.btn_recent = QPushButton("최근 사용한 단어 (DB)")
        self.btn_recent.clicked.connect(self.on_recent)
        layout.addWidget(self.btn_recent)
        self.btn_cancel = QPushButton("Cancel (종료)")
        self.btn_cancel.setStyleSheet("color: red;")
        self.btn_cancel.clicked.connect(self.reject)
        layout.addWidget(self.btn_cancel)
        self.setLayout(layout)
    def on_ok(self):
        self.selected_mode = "INPUT"
        self.input_text = self.input_edit.text().strip()
        self.accept()
    def on_random(self):
        self.selected_mode = "RANDOM"
        self.accept()
    def on_recent(self):
        self.selected_mode = "RECENT"
        self.accept()

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
        if result_msg: self.log(result_msg)

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
        self.chzzk_monitor = ChzzkMonitor(self.signals)
        self.youtube_monitor = YouTubeMonitor(self.signals)
        self.db_manager = DatabaseManager()
        self.command_manager = CommandManager(self)
        self.profanity_filter = ProfanityFilter()
        
        self.start_time = None 
        self.program_start_dt = datetime.now() 
        self.last_change_time = time.time()
        self.current_word_text = ""
        
        self.use_chzzk = False
        self.use_youtube = False
        self.platform_status = {}
        self.is_global_offline = False

        self.current_fail_count = 0
        self.last_platform = None
        self.last_user = None

        self.db_reset_date = os.getenv("db_reset_time", "알 수 없음")
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
        
        QTimer.singleShot(100, self.run_startup_sequence)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        self.timer.start(1000)

    def start_monitor_service(self):
        loop = asyncio.get_event_loop()
        if self.use_chzzk:
            loop.create_task(self.chzzk_monitor.run())
            self.platform_status['치지직'] = False 
        
        if self.use_youtube:
            loop.create_task(self.youtube_monitor.run())
            self.platform_status['유튜브'] = False

    def run_startup_sequence(self):
        check_dlg = StartupCheckDialog(self.chzzk_monitor, self.youtube_monitor, self.db_manager)
        if check_dlg.exec() != QDialog.DialogCode.Accepted:
            sys.exit() 
        
        self.use_chzzk = check_dlg.use_chzzk
        self.use_youtube = check_dlg.use_youtube

        word_dlg = StartWordOptionDialog()
        start_user = None 
        
        if word_dlg.exec() == QDialog.DialogCode.Accepted:
            mode = word_dlg.selected_mode
            start_word = "시작"
            if mode == "INPUT":
                text = word_dlg.input_text
                if text and re.fullmatch(r'[가-힣]+', text):
                    start_word = text
            elif mode == "RANDOM":
                start_word = self.db_manager.get_random_start_word()
            elif mode == "RECENT":
                ret = self.db_manager.get_last_used_word()
                if isinstance(ret, tuple):
                    start_word = ret[0]
                    start_user = ret[1]
                else:
                    start_word = str(ret)
                    start_user = None
            
            self.start_monitor_service()
            self.start_game_logic(start_word, start_user=start_user, restore_time=False)
        else:
            sys.exit()

    def closeEvent(self, event: QCloseEvent):
        shutdown_dlg = ShutdownDialog()
        shutdown_dlg.show()
        
        self.db_manager.end_game_session(
            self.current_fail_count,
            self.current_word_text,
            self.last_platform,
            self.last_user
        )

        shutdown_dlg.set_status("로그 및 데이터 백업 중...")
        self.db_manager.export_all_data_to_csv()
        time.sleep(0.5) 
        shutdown_dlg.set_status("데이터베이스 연결 해제 중...")
        if self.db_manager.conn:
            try: self.db_manager.conn.close()
            except: pass
        time.sleep(0.3)
        shutdown_dlg.set_status("프로그램을 종료합니다.")
        time.sleep(0.3)
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
        self.setWindowTitle("치지직/유튜브 한국어 끝말잇기")
        self.setFixedSize(1200, 700)
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
        main_layout = QHBoxLayout() 
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(30)
        # Left
        left_layout = QVBoxLayout()
        self.title_label = QLabel("한국어 끝말잇기")
        self.title_label.setFont(QFont("NanumBarunGothic", 50, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        left_layout.addWidget(self.title_label)
        self.subtitle_label = QLabel("치지직 / 유튜브 동시송출 - 동시참여")
        self.subtitle_label.setFont(QFont("NanumBarunGothic", 18))
        self.subtitle_label.setStyleSheet("color: #CCCCCC; margin-bottom: 10px;") 
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        left_layout.addWidget(self.subtitle_label)
        left_layout.addStretch(1)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("""
            border: 2px solid white; 
            color: #AAAAAA; 
            font-family: NanumBarunGothic; 
            font-size: 14px;
            background-color: #111;
        """)
        left_layout.addWidget(self.log_display, stretch=5)
        self.btn_console = QPushButton("CONSOLE")
        self.btn_console.setFixedHeight(50)
        self.btn_console.setFont(QFont("NanumBarunGothic", 14, QFont.Weight.Bold))
        self.btn_console.setStyleSheet("""
            QPushButton { border: 2px solid white; background-color: #333; color: white; } 
            QPushButton:hover { background-color: #555; }
        """)
        self.btn_console.clicked.connect(self.open_console)
        left_layout.addWidget(self.btn_console)
        # Right
        right_layout = QVBoxLayout()
        info_grid = QGridLayout()
        info_grid.setSpacing(15)
        lbl_style_title = "background-color: #333; padding: 8px; font-weight: bold; font-size: 14px; color: #EEE;"
        lbl_style_val = "border: 1px solid white; padding: 8px; font-size: 14px; color: white;"
        lb_rt = QLabel("프로그램 런 타임")
        lb_rt.setStyleSheet(lbl_style_title)
        lb_rt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_runtime = QLabel("-")
        self.lbl_runtime.setStyleSheet(lbl_style_val)
        self.lbl_runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_reset = QLabel("사용된 단어 목록 초기화 된 시간")
        lb_reset.setStyleSheet(lbl_style_title)
        lb_reset.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_reset_time = QLabel(self.db_reset_date)
        self.lbl_reset_time.setStyleSheet(lbl_style_val)
        self.lbl_reset_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_elapsed = QLabel("현재 단어 경과 시간")
        lb_elapsed.setStyleSheet(lbl_style_title)
        lb_elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_word_elapsed = QLabel("00:00:00")
        self.lbl_word_elapsed.setStyleSheet(lbl_style_val)
        self.lbl_word_elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lb_count = QLabel("이번 게임에서 제시된 단어 수")
        lb_count.setStyleSheet(lbl_style_title)
        lb_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_word_count = QLabel("0")
        self.lbl_word_count.setStyleSheet(lbl_style_val)
        self.lbl_word_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_grid.addWidget(lb_rt, 0, 0)
        info_grid.addWidget(lb_reset, 0, 1)
        info_grid.addWidget(self.lbl_runtime, 1, 0)
        info_grid.addWidget(self.lbl_reset_time, 1, 1)
        info_grid.addWidget(lb_elapsed, 2, 0)
        info_grid.addWidget(lb_count, 2, 1)
        info_grid.addWidget(self.lbl_word_elapsed, 3, 0)
        info_grid.addWidget(self.lbl_word_count, 3, 1)
        right_layout.addLayout(info_grid)
        right_layout.addSpacing(30)
        self.lbl_last_winner = QLabel("현재 단어를 맞춘 사람: -")
        self.lbl_last_winner.setFixedHeight(40)
        self.lbl_last_winner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_last_winner.setStyleSheet("background-color: #222; color: #EEE; font-size: 16px; border: 1px solid #555;")
        right_layout.addWidget(self.lbl_last_winner)
        game_area = QVBoxLayout()
        game_area.addStretch(1)
        lbl_cw_title = QLabel("현재 단어")
        lbl_cw_title.setFont(QFont("NanumBarunGothic", 24))
        lbl_cw_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_cw_title.setStyleSheet("color: #AAA;")
        self.lbl_current_word = QLabel("...")
        self.lbl_current_word.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        # [수정] 기본 폰트 크기 100으로 시작
        self.lbl_current_word.setFont(QFont("NanumBarunGothic", 100, QFont.Weight.Bold))
        self.lbl_current_word.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_current_word.setStyleSheet("color: white;")
        self.lbl_current_word.setWordWrap(True)
        self.lbl_pause_status = QLabel("⛔ 정답 입력 중지됨 ⛔")
        self.lbl_pause_status.setFont(QFont("NanumBarunGothic", 30, QFont.Weight.Bold))
        self.lbl_pause_status.setStyleSheet("color: #FF4444;")
        self.lbl_pause_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pause_status.hide()
        self.lbl_next_hint = QLabel("다음 단어")
        self.lbl_next_hint.setFont(QFont("NanumBarunGothic", 20))
        self.lbl_next_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_next_hint.setStyleSheet("color: #888;")
        game_area.addWidget(lbl_cw_title)
        
        # [유지] 공간 확보를 위해 비율 3 적용
        game_area.addWidget(self.lbl_current_word, 3)
        
        game_area.addWidget(self.lbl_pause_status)
        game_area.addWidget(self.lbl_next_hint)
        game_area.addStretch(1)
        right_layout.addLayout(game_area, stretch=1)
        lbl_credits = QLabel("이름없는존재 제작\nMade by Nameless_Anonymous\nducldpdy@naver.com")
        lbl_credits.setFont(QFont("NanumBarunGothic", 10))
        lbl_credits.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        lbl_credits.setStyleSheet("color: #777;")
        right_layout.addWidget(lbl_credits)
        main_layout.addLayout(left_layout, stretch=3) 
        main_layout.addLayout(right_layout, stretch=7) 
        parent_widget.setLayout(main_layout)

    def open_console(self):
        if self.console_window is None:
            self.console_window = ConsoleWindow(self)
        self.console_window.show()

    def log_message(self, message):
        self.log_display.append(message)
        self.log_display.verticalScrollBar().setValue(self.log_display.verticalScrollBar().maximum())

    # [수정] 6글자 단위 줄바꿈 및 오버플로우 방지 로직 (Auto-Shrink)
    def set_responsive_text(self, text):
        if not text: return
        length = len(text)
        
        # 1. 6글자 단위로 텍스트 분할 (무조건)
        chunk_size = 6
        chunks = [text[i:i+chunk_size] for i in range(0, length, chunk_size)]
        formatted_text = "\n".join(chunks)
        num_lines = len(chunks)

        # 2. 시작 폰트 크기 설정 (기존보다 더 보수적으로 잡음)
        if num_lines == 1: target_size = 100
        elif num_lines == 2: target_size = 65 
        elif num_lines == 3: target_size = 45 
        else: target_size = 30
        
        # 3. 오버플로우 방지 로직 (Auto-Shrink)
        # 라벨의 현재 크기를 가져옵니다.
        label_w = self.lbl_current_word.width()
        label_h = self.lbl_current_word.height()
        
        # 윈도우가 아직 안 떠서 크기가 0일 경우, 고정된 크기(1200x700) 기반으로 대략적인 가용 영역 추정
        # 레이아웃 비율이 3:5 정도 되므로 높이는 대략 300~400px, 너비는 600px 정도 예상
        if label_w < 10 or label_h < 10:
            label_w = 600
            label_h = 300

        font = self.lbl_current_word.font()
        font.setPointSize(target_size)
        fm = QFontMetrics(font)
        
        # 텍스트가 들어갈 영역 계산 (Padding 고려)
        # boundingRect(rect, flags, text) 사용 시 정렬 플래그 포함
        bound_rect = fm.boundingRect(0, 0, label_w, label_h, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, formatted_text)
        
        # 영역을 벗어나면 폰트 크기 줄이기 루프 (최소 10pt까지)
        while (bound_rect.height() > label_h or bound_rect.width() > label_w) and target_size > 10:
            target_size -= 5
            font.setPointSize(target_size)
            fm = QFontMetrics(font)
            bound_rect = fm.boundingRect(0, 0, label_w, label_h, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, formatted_text)
        
        self.lbl_current_word.setFont(font)
        self.lbl_current_word.setText(formatted_text)

    def start_game_logic(self, start_word, start_user=None, restore_time=False):
        if isinstance(start_word, (tuple, list)):
            if start_word:
                start_word = str(start_word[0])
            else:
                start_word = "시작"

        self.start_time = time.time()
        self.current_word_text = start_word
        
        self.current_fail_count = 0
        self.db_manager.start_new_game_session(start_word)
        
        self.set_responsive_text(start_word)
        self.lbl_current_word.repaint()     
        QApplication.processEvents()        
        if restore_time:
            saved_str = os.getenv("last_word_change_time")
            if saved_str:
                try:
                    dt = datetime.strptime(saved_str, "%Y.%m.%d %H:%M:%S")
                    self.last_change_time = dt.timestamp()
                except ValueError: self.last_change_time = time.time()
            else: self.last_change_time = time.time()
        else: self.last_change_time = time.time()
        curr_dt_str = datetime.fromtimestamp(self.last_change_time).strftime("%Y.%m.%d %H:%M:%S")
        update_env_variable("last_word_change_time", curr_dt_str)

        if start_user:
            self.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {start_user}")
        else:
            self.lbl_last_winner.setText("현재 단어를 맞춘 사람: -")

        self.log_display.clear()
        self.answer_check_enabled = True
        self.lbl_pause_status.hide()
        count = self.db_manager.get_used_word_count()
        self.lbl_word_count.setText(str(count))
        self.async_log_system(1, "Game", f"게임 시작 (시작 단어: {start_word})")
        self.update_hint(start_word[-1])
        self.log_message(f"[시스템] 게임 시작! 시작 단어: {start_word}")

    def setup_connections(self):
        self.signals.word_detected.connect(self.handle_new_word)
        self.signals.stream_offline.connect(self.handle_stream_offline)
        self.signals.stream_connected.connect(self.handle_stream_connected)
        self.signals.log_request.connect(self.async_log_system)
        self.signals.gui_log_message.connect(self.log_message)
        self.signals.game_check_result.connect(self.on_word_check_finished)

    def handle_stream_offline(self, platform_name):
        if platform_name in self.platform_status:
            self.platform_status[platform_name] = False
        
        active_platforms = [p for p in self.platform_status.keys()]
        if not active_platforms: return 

        any_alive = any(self.platform_status.values())

        if not any_alive:
            if not self.is_global_offline:
                self.is_global_offline = True
                self.async_log_system(10, "Game", "모든 방송 연결 끊김. 대기 모드 진입.")
                self.lbl_current_word.setText("방송 연결 대기 중...")
                self.lbl_current_word.setStyleSheet("color: orange; font-size: 50px;")
                self.log_message("[시스템] 모든 방송 연결이 끊겼습니다. 재접속 대기 중...")
        else:
            self.log_message(f"[시스템] {platform_name} 연결 불안정. 재접속 시도 중...")

    def handle_stream_connected(self, platform_name):
        was_connected = self.platform_status.get(platform_name, False)
        
        if not was_connected:
            self.log_message(f"[시스템] {platform_name} 방송 연결됨.")
            self.platform_status[platform_name] = True

        if self.is_global_offline:
            self.is_global_offline = False
            self.lbl_current_word.setStyleSheet("color: white;")
            self.set_responsive_text(self.current_word_text)
            self.log_message("[시스템] 방송 연결 복구. 게임 재개.")

    def update_runtime(self):
        if self.start_time is None:
            start_str = self.program_start_dt.strftime("%Y.%m.%d %H:%M:%S")
            self.lbl_runtime.setText(f"{start_str} - 00:00:00")
            return
        now_ts = time.time()
        total_elapsed_sec = int(now_ts - self.start_time)
        total_delta = timedelta(seconds=total_elapsed_sec)
        start_str = self.program_start_dt.strftime("%Y.%m.%d %H:%M:%S")
        self.lbl_runtime.setText(f"{start_str} - {str(total_delta)}")
        word_elapsed = now_ts - self.last_change_time
        self.lbl_word_elapsed.setText(str(timedelta(seconds=int(word_elapsed))))
        if word_elapsed > 3600 and not self.email_sent_flag:
            self.email_sent_flag = True
            self.async_log_system(6, "Game", "1시간 경과, 메일 발송 시도")
            threading.Thread(target=self.thread_send_mail).start()

    def thread_send_mail(self):
        success, msg = send_alert_email(self.current_word_text)
        if success: self.async_log_system(1, "Mail", "알림 메일 발송 성공")
        else: self.async_log_system(8, "Mail", "메일 발송 실패", msg)

    def update_hint(self, last_char):
        valid_starts = apply_dueum_rule(last_char)
        hint_str = ", ".join([f"!{c}..." for c in valid_starts])
        self.lbl_next_hint.setText(f"다음 글자: '{last_char}' (가능: {hint_str})")
        
    def unlock_input(self):
        self.input_locked = False

    def async_log_system(self, level, source, message, trace=None):
        threading.Thread(target=self.db_manager.log_system, args=(level, source, message, trace)).start()

    def async_log_history(self, nickname, input_word, previous_word, status, reason=None):
        threading.Thread(target=self.db_manager.log_history, args=(nickname, input_word, previous_word, status, reason)).start()
    
    def play_success_sound(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        self.player.play()

    def handle_new_word(self, platform, nickname, word):
        if self.input_locked: return
        if self.stacked_widget.currentIndex() == 1: return
        if not self.answer_check_enabled: return
        if self.is_global_offline: return

        word = unicodedata.normalize('NFC', word)

        is_bad, bad_word = self.profanity_filter.check(word)
        if is_bad:
            self.current_fail_count += 1
            self.log_message(f"[차단] {platform} - {nickname}: {word} (금지어: {bad_word})")
            self.async_log_history(nickname, word, self.current_word_text, "Fail", f"금지어({bad_word})")
            threading.Thread(target=self.db_manager.mark_word_as_forbidden, args=(word,)).start()
            return

        if len(word) < 1: return
        if not re.fullmatch(r'[가-힣]+', word):
            self.current_fail_count += 1
            self.async_log_history(nickname, word, self.current_word_text, "Fail", "한글 아님")
            return

        if self.current_word_text:
            last_char = self.current_word_text[-1]
            first_char = word[0]
            valid_starts = apply_dueum_rule(last_char)
            if first_char not in valid_starts:
                self.current_fail_count += 1
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "규칙 위반")
                self.log_message(f"[실패] {platform} - {nickname}: {word} (초성 불일치)")
                return

        self.input_locked = True
        
        threading.Thread(target=self._bg_check_word, args=(platform, word, nickname)).start()

    def _bg_check_word(self, platform, word, nickname):
        result = self.db_manager.check_and_use_word(word, nickname)
        is_game_over = False

        if result == "success":
            next_starts = apply_dueum_rule(word[-1])
            any_left = False
            for char in next_starts:
                if self.db_manager.check_remaining_words(char):
                    any_left = True
                    break
            if not any_left:
                is_game_over = True
        
        self.signals.game_check_result.emit(result, platform, nickname, word, is_game_over)

    def on_word_check_finished(self, result_status, platform, nickname, word, is_game_over):
        if result_status == "success":
            QTimer.singleShot(1000, self.unlock_input)
            
            self.last_platform = platform
            self.last_user = nickname
            
            self.play_success_sound()
            self.async_log_history(nickname, word, self.current_word_text, "Success")
            
            display_str = f"[{platform}] {nickname}"
            self.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {display_str}")
            self.log_message(f"[성공] {platform} - {nickname}: {word}")

            self.current_word_text = word
            self.set_responsive_text(word)
            
            self.last_change_time = time.time()
            curr_dt_str = datetime.fromtimestamp(self.last_change_time).strftime("%Y.%m.%d %H:%M:%S")
            update_env_variable("last_word_change_time", curr_dt_str)
            self.email_sent_flag = False 
            
            current_count = int(self.lbl_word_count.text())
            self.lbl_word_count.setText(str(current_count + 1))
            self.update_runtime()
            self.update_hint(word[-1])

            if is_game_over:
                self.log_message(f"[시스템] 게임 종료!")
                self.process_game_over(word, nickname)

        else:
            self.input_locked = False
            self.current_fail_count += 1
            fail_msg = f"[실패] {platform} - {nickname}: {word}"
            
            if result_status == "unavailable":
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "부적절")
                self.log_message(f"{fail_msg} (사전에 없음)") 
                threading.Thread(target=handle_violation_alert, args=(nickname, word)).start()
            elif result_status == "not_found":
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "사전없음")
                self.log_message(f"{fail_msg} (사전에 없음)")
                threading.Thread(target=log_unknown_word, args=(word,)).start()
            elif result_status == "used":
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "이미사용")
                self.log_message(f"{fail_msg} (이미 사용됨)")
            elif result_status == "forbidden":
                self.async_log_history(nickname, word, self.current_word_text, "Fail", "금지어")
                self.log_message(f"{fail_msg} (금지어)")
            else:
                self.log_message(f"[시스템 오류] {fail_msg} (DB 에러 발생)")
                self.input_locked = False

    def process_game_over(self, last_word, last_winner):
        self.db_manager.end_game_session(
            self.current_fail_count,
            last_word,
            self.last_platform,
            self.last_user
        )
        
        self.db_manager.export_all_data_to_csv()
        count = self.db_manager.get_used_word_count()
        today_str = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        update_env_variable("db_reset_time", today_str)
        self.lbl_reset_time.setText(today_str)
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
        self.start_game_logic(start_word, restore_time=False)
        self.stacked_widget.setCurrentIndex(0)