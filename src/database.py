# src/database.py
import pymysql
import os
import csv
import threading
import queue
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "word_chain_game_db")
        self.port = int(os.getenv("DB_PORT", 3306))
        
        self.current_game_id = None
        self.conn = None
        self.lock = threading.Lock() 
        
        self.connect()

        self.log_queue = queue.Queue()
        self.log_worker = threading.Thread(target=self._log_worker_loop, daemon=True)
        self.log_worker.start()

    def connect(self):
        try:
            if self.conn:
                try: self.conn.close()
                except: pass
            
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
            
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS banned_end_chars (
                        char_val VARCHAR(10) PRIMARY KEY,
                        banned_at DATETIME
                    )
                """)
                
            print(f"[시스템] DB 연결 성공 (Database: {self.db_name})")
        except Exception as e:
            print(f"[오류] DB 연결 실패: {e}")
            self.conn = None

    def _ensure_connection(self):
        if self.conn is None:
            self.connect()
            return
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self.connect()

    def _create_worker_connection(self):
        try:
            return pymysql.connect(
                host=self.host, user=self.user, password=self.password,
                db=self.db_name, port=self.port, charset='utf8mb4',
                autocommit=True, cursorclass=pymysql.cursors.Cursor
            )
        except: return None

    def _log_worker_loop(self):
        worker_conn = self._create_worker_connection()
        while True:
            task = self.log_queue.get()
            if task is None: 
                if worker_conn: worker_conn.close()
                break
            try:
                if not worker_conn: worker_conn = self._create_worker_connection()
                worker_conn.ping(reconnect=True)
                with worker_conn.cursor() as cursor:
                    if task['type'] == 'system':
                        sql = "INSERT INTO app_logs (log_level, source_class, message, stack_trace) VALUES (%s, %s, %s, %s)"
                        cursor.execute(sql, task['data'])
                    elif task['type'] == 'history':
                        sql = "INSERT INTO game_history (nickname, input_word, previous_word, result_status, fail_reason) VALUES (%s, %s, %s, %s, %s)"
                        cursor.execute(sql, task['data'])
            except Exception as e:
                print(f"[DB 로그 저장 실패] {e}")
            finally:
                self.log_queue.task_done()

    def log_system(self, level, source, message, trace=None):
        self.log_queue.put({'type': 'system', 'data': (level, source, message, trace)})

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        self.log_queue.put({'type': 'history', 'data': (nickname, input_word, previous_word, status, reason)})

    def get_recent_logs(self, log_type, limit=10):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return []
            try:
                table_name = "app_logs" if log_type == "all" else "game_history"
                with self.conn.cursor() as cursor:
                    sql = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT %s"
                    cursor.execute(sql, (limit,))
                    return cursor.fetchall()
            except Exception as e:
                raise e

    def start_new_game_session(self, start_word):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                with self.conn.cursor() as cursor:
                    sql = "INSERT INTO game_status(start_word) VALUES (%s)"
                    cursor.execute(sql, (start_word,))
                    self.current_game_id = cursor.lastrowid
            except Exception as e:
                print(f"[오류] 게임 시작 실패: {e}")

    def end_game_session(self, fail_count, end_word, end_platform, end_user):
        if self.current_game_id is None: return
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    success_count = cursor.fetchone()[0]

                    sql = """
                        UPDATE game_status 
                        SET word_currect_count = %s, word_fail_count = %s, end_at = NOW(),
                            end_word = %s, end_platform = %s, end_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql, (success_count, fail_count, end_word, end_platform, end_user, self.current_game_id))
                self.current_game_id = None
            except Exception as e:
                print(f"[오류] 게임 종료 기록 실패: {e}")

    def check_and_use_word(self, word, nickname):
        word = word.strip()
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "error:DB 연결이 끊어져 있습니다."
            try:
                with self.conn.cursor() as cursor:
                    # [수정 반영] 24시간 조건 체크 없이 존재 여부만 확인. 사전에 있든 없든 즉시 차단
                    sql_banned = "SELECT 1 FROM banned_end_chars WHERE char_val = %s"
                    cursor.execute(sql_banned, (word[-1],))
                    if cursor.fetchone():
                        return "forbidden_end_char" 

                    sql_check = "SELECT num, is_use, can_use, available FROM ko_word WHERE word = %s"
                    cursor.execute(sql_check, (word,))
                    result = cursor.fetchone()

                    if not result: return "not_found"
                    pk_num, is_use, can_use, available = result

                    if not available: return "unavailable"
                    if not can_use: return "forbidden"
                    if is_use: return "used"

                    sql_update = "UPDATE ko_word SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s WHERE num = %s AND is_use = FALSE"
                    affected = cursor.execute(sql_update, (nickname, pk_num))
                    return "success" if affected > 0 else "used"
            except Exception as e:
                err_str = str(e).replace('\n', ' ')
                return f"error:{err_str}"

    def check_remaining_words(self, start_char):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return 0
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT char_val FROM banned_end_chars")
                    banned_chars = [row[0] for row in cursor.fetchall()]
                    
                    if banned_chars:
                        placeholders = ','.join(['%s'] * len(banned_chars))
                        sql = f"""
                            SELECT count(*) FROM ko_word 
                            WHERE word LIKE %s 
                            AND is_use = FALSE 
                            AND can_use = TRUE 
                            AND available = TRUE 
                            AND end_char NOT IN ({placeholders})
                        """
                        params = [start_char + "%"] + banned_chars
                        cursor.execute(sql, tuple(params))
                    else:
                        sql = """
                            SELECT count(*) FROM ko_word 
                            WHERE word LIKE %s 
                            AND is_use = FALSE 
                            AND can_use = TRUE 
                            AND available = TRUE
                        """
                        cursor.execute(sql, (start_char + "%",))
                    
                    return cursor.fetchone()[0] 
            except Exception as e:
                print(f"[오류] 남은 단어 확인 에러: {e}")
                return 0

    # [로직 전면 수정] 게임 종료 시 마지막 단어 첫 글자 기준 금지 판별
    def check_and_ban_start_char(self, last_word):
        if not last_word: return
        start_char = last_word[0]
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                from .utils import apply_dueum_rule # 한방 단어 판독을 위한 두음법칙 호출
                with self.conn.cursor() as cursor:
                    # [수정 반영] 게임이 종료되는 이 시점에만 24시간이 넘은 밴 목록을 청소합니다.
                    cursor.execute("DELETE FROM banned_end_chars WHERE banned_at <= NOW() - INTERVAL 24 HOUR")

                    # 한방 단어가 아닌 것을 판별하기 위해, DB에 실제로 존재하는 모든 유효한 '시작 글자' 목록을 확보
                    cursor.execute("SELECT DISTINCT LEFT(word, 1) FROM ko_word WHERE available = TRUE AND can_use = TRUE")
                    valid_starts_in_db = {row[0] for row in cursor.fetchall()}

                    # 마지막 단어의 '첫 글자'로 '시작'하고, '유효한(available=1, can_use=1)' 단어들의 끝 글자만 모두 가져옴
                    cursor.execute("SELECT end_char FROM ko_word WHERE word LIKE %s AND available = TRUE AND can_use = TRUE", (start_char + "%",))
                    end_chars = [row[0] for row in cursor.fetchall()]

                    # 가져온 끝 글자들에 두음법칙을 적용해 보며, 다음 단어로 이어갈 수 있는 '한방 단어가 아닌 단어'만 카운트
                    non_one_hit_count = 0
                    for ec in end_chars:
                        possible_next_chars = apply_dueum_rule(ec)
                        if any(nc in valid_starts_in_db for nc in possible_next_chars):
                            non_one_hit_count += 1

                    # '한방 단어가 아닌' 유효 단어가 5개 이하라면 규칙 발동
                    if non_one_hit_count <= 5:
                        sql_insert = """
                            INSERT INTO banned_end_chars (char_val, banned_at) 
                            VALUES (%s, NOW()) 
                            ON DUPLICATE KEY UPDATE banned_at = NOW()
                        """
                        cursor.execute(sql_insert, (start_char,))
                        print(f"[시스템] 규칙 발동: '{start_char}'(으)로 끝나는 단어 24시간 금지 등록됨 (생존 가능 단어: {non_one_hit_count}개).")
            except Exception as e:
                print(f"[오류] 금지 글자 등록/해제 실패: {e}")

    def toggle_banned_char(self, char):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "DB 연결 상태를 확인해주세요."
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM banned_end_chars WHERE char_val = %s", (char,))
                    if cursor.fetchone():
                        cursor.execute("DELETE FROM banned_end_chars WHERE char_val = %s", (char,))
                        return f"[성공] '{char}' 글자가 금지 목록에서 해제되었습니다."
                    else:
                        sql_insert = """
                            INSERT INTO banned_end_chars (char_val, banned_at) 
                            VALUES (%s, NOW()) 
                            ON DUPLICATE KEY UPDATE banned_at = NOW()
                        """
                        cursor.execute(sql_insert, (char,))
                        return f"[성공] '{char}' 글자가 24시간 금지 목록에 추가되었습니다."
            except Exception as e:
                return f"[오류] 금지 설정 실패: {e}"

    def get_banned_end_chars(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return []
            try:
                with self.conn.cursor() as cursor:
                    # 타이머 호출 시에는 시간 제한 검사나 삭제를 하지 않고 있는 그대로 반환
                    cursor.execute("SELECT char_val FROM banned_end_chars")
                    return [row[0] for row in cursor.fetchall()]
            except Exception: return []

    def check_rare_end_word(self, end_char):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return -1
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT count(*) FROM ko_word WHERE end_char = %s AND source NOT IN ('movie', 'medicine', 'company', 'food')"
                    cursor.execute(sql, (end_char,))
                    return cursor.fetchone()[0]
            except Exception: return -1

    def get_used_word_count(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return 0
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    return cursor.fetchone()[0]
            except Exception: return 0

    def mark_word_as_forbidden(self, word):
        word = word.strip()
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False
            try:
                with self.conn.cursor() as cursor:
                    sql = "UPDATE ko_word SET can_use = FALSE WHERE word = %s"
                    affected = cursor.execute(sql, (word,))
                    return affected > 0
            except Exception: return False

    def admin_force_use_word(self, word, nickname="console-admin"):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False
            try:
                with self.conn.cursor() as cursor:
                    sql_check = "SELECT num FROM ko_word WHERE word = %s"
                    cursor.execute(sql_check, (word,))
                    result = cursor.fetchone()

                    if result:
                        pk_num = result[0]
                        sql_update = "UPDATE ko_word SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s WHERE num = %s"
                        cursor.execute(sql_update, (nickname, pk_num))
                        return True
                    else:
                        return False
            except Exception as e:
                self.conn.rollback()
                return False

    def test_db_integrity(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False, "DB 연결 실패"
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return True, "정상 응답"
            except Exception as e: return False, str(e)

    def get_last_used_word(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return ("시작", None)
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT word, is_use_user FROM ko_word WHERE is_use = TRUE ORDER BY is_use_date DESC, num DESC LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    return (str(result[0]), str(result[1])) if result else ("시작", None)
            except Exception: return ("시작", None)

    def get_random_start_word(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "시작"
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT word FROM ko_word WHERE can_use = TRUE AND available = TRUE ORDER BY RAND() LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    return str(result[0]) if result else "시작"
            except Exception: return "시작"

    def get_and_use_random_available_word(self, nickname="console-random"):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return None
            try:
                with self.conn.cursor() as cursor:
                    sql_select = "SELECT num, word FROM ko_word WHERE is_use = FALSE AND can_use = TRUE AND available = TRUE ORDER BY RAND() LIMIT 1"
                    cursor.execute(sql_select)
                    result = cursor.fetchone()
                    
                    if not result: return None
                    
                    pk_num, word = result
                    sql_update = "UPDATE ko_word SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s WHERE num = %s"
                    cursor.execute(sql_update, (nickname, pk_num))
                    return str(word)
            except Exception: return None

    def export_all_data_to_csv(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        if not os.path.exists(backup_dir): os.makedirs(backup_dir)
        
        tables = ["app_logs", "game_history", "game_status", "banned_end_chars"]
        tables_data = {}

        try:
            with self.lock:
                self._ensure_connection()
                if not self.conn: return False, None
                with self.conn.cursor() as cursor:
                    for table in tables:
                        try:
                            cursor.execute(f"SELECT * FROM {table}")
                            rows = cursor.fetchall()
                            cols = [i[0] for i in cursor.description] if cursor.description else []
                            tables_data[table] = (cols, rows)
                        except Exception: continue

            for table, (cols, rows) in tables_data.items():
                filename = f"{backup_dir}/{table}_{timestamp}.csv"
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    if cols: writer.writerow(cols)
                    writer.writerows(rows)
            return True, timestamp
        except Exception: return False, None

    def reset_all_tables(self):
        with self.lock:
            self._ensure_connection()
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL")
                    cursor.execute("TRUNCATE TABLE app_logs")
                    cursor.execute("TRUNCATE TABLE game_history")
                    cursor.execute("TRUNCATE TABLE game_status") 
                return True
            except Exception: return False
            
    def close(self):
        self.log_queue.put(None)
        if self.conn:
            try: self.conn.close()
            except: pass