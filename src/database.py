import pymysql
import os

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

    def log_system(self, level, source, message, trace=None):
        """시스템 로그 기록 (app_logs)"""
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return

        try:
            with self.conn.cursor() as cursor:
                sql = """
                    INSERT INTO app_logs (log_level, source_class, message, stack_trace)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (level, source, message, trace))
        except Exception as e:
            print(f"[DB 로그 저장 실패] {e}")

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        """게임 히스토리 기록 (game_history)"""
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return

        try:
            with self.conn.cursor() as cursor:
                sql = """
                    INSERT INTO game_history (nickname, input_word, previous_word, result_status, fail_reason)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (nickname, input_word, previous_word, status, reason))
        except Exception as e:
            print(f"[DB 히스토리 저장 실패] {e}")

    def check_and_use_word(self, word, nickname):
        """
        [수정됨] 단어 유효성 확인 및 사용 처리
        - 성공 시 is_use=True 처리 및 is_use_user에 닉네임 저장
        """
        if not self.conn or not self.conn.open:
            self.connect()
            if not self.conn: return False

        try:
            with self.conn.cursor() as cursor:
                # 1. 단어 존재 여부, 미사용 여부, 사용 가능 여부 확인
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
                    
                    # 2. 사용 처리 및 유저 기록 (source는 건드리지 않음)
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
            self.log_system(8, "DatabaseManager", "단어 검증 중 DB 에러 발생", str(e))
            self.conn.rollback()
            return False