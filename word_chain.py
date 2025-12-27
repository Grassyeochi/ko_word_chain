import sys
import asyncio
import json
import os
import time
import requests
import websockets
import re
import pymysql
from datetime import timedelta
from dotenv import load_dotenv

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QFrame, QInputDialog, QSizePolicy, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from qasync import QEventLoop

# .env 파일 로드
load_dotenv()

# --- 0. 데이터베이스 관리 클래스 ---
class DatabaseManager:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "word_chain_game_db")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.conn = None
        self.connect()

    def connect(self):
        try:
            self.conn = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                db=self.db_name,
                port=self.port,
                charset='utf8mb4'
            )
            print(f"[시스템] DB 연결 성공 (Database: {self.db_name})")
        except Exception as e:
            print(f"[오류] DB 연결 실패: {e}")

    def check_and_use_word(self, word):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return False

        try:
            with self.conn.cursor() as cursor:
                sql_check = """
                    SELECT num FROM ko_word 
                    WHERE word = %s 
                    AND is_use = FALSE 
                    AND can_use = TRUE
                """
                cursor.execute(sql_check, (word,))
                result = cursor.fetchone()

                if result:
                    pk_num = result[0]
                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, is_use_date = NOW()
                        WHERE num = %s
                    """
                    cursor.execute(sql_update, (pk_num,))
                    self.conn.commit()
                    return True
                else:
                    return False
        except Exception as e:
            print(f"[DB 에러] {e}")
            self.conn.rollback()
            return False

# --- 1. 통신 신호 관리 클래스 ---
class GameSignals(QObject):
    word_detected = pyqtSignal(str, str)
    stream_offline = pyqtSignal()

# --- 2. 치지직 모니터링 로직 ---
class ChzzkMonitor:
    def __init__(self, signals):
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.ws_url = "wss://kr-ss1.chat.naver.com/chat"
        self.signals = signals
        self.running = True

    async def run(self):
        if not self.channel_id:
            print("[오류] .env 파일에 CHZZK_CHANNEL_ID가 설정되지 않았습니다.")
            return

        try:
            status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
            res = requests.get(status_url).json()
            content = res.get('content', {})
            
            live_status = content.get('status')
            if live_status != 'OPEN':
                print(f"[시스템] 현재 방송 상태: {live_status} (연결 중단)")
                self.signals.stream_offline.emit()
                return

            chat_channel_id = content['chatChannelId']

            token_url = f"https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chat_channel_id}&chatType=STREAMING"
            token_res = requests.get(token_url).json()
            access_token = token_res['content']['accessToken']

            async with websockets.connect(self.ws_url) as websocket:
                print(f"[시스템] 채팅 서버 연결 성공 (Chat ID: {chat_channel_id})")
                
                await websocket.send(json.dumps({
                    "ver": "2", "cmd": 100, "svcid": "game", "cid": chat_channel_id, "tid": 1,
                    "bdy": {"uid": None, "devType": 2001, "accTkn": access_token, "auth": "READ"}
                }))

                while self.running:
                    try:
                        res = await websocket.recv()
                        data = json.loads(res)

                        if data.get('cmd') == 93101:
                            for chat in data.get('bdy', []):
                                msg = chat.get('msg', '').strip()
                                profile = json.loads(chat.get('profile', '{}'))
                                nickname = profile.get('nickname', '익명')

                                if msg.startswith("!"):
                                    content = msg[1:].strip()
                                    if content:
                                        clean_word = content.split()[0]
                                        self.signals.word_detected.emit(nickname, clean_word)

                        elif data.get('cmd') == 0:
                            await websocket.send(json.dumps({"ver": "2", "cmd": 10000}))
                            
                    except Exception as e:
                        print(f"[연결 끊김 또는 에러] {e}")
                        break
        except Exception as e:
            print(f"[초기화 오류] {e}")

# --- 3. 메인 GUI 클래스 ---
class ChzzkGameGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = GameSignals()
        self.monitor = ChzzkMonitor(self.signals)
        
        self.db_manager = DatabaseManager()
        
        self.start_time = time.time()
        self.last_change_time = time.time()
        self.current_word_text = ""
        
        # [요구사항 1] 입력 쿨타임 관리를 위한 플래그
        self.input_locked = False 

        self.init_ui()
        self.setup_connections()
        
        self.ask_starting_word()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_runtime)
        self.timer.start(1000)

        asyncio.get_event_loop().create_task(self.monitor.run())

    def init_ui(self):
        self.setWindowTitle("치지직 한국어 끝말잇기")
        self.resize(1000, 650) # 크레딧 공간 확보를 위해 세로 살짝 늘림
        self.setStyleSheet("background-color: black; color: white;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 20)
        main_layout.setSpacing(20)

        # === 상단 영역 ===
        top_layout = QHBoxLayout()
        
        self.title_label = QLabel("한국어 끝말잇기")
        self.title_label.setFont(QFont("NanumBarunGothic", 40, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        top_right_layout = QVBoxLayout()
        
        self.lbl_runtime_title = QLabel("프로그램 런 타임")
        self.lbl_runtime_title.setStyleSheet("background-color: #333; padding: 5px; font-weight: bold;")
        self.lbl_runtime_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_runtime = QLabel("00:00:00")
        self.lbl_runtime.setStyleSheet("border: 1px solid white; padding: 5px;")
        self.lbl_runtime.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_elapsed_title = QLabel("현재 단어가 바뀌고 나서 지난 시간")
        self.lbl_elapsed_title.setStyleSheet("background-color: #333; padding: 5px; margin-top: 5px; font-weight: bold;")
        self.lbl_elapsed_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_word_elapsed = QLabel("00:00:00")
        self.lbl_word_elapsed.setStyleSheet("border: 1px solid white; padding: 5px;")
        self.lbl_word_elapsed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_word_elapsed.setFont(QFont("NanumBarunGothic", 12))

        top_right_layout.addWidget(self.lbl_runtime_title)
        top_right_layout.addWidget(self.lbl_runtime)
        top_right_layout.addWidget(self.lbl_elapsed_title)
        top_right_layout.addWidget(self.lbl_word_elapsed)
        
        top_layout.addWidget(self.title_label, stretch=7)
        top_layout.addLayout(top_right_layout, stretch=3)

        # === 하단 영역 ===
        bottom_layout = QHBoxLayout()

        # [요구사항 2] 순위 영역 "공사중" 처리
        rank_container = QFrame()
        rank_container.setStyleSheet("border: 2px solid white;")
        rank_layout = QVBoxLayout(rank_container)
        
        self.lbl_rank_content = QLabel("순위\n공사중")
        self.lbl_rank_content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rank_content.setFont(QFont("NanumBarunGothic", 25, QFont.Weight.Bold))
        self.lbl_rank_content.setStyleSheet("border: none; color: #AAAAAA;")
        self.lbl_rank_content.setWordWrap(True)

        rank_layout.addWidget(self.lbl_rank_content)
        
        # === 현재 단어 표시 영역 ===
        game_display_layout = QVBoxLayout()
        game_display_layout.setContentsMargins(20, 0, 0, 0)
        game_display_layout.setSpacing(0)

        self.lbl_current_word_title = QLabel("현재 단어")
        self.lbl_current_word_title.setFont(QFont("NanumBarunGothic", 20))
        self.lbl_current_word_title.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
        self.lbl_current_word_title.setStyleSheet("color: #AAAAAA; margin-bottom: 0px;")

        self.lbl_current_word = QLabel("...")
        self.lbl_current_word.setFont(QFont("NanumBarunGothic", 90, QFont.Weight.Bold))
        self.lbl_current_word.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)
        self.lbl_current_word.setStyleSheet("color: white; margin-top: 0px;") 
        
        self.lbl_current_word.setWordWrap(True)
        self.lbl_current_word.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self.lbl_next_hint = QLabel("게임 준비 중...")
        self.lbl_next_hint.setFont(QFont("NanumBarunGothic", 18))
        self.lbl_next_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_next_hint.setStyleSheet("color: #888888; margin-top: 20px;")

        game_display_layout.addWidget(self.lbl_current_word_title, stretch=1)
        game_display_layout.addWidget(self.lbl_current_word, stretch=6)
        game_display_layout.addWidget(self.lbl_next_hint, stretch=2)

        bottom_layout.addWidget(rank_container, stretch=3)
        bottom_layout.addLayout(game_display_layout, stretch=7)

        main_layout.addLayout(top_layout, stretch=2)
        main_layout.addLayout(bottom_layout, stretch=8)

        # [요구사항 3] 하단 크레딧 추가
        self.lbl_credits = QLabel("이름없는존재 제작\nMade by Nameless_Anonymous\nducldpdy@naver.com")
        self.lbl_credits.setFont(QFont("NanumBarunGothic", 10))
        self.lbl_credits.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.lbl_credits.setStyleSheet("color: #777777; margin-top: 10px;")
        
        main_layout.addWidget(self.lbl_credits)

        self.setLayout(main_layout)

    def set_responsive_text(self, text):
        length = len(text)
        font = self.lbl_current_word.font()
        
        formatted_text = text
        new_size = 90  

        if length > 20:
            p1 = length // 3
            p2 = (length // 3) * 2
            formatted_text = text[:p1] + "\n" + text[p1:p2] + "\n" + text[p2:]
            new_size = 45
        elif length > 10:
            mid = length // 2
            formatted_text = text[:mid] + "\n" + text[mid:]
            new_size = 65
        else:
            formatted_text = text
            if length > 6:
                new_size = 70
            else:
                new_size = 90

        font.setPointSize(new_size)
        self.lbl_current_word.setFont(font)
        self.lbl_current_word.setText(formatted_text)

    def apply_dueum_rule(self, char):
        if not re.match(r'[가-힣]', char):
            return [char]

        base_code = ord(char) - 44032
        chosung_idx = base_code // 588
        jungsung_idx = (base_code % 588) // 28
        jongsung_idx = base_code % 28

        y_sounds = [2, 3, 6, 7, 12, 17, 20] 
        variations = [char]
        new_chosung = -1

        if chosung_idx == 5: # ㄹ
            if jungsung_idx in y_sounds:
                new_chosung = 11 # ㅇ
            else:
                new_chosung = 2  # ㄴ
        elif chosung_idx == 2: # ㄴ
            if jungsung_idx in y_sounds:
                new_chosung = 11 # ㅇ

        if new_chosung != -1:
            new_char_code = 44032 + (new_chosung * 588) + (jungsung_idx * 28) + jongsung_idx
            variations.append(chr(new_char_code))
        
        return variations

    def ask_starting_word(self):
        text, ok = QInputDialog.getText(self, '게임 설정', '시작 단어를 입력하세요:')
        if ok and text and re.fullmatch(r'[가-힣]+', text.strip()):
            start_word = text.strip()
        else:
            start_word = "시작"

        self.current_word_text = start_word
        self.set_responsive_text(start_word)
        self.last_change_time = time.time()
        
        self.update_hint(start_word[-1])

    def setup_connections(self):
        self.signals.word_detected.connect(self.handle_new_word)
        self.signals.stream_offline.connect(self.handle_stream_offline)

    def handle_stream_offline(self):
        QMessageBox.critical(self, "연결 실패", "현재 방송이 시작되지 않았습니다.\n방송을 켠 후 다시 실행해주세요.")
        sys.exit()

    def update_runtime(self):
        now = time.time()
        total_elapsed = int(now - self.start_time)
        self.lbl_runtime.setText(str(timedelta(seconds=total_elapsed)))
        
        word_elapsed = int(now - self.last_change_time)
        self.lbl_word_elapsed.setText(str(timedelta(seconds=word_elapsed)))

    def update_hint(self, last_char):
        valid_starts = self.apply_dueum_rule(last_char)
        hint_str = ", ".join([f"!{c}..." for c in valid_starts])
        self.lbl_next_hint.setText(f"다음 글자: '{last_char}' (가능: {hint_str})")
        
    def unlock_input(self):
        """쿨타임 종료 후 입력 잠금 해제"""
        self.input_locked = False
        # print("[시스템] 입력 쿨타임 종료")

    def handle_new_word(self, nickname, word):
        # [요구사항 1] 쿨타임 중이면 무시
        if self.input_locked:
            return

        if len(word) < 1:
            return

        if not re.fullmatch(r'[가-힣]+', word):
            return

        if self.current_word_text:
            last_char = self.current_word_text[-1]
            first_char = word[0]
            
            valid_starts = self.apply_dueum_rule(last_char)
            
            if first_char not in valid_starts:
                return

        # DB 기록
        is_success_db = self.db_manager.check_and_use_word(word)

        if is_success_db:
            # [요구사항 1] 성공 시 1초간 입력 잠금
            self.input_locked = True
            QTimer.singleShot(1000, self.unlock_input)
            
            self.current_word_text = word
            self.set_responsive_text(word)
            
            self.last_change_time = time.time()
            self.update_runtime()

            # [요구사항 2] 순위 업데이트 로직 제거됨 (공사중 텍스트 유지)

            self.update_hint(word[-1])
        else:
            print(f"[게임] '{word}' - 유효하지 않거나 이미 사용된 단어입니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = ChzzkGameGUI()
    window.show()
    with loop:
        loop.run_forever()