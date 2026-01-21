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
        
        # [신규] 현재 진행 중인 게임의 고유 번호 (game_status.num)
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
            print(f"[시스템] DB 연결 성공 (Database: {self.db_name})")
        except Exception as e:
            print(f"[오류] DB 연결 실패: {e}")
            self.conn = None

    def _ensure_connection(self):
        if self.conn is None:
            self.connect()
            return

        try:
            self.conn.ping(reconnect=False)
        except Exception:
            print("[시스템] DB 연결 끊김 감지, 재연결 시도...")
            self.connect()

    # --- [신규] 게임 세션 관리 메서드 ---
    
    def start_new_game_session(self, start_word):
        """
        새로운 게임 시작 시 game_status 테이블에 기록하고 ID를 저장
        """
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                with self.conn.cursor() as cursor:
                    # 2-1. 요구사항에 맞춘 INSERT 문
                    sql = "INSERT INTO game_status(start_word) VALUES (%s)"
                    cursor.execute(sql, (start_word,))
                    self.current_game_id = cursor.lastrowid # 방금 생성된 num 저장
                    print(f"[시스템] 새 게임 세션 시작 (ID: {self.current_game_id}, 시작 단어: {start_word})")
            except Exception as e:
                print(f"[오류] 게임 세션 시작 실패: {e}")

    def end_game_session(self, fail_count, end_word, end_platform, end_user):
        """
        게임 종료 또는 프로그램 종료 시 현재 게임 정보를 업데이트
        """
        if self.current_game_id is None:
            return

        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                # 3. 성공 횟수는 DB에서 직접 조회
                success_count = 0
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    success_count = cursor.fetchone()[0]

                with self.conn.cursor() as cursor:
                    # 3. 업데이트 쿼리 (종료 시간, 단어, 플랫폼, 유저, 카운트)
                    sql = """
                        UPDATE game_status 
                        SET word_currect_count = %s,
                            word_fail_count = %s,
                            end_at = NOW(),
                            end_word = %s,
                            end_platform = %s,
                            end_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql, (success_count, fail_count, end_word, end_platform, end_user, self.current_game_id))
                    print(f"[시스템] 게임 세션 종료 기록 완료 (ID: {self.current_game_id})")
                
                # 기록 후 ID 초기화 (중복 업데이트 방지)
                self.current_game_id = None
                
            except Exception as e:
                print(f"[오류] 게임 세션 종료 처리 실패: {e}")

    # -----------------------------------

    def check_and_use_word(self, word, nickname):
        word = word.strip()
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "error"

            try:
                with self.conn.cursor() as cursor:
                    sql_check = "SELECT num, is_use, can_use, available FROM ko_word WHERE TRIM(word) = %s"
                    cursor.execute(sql_check, (word,))
                    result = cursor.fetchone()

                    if not result: 
                        return "not_found"

                    pk_num, is_use, can_use, available = result

                    if not available:
                        return "unavailable"

                    if is_use: 
                        return "used"

                    if not can_use: 
                        return "forbidden"

                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s
                        WHERE num = %s AND is_use = FALSE
                    """
                    affected = cursor.execute(sql_update, (nickname, pk_num))
                    return "success" if affected > 0 else "used"

            except pymysql.OperationalError:
                self.connect()
                return "error"
            except Exception as e:
                print(f"[오류] 단어 검증 에러: {e}")
                return "error"
    
    def get_used_word_count(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return 0
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM ko_word WHERE is_use = TRUE")
                    return cursor.fetchone()[0]
            except Exception:
                return 0

    def mark_word_as_forbidden(self, word):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False
            try:
                with self.conn.cursor() as cursor:
                    sql = "UPDATE ko_word SET can_use = FALSE WHERE TRIM(word) = %s"
                    affected = cursor.execute(sql, (word.strip(),))
                    if affected > 0:
                        print(f"[시스템] 단어 '{word}' DB 차단 처리 완료 (can_use=FALSE)")
                        return True
                    return False
            except Exception as e:
                print(f"[오류] 단어 차단 실패: {e}")
                return False

    def test_db_integrity(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False, "DB 연결 실패"
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT 1" 
                    cursor.execute(sql)
                    return True, "정상 응답"
            except Exception as e:
                return False, str(e)

    def get_last_used_word(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "시작"
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT word FROM ko_word WHERE is_use = TRUE ORDER BY is_use_date DESC, num DESC LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    if result and result[0] and str(result[0]).strip():
                        return str(result[0])
                    else:
                        return "시작"
            except Exception as e:
                print(f"[오류] 최근 단어 조회 실패: {e}")
                return "시작"
    
    def get_and_use_random_available_word(self, nickname="console-random"):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return None
            try:
                with self.conn.cursor() as cursor:
                    sql_select = """
                        SELECT num, word FROM ko_word 
                        WHERE is_use = FALSE 
                        AND can_use = TRUE 
                        AND available = TRUE 
                        ORDER BY RAND() LIMIT 1
                    """
                    cursor.execute(sql_select)
                    result = cursor.fetchone()
                    
                    if not result: return None
                    
                    pk_num, word = result
                    
                    sql_update = """
                        UPDATE ko_word 
                        SET is_use = TRUE, is_use_date = NOW(), is_use_user = %s
                        WHERE num = %s
                    """
                    cursor.execute(sql_update, (nickname, pk_num))
                    return word
            except Exception as e:
                print(f"[오류] 랜덤 변경 실패: {e}")
                return None

    def log_system(self, level, source, message, trace=None):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                with self.conn.cursor() as cursor:
                    sql = "INSERT INTO app_logs (log_level, source_class, message, stack_trace) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (level, source, message, trace))
            except Exception as e:
                print(f"[DB 로그 저장 실패] {e}")

    def log_history(self, nickname, input_word, previous_word, status, reason=None):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return
            try:
                with self.conn.cursor() as cursor:
                    sql = "INSERT INTO game_history (nickname, input_word, previous_word, result_status, fail_reason) VALUES (%s, %s, %s, %s, %s)"
                    cursor.execute(sql, (nickname, input_word, previous_word, status, reason))
            except Exception as e:
                print(f"[DB 히스토리 저장 실패] {e}")

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
                print(f"[DB 조회 실패] {e}")
                raise e
    
    def check_remaining_words(self, start_char):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return False
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT count(*) FROM ko_word WHERE start_char = %s AND is_use = FALSE AND can_use = TRUE AND available = TRUE"
                    cursor.execute(sql, (start_char,))
                    count = cursor.fetchone()[0]
                    return count > 0 
            except Exception as e:
                print(f"[오류] 남은 단어 확인 에러: {e}")
                return False

    def get_random_start_word(self):
        with self.lock:
            self._ensure_connection()
            if not self.conn: return "시작"
            try:
                with self.conn.cursor() as cursor:
                    sql = "SELECT word FROM ko_word WHERE can_use = TRUE AND available = TRUE ORDER BY RAND() LIMIT 1"
                    cursor.execute(sql)
                    result = cursor.fetchone()
                    return result[0] if result else "시작"
            except Exception as e:
                print(f"[오류] 랜덤 단어 조회 실패: {e}")
                return "시작"

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
                print(f"[오류] 관리자 단어 변경 실패: {e}")
                self.conn.rollback()
                return False

    def export_all_data_to_csv(self):
        with self.lock:
            self._ensure_connection()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = "backups"
            if not os.path.exists(backup_dir): os.makedirs(backup_dir)
            
            # [수정] game_status 테이블 추가
            tables = ["app_logs", "game_history", "game_status"]
            
            try:
                if not self.conn: return False, None
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
        with self.lock:
            self._ensure_connection()
            try:
                with self.conn.cursor() as cursor:
                    sql_word_reset = "UPDATE ko_word SET is_use = FALSE, is_use_date = NULL, is_use_user = NULL"
                    cursor.execute(sql_word_reset)
                    cursor.execute("TRUNCATE TABLE app_logs")
                    cursor.execute("TRUNCATE TABLE game_history")
                    # game_status는 히스토리 성격이므로 TRUNCATE 여부는 선택사항이나, 
                    # 보통 완전 리셋이면 날리는게 맞음. 여기선 포함.
                    cursor.execute("TRUNCATE TABLE game_status") 
                print("[시스템] 모든 DB 테이블이 초기화되었습니다.")
                return True
            except Exception as e:
                print(f"[오류] DB 초기화 실패: {e}")
                return False