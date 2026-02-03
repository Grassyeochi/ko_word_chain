# src/database.py
import pymysql
import os
import csv
import time
import threading 
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "word_chain_game_db")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.conn = None
        self.lock = threading.Lock() 
        
        # 현재 진행 중인 게임의 고유 번호 (game_status.num)
        self.current_game_id = None
        
        self.connect()

    def connect(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            
            self.conn = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                db=self.db_name,
                port=self.port,
                charset='utf8mb4',
                autocommit=True,
                cursorclass=pymysql.cursors.Cursor,
                connect_timeout=10 
            )
            print("[시스템] DB 연결 성공")
        except Exception as e:
            print(f"[오류] DB 연결 실패: {e}")
            self.conn = None

    def _ensure_connection(self):
        if not self.conn or not self.conn.open:
            print("[시스템] DB 재연결 시도...")
            self.connect()

    def test_db_integrity(self):
        self._ensure_connection()
        if not self.conn:
            return False, "연결 실패"
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                return True, "정상"
        except Exception as e:
            return False, str(e)

    def get_random_start_word(self):
        """
        무작위 시작 단어를 하나 가져옵니다.
        """
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                # 무작위 정렬 후 1개
                sql = "SELECT word FROM ko_word ORDER BY RAND() LIMIT 1;"
                cursor.execute(sql)
                result = cursor.fetchone()
                if result:
                    # 튜플의 첫 번째 요소(단어 문자열) 반환
                    return str(result[0])
                return "시작"
        except Exception as e:
            print(f"[DB 오류] 랜덤 단어 조회 실패: {e}")
            return "시작"

    def get_last_used_word(self):
        """
        가장 최근에 사용된(is_use_date가 최신인) 단어를 가져옵니다.
        만약 기록이 없거나(is_use_date가 모두 NULL) 테이블이 비어있으면 무작위 단어를 반환합니다.
        """
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                # [수정됨] SELECT * 사용, 날짜 역순 정렬
                sql = "SELECT * FROM ko_word ORDER BY is_use_date DESC LIMIT 1;"
                cursor.execute(sql)
                result = cursor.fetchone()

                if result:
                    col_names = [desc[0] for desc in cursor.description]
                    
                    # 1. is_use_date 컬럼 값 확인
                    date_val = None
                    if 'is_use_date' in col_names:
                        date_idx = col_names.index('is_use_date')
                        date_val = result[date_idx]
                    
                    # 2. 날짜가 유효한(NULL이 아닌) 경우에만 해당 단어 반환
                    if date_val is not None:
                        if 'word' in col_names:
                            target_index = col_names.index('word')
                            return str(result[target_index])
                        else:
                            # word 컬럼을 명시적으로 못 찾으면 첫 번째 컬럼 반환 (fallback)
                            return str(result[0])
                    
                    # 3. 날짜가 None이면 (DB 초기화 상태) -> 무작위 단어로 대체
                    print("[시스템] 최근 사용 단어 기록 없음(NULL). 무작위 단어로 시작합니다.")
                    return self.get_random_start_word()
                
                # 4. 결과 자체가 없으면 무작위
                return self.get_random_start_word()

        except Exception as e:
            print(f"[DB 오류] 최근 단어 조회 실패: {e}")
            # 오류 발생 시 안전하게 랜덤 단어 반환
            return self.get_random_start_word()

    def start_new_game_session(self, start_word):
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    # 이전 세션 중 종료되지 않은 게 있다면 종료 처리 (옵션)
                    # 여기서는 단순히 새 레코드를 INSERT
                    sql = """
                        INSERT INTO game_status (start_time, start_word, status)
                        VALUES (NOW(), %s, 'Playing')
                    """
                    cursor.execute(sql, (start_word,))
                    self.current_game_id = cursor.lastrowid
        except Exception as e:
            print(f"[오류] 게임 세션 시작 실패: {e}")

    def end_game_session(self, fail_count, last_word, last_platform, last_user):
        if not self.current_game_id: return
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    sql = """
                        UPDATE game_status 
                        SET end_time = NOW(), 
                            status = 'Finished',
                            fail_count = %s,
                            last_word = %s,
                            last_platform = %s,
                            last_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql, (fail_count, last_word, last_platform, last_user, self.current_game_id))
        except Exception as e:
            print(f"[오류] 게임 세션 종료 처리 실패: {e}")

    def check_and_use_word(self, word, nickname):
        """
        단어 유효성 검사 및 사용 처리 (트랜잭션)
        반환값: "success", "unavailable"(사전없음/부적절), "used", "forbidden", "error"
        """
        self._ensure_connection()
        with self.lock:
            try:
                with self.conn.cursor() as cursor:
                    # 1. 단어 존재 여부 및 사용 가능 여부 확인
                    # ko_word 테이블 가정: word, available, is_use 등
                    sql_check = "SELECT available, is_use FROM ko_word WHERE word = %s"
                    cursor.execute(sql_check, (word,))
                    row = cursor.fetchone()
                    
                    if not row:
                        return "not_found"
                    
                    available, is_use = row
                    
                    # available이 1이 아니면 사용 불가 단어(비표준어, 욕설 등 DB상 마킹)
                    if available != 1:
                        return "unavailable"
                    
                    # 이미 사용된 단어인지 확인
                    if is_use == 1:
                        return "used"
                    
                    # 2. 사용 처리
                    # 닉네임, 날짜 업데이트
                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, 
                            is_use_date = NOW(), 
                            is_use_user = %s 
                        WHERE word = %s
                    """
                    cursor.execute(sql_update, (nickname, word))
                    
                    return "success"
            except Exception as e:
                print(f"[DB 오류] 단어 체크 중 오류: {e}")
                return "error"

    def check_remaining_words(self, start_char):
        """
        해당 글자로 시작하는 사용 가능한(안 쓴) 단어가 있는지 확인
        """
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                # LIKE로 검색. 인덱스 타도록 설계 권장
                # available=1 AND is_use=0
                sql = "SELECT 1 FROM ko_word WHERE word LIKE %s AND available = 1 AND is_use = 0 LIMIT 1"
                cursor.execute(sql, (start_char + "%",))
                return cursor.fetchone() is not None
        except:
            return False

    def get_used_word_count(self):
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                sql = "SELECT COUNT(*) FROM ko_word WHERE is_use = 1"
                cursor.execute(sql)
                return cursor.fetchone()[0]
        except:
            return 0

    def mark_word_as_forbidden(self, word):
        """
        실시간 금지어 처리 (available=0 으로 변경 등)
        """
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    sql = "UPDATE ko_word SET available = 0 WHERE word = %s"
                    cursor.execute(sql, (word,))
        except Exception as e:
            print(f"[오류] 금지어 마킹 실패: {e}")

    def log_system(self, level, source, message, trace=None):
        """
        시스템 로그 (app_logs 테이블)
        """
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    sql = """
                        INSERT INTO app_logs (level, source, message, trace_info)
                        VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(sql, (level, source, message, trace))
        except Exception as e:
            # 로그 저장 실패는 프린트로만 남김 (무한 루프 방지)
            print(f"[DB 로그 실패] {message} / {e}")

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        """
        게임 진행 로그 (game_history 테이블)
        """
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    sql = """
                        INSERT INTO game_history (game_id, nickname, input_word, previous_word, status, fail_reason)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(sql, (self.current_game_id, nickname, input_word, previous_word, status, reason))
        except Exception as e:
            print(f"[DB 로그 실패] 히스토리 저장 실패: {e}")

    def export_all_data_to_csv(self):
        """
        현재 DB 데이터를 CSV로 백업
        """
        backup_dir = "backup"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tables = ["ko_word", "app_logs", "game_history", "game_status"]
        
        self._ensure_connection()
        with self.lock:
            try:
                with self.conn.cursor() as cursor:
                    for table in tables:
                        # 테이블 존재 여부 확인 (간단히)
                        try:
                            cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")
                        except:
                            continue
                            
                        cursor.execute(f"SELECT * FROM {table}")
                        rows = cursor.fetchall()
                        if not rows: continue
                        
                        if cursor.description:
                            column_names = [i[0] for i in cursor.description]
                        else: column_names = []
                        
                        filename = f"{backup_dir}/{table}_{timestamp}.csv"
                        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            if column_names: writer.writerow(column_names)
                            writer.writerows(rows)
                        print(f"[시스템] {table} 백업 완료: {filename}")
                return True, timestamp
            except Exception as e:
                print(f"[오류] CSV 내보내기 실패: {e}")
                return False, None

    def reset_all_tables(self):
        with self.lock:
            self._ensure_connection()
            try:
                with self.conn.cursor() as cursor:
                    # ko_word 초기화 (is_use, 날짜, 유저)
                    sql_word_reset = "UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL"
                    cursor.execute(sql_word_reset)
                    
                    # 로그성 테이블 비우기
                    cursor.execute("TRUNCATE TABLE app_logs")
                    cursor.execute("TRUNCATE TABLE game_history")
                    cursor.execute("TRUNCATE TABLE game_status") 
                print("[시스템] 모든 DB 테이블이 초기화되었습니다.")
                return True
            except Exception as e:
                print(f"[오류] DB 초기화 실패: {e}")
                return False