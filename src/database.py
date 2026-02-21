# src/database.py
import pymysql
import os
import csv
import time
import threading
import queue
from contextlib import contextmanager
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        self.host = os.getenv("DB_HOST", "localhost")
        self.user = os.getenv("DB_USER", "root")
        self.password = os.getenv("DB_PASSWORD", "")
        self.db_name = os.getenv("DB_NAME", "word_chain_game_db")
        self.port = int(os.getenv("DB_PORT", 3306))
        
        self.current_game_id = None
        self.state_lock = threading.Lock() # 상태 변수(game_id 등) 보호용 락
        
        # [핵심] DB 커넥션 풀(Connection Pool) 초기화 (15개)
        self.pool_size = 15
        self.connection_pool = queue.Queue(maxsize=self.pool_size)
        
        for _ in range(self.pool_size):
            conn = self._create_connection()
            if conn:
                self.connection_pool.put(conn)
                
        # [핵심] 로그 전담 큐(Queue) 및 백그라운드 워커 스레드 초기화
        self.log_queue = queue.Queue()
        self.log_worker_thread = threading.Thread(target=self._log_worker_loop, daemon=True)
        self.log_worker_thread.start()

    def _create_connection(self):
        try:
            return pymysql.connect(
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
        except Exception as e:
            print(f"[오류] DB 연결 생성 실패: {e}")
            return None

    @contextmanager
    def get_connection(self):
        """커넥션 풀에서 연결을 가져와 사용 후 반납하는 컨텍스트 매니저"""
        conn = self.connection_pool.get()
        try:
            conn.ping(reconnect=True) # 연결이 끊겼으면 자동 재연결
            yield conn
        finally:
            self.connection_pool.put(conn)

    # --- 로그 전담 스레드 (Queue Worker) ---
    def _log_worker_loop(self):
        """메인/검증 스레드를 막지 않고 백그라운드에서 로그 삽입만 전담"""
        worker_conn = self._create_connection()
        while True:
            task = self.log_queue.get()
            if task is None: # 종료 시그널
                if worker_conn: worker_conn.close()
                break
                
            try:
                worker_conn.ping(reconnect=True)
                with worker_conn.cursor() as cursor:
                    if task['type'] == 'system':
                        sql = "INSERT INTO app_logs (log_level, source_class, message, stack_trace) VALUES (%s, %s, %s, %s)"
                        cursor.execute(sql, task['data'])
                    elif task['type'] == 'history':
                        sql = "INSERT INTO game_history (nickname, input_word, previous_word, result_status, fail_reason) VALUES (%s, %s, %s, %s, %s)"
                        cursor.execute(sql, task['data'])
            except Exception as e:
                print(f"[DB 로그 전담 워커 실패] {e}")
            finally:
                self.log_queue.task_done()

    def log_system(self, level, source, message, trace=None):
        # 큐에 데이터를 밀어넣기만 하므로 0.0001초만에 리턴됨 (프리징 방지)
        self.log_queue.put({'type': 'system', 'data': (level, source, message, trace)})

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        self.log_queue.put({'type': 'history', 'data': (nickname, input_word, previous_word, status, reason)})

    def start_new_game_session(self, start_word):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    sql = "INSERT INTO game_status(start_word) VALUES (%s)"
                    cursor.execute(sql, (start_word,))
                    with self.state_lock:
                        self.current_game_id = cursor.lastrowid
                    print(f"[시스템] 새 게임 시작 (ID: {self.current_game_id}, 시작 단어: {start_word})")
            except Exception as e:
                print(f"[오류] 게임 세션 시작 실패: {e}")

    def end_game_session(self, fail_count, end_word, end_platform, end_user):
        with self.state_lock:
            game_id = self.current_game_id
            self.current_game_id = None
            
        if game_id is None: return

        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    success_count = cursor.fetchone()[0]

                    sql = """
                        UPDATE game_status 
                        SET word_currect_count = %s, word_fail_count = %s, end_at = NOW(),
                            end_word = %s, end_platform = %s, end_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql, (success_count, fail_count, end_word, end_platform, end_user, game_id))
                    print(f"[시스템] 게임 세션 종료 기록 완료 (ID: {game_id})")
            except Exception as e:
                print(f"[오류] 게임 세션 종료 처리 실패: {e}")

    def check_and_use_word(self, word, nickname):
        word = word.strip()
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
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
                print(f"[오류] 단어 검증 에러: {e}")
                return "error"

    def check_rare_end_word(self, end_char):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    sql = "SELECT count(*) FROM ko_word WHERE end_char = %s AND source NOT IN ('movie', 'medicine', 'company', 'food')"
                    cursor.execute(sql, (end_char,))
                    return cursor.fetchone()[0]
            except Exception: return -1

    def get_used_word_count(self):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    return cursor.fetchone()[0]
            except Exception: return 0

    def mark_word_as_forbidden(self, word):
        word = word.strip()
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    sql = "UPDATE ko_word SET can_use = FALSE WHERE word = %s"
                    affected = cursor.execute(sql, (word,))
                    return affected > 0
            except Exception: return False

    def test_db_integrity(self):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return True, "정상 응답"
            except Exception as e: return False, str(e)

    def get_last_used_word(self):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    sql = "SELECT word, is_use_user FROM ko_word WHERE is_use = TRUE ORDER BY is_use_date DESC, num DESC LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    return (str(result[0]), str(result[1])) if result else ("시작", None)
            except Exception: return ("시작", None)

    def get_random_start_word(self):
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    sql = "SELECT word FROM ko_word WHERE can_use = TRUE AND available = TRUE ORDER BY RAND() LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    return str(result[0]) if result else "시작"
            except Exception: return "시작"

    def export_all_data_to_csv(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        if not os.path.exists(backup_dir): os.makedirs(backup_dir)
        
        tables = ["app_logs", "game_history", "game_status"]
        tables_data = {}

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
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
        with self.get_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL")
                    cursor.execute("TRUNCATE TABLE app_logs")
                    cursor.execute("TRUNCATE TABLE game_history")
                    cursor.execute("TRUNCATE TABLE game_status") 
                return True
            except Exception: return False
            
    def close(self):
        """종료 시 큐 워커 종료 및 풀 안의 모든 커넥션 해제"""
        self.log_queue.put(None)
        while not self.connection_pool.empty():
            conn = self.connection_pool.get()
            try: conn.close()
            except: pass