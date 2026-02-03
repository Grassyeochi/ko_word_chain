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
        무작위 시작 단어를 하나 가져옵니다. (문자열 반환)
        """
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                sql = "SELECT word FROM ko_word ORDER BY RAND() LIMIT 1;"
                cursor.execute(sql)
                result = cursor.fetchone()
                if result:
                    return str(result[0])
                return "시작"
        except Exception as e:
            print(f"[DB 오류] 랜덤 단어 조회 실패: {e}")
            return "시작"

    def get_last_used_word(self):
        """
        [수정] 최근 사용한 단어와 정답자를 가져옵니다.
        반환값: (word_string, user_string or None) 튜플
        """
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
                # [요청 쿼리 적용]
                sql = """
                    SELECT word, is_use_user
                    FROM ko_word
                    ORDER BY is_use_date DESC
                    LIMIT 1;
                """
                cursor.execute(sql)
                result = cursor.fetchone()

                if result:
                    # result[0] = word, result[1] = is_use_user
                    word = result[0]
                    user = result[1]
                    
                    if word:
                        # 튜플 형태로 반환 (단어, 유저명)
                        return str(word), (str(user) if user else None)
                
                # 결과가 없으면 랜덤 단어 + 유저없음
                print("[시스템] 최근 단어 기록 없음. 무작위 단어 사용.")
                return self.get_random_start_word(), None

        except Exception as e:
            print(f"[DB 오류] 최근 단어 조회 실패: {e}")
            return self.get_random_start_word(), None

    def start_new_game_session(self, start_word):
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
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
        self._ensure_connection()
        with self.lock:
            try:
                with self.conn.cursor() as cursor:
                    sql_check = "SELECT available, is_use FROM ko_word WHERE word = %s"
                    cursor.execute(sql_check, (word,))
                    row = cursor.fetchone()
                    
                    if not row:
                        return "not_found"
                    
                    available, is_use = row
                    
                    if available != 1:
                        return "unavailable"
                    
                    if is_use == 1:
                        return "used"
                    
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
        self._ensure_connection()
        try:
            with self.conn.cursor() as cursor:
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
        self._ensure_connection()
        try:
            with self.lock:
                with self.conn.cursor() as cursor:
                    sql = "UPDATE ko_word SET available = 0 WHERE word = %s"
                    cursor.execute(sql, (word,))
        except Exception as e:
            print(f"[오류] 금지어 마킹 실패: {e}")

    def log_system(self, level, source, message, trace=None):
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
            print(f"[DB 로그 실패] {message} / {e}")

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
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
                    sql_word_reset = "UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL"
                    cursor.execute(sql_word_reset)
                    
                    cursor.execute("TRUNCATE TABLE app_logs")
                    cursor.execute("TRUNCATE TABLE game_history")
                    cursor.execute("TRUNCATE TABLE game_status") 
                print("[시스템] 모든 DB 테이블이 초기화되었습니다.")
                return True
            except Exception as e:
                print(f"[오류] DB 초기화 실패: {e}")
                return False