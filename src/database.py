# src/database.py
import pymysql
import os
import csv
import time
from datetime import datetime

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
                charset='utf8mb4',
                autocommit=True
            )
            print(f"[시스템] DB 연결 성공 (Database: {self.db_name})")
        except Exception as e:
            print(f"[오류] DB 연결 실패: {e}")

    # ... (기존 log_system, log_history 생략 - 유지) ...

    def log_system(self, level, source, message, trace=None):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return
        try:
            with self.conn.cursor() as cursor:
                sql = "INSERT INTO app_logs (log_level, source_class, message, stack_trace) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (level, source, message, trace))
        except Exception as e:
            print(f"[DB 로그 저장 실패] {e}")

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return
        try:
            with self.conn.cursor() as cursor:
                sql = "INSERT INTO game_history (nickname, input_word, previous_word, result_status, fail_reason) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (nickname, input_word, previous_word, status, reason))
        except Exception as e:
            print(f"[DB 히스토리 저장 실패] {e}")

    # ... (check_and_use_word, check_remaining_words, get_used_word_count 등 기존 메서드 유지) ...
    
    def check_and_use_word(self, word, nickname):
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
                    AND available = TRUE
                """
                cursor.execute(sql_check, (word,))
                result = cursor.fetchone()

                if result:
                    pk_num = result[0]
                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql_update, (nickname, pk_num))
                    return True
                else:
                    return False
        except Exception as e:
            self.log_system(8, "DatabaseManager", "단어 검증 중 DB 에러 발생", str(e))
            self.conn.rollback()
            return False
            
    def check_remaining_words(self, start_char):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return False
        try:
            with self.conn.cursor() as cursor:
                sql = "SELECT COUNT(*) FROM ko_word WHERE start_char = %s AND is_use = FALSE AND can_use = TRUE AND available = TRUE"
                cursor.execute(sql, (start_char,))
                count = cursor.fetchone()[0]
                return count == 0
        except Exception as e:
            self.log_system(8, "DatabaseManager", "남은 단어 확인 중 에러", str(e))
            return False

    def get_used_word_count(self):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return 0
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_random_start_word(self):
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return "시작"
        try:
            with self.conn.cursor() as cursor:
                sql = "SELECT word FROM ko_word WHERE can_use = TRUE AND available = TRUE ORDER BY RAND() LIMIT 1"
                cursor.execute(sql)
                result = cursor.fetchone()
                return result[0] if result else "시작"
        except Exception as e:
            self.log_system(8, "DatabaseManager", "랜덤 단어 조회 실패", str(e))
            return "시작"

    # [추가] 관리자 명령어용: 단어 강제 변경
    def admin_force_use_word(self, word, nickname="console-admin"):
        """
        [명령어 chcw] 단어의 상태를 강제로 '사용됨'으로 변경
        - 단어가 DB에 존재해야 함 (available/can_use 무관하게 존재하면 처리)
        """
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return False

        try:
            with self.conn.cursor() as cursor:
                # 단어 존재 확인 (사용 여부 무관)
                sql_check = "SELECT num FROM ko_word WHERE word = %s"
                cursor.execute(sql_check, (word,))
                result = cursor.fetchone()

                if result:
                    pk_num = result[0]
                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, 
                            is_use_date = NOW(),
                            is_use_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql_update, (nickname, pk_num))
                    return True
                else:
                    return False
        except Exception as e:
            self.log_system(8, "DatabaseManager", f"관리자 단어 변경 실패: {word}", str(e))
            self.conn.rollback()
            return False

    def export_all_data_to_csv(self):
        if not self.conn or not self.conn.open:
            self.connect()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        if not os.path.exists(backup_dir): os.makedirs(backup_dir)
        tables = ["ko_word", "app_logs", "game_history"]
        try:
            with self.conn.cursor() as cursor:
                for table in tables:
                    sql = f"SELECT * FROM {table}"
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    if cursor.description: column_names = [i[0] for i in cursor.description]
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
        if not self.conn or not self.conn.open:
            self.connect()
        try:
            with self.conn.cursor() as cursor:
                sql_word_reset = "UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL"
                cursor.execute(sql_word_reset)
                cursor.execute("TRUNCATE TABLE app_logs")
                cursor.execute("TRUNCATE TABLE game_history")
            print("[시스템] 모든 DB 테이블이 초기화되었습니다.")
            return True
        except Exception as e:
            print(f"[오류] DB 초기화 실패: {e}")
            return False