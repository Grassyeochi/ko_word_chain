import os
import threading
import mysql.connector
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class DBSynchronizer:
    def __init__(self):
        # 환경 변수에서 설정 불러오기
        self.table_name = os.getenv("DB_TABLE_NAME")
        
        self.config_a = {
            'host': os.getenv("DB_HOST"),
            'user': os.getenv("DB_USER"),
            'password': os.getenv("DB_PASSWORD"),
            'database': os.getenv("DB_NAME")
        }
        
        self.config_b = {
            'host': os.getenv("DB_HOST_REAL"),
            'user': os.getenv("DB_USER_REAL"),
            'password': os.getenv("DB_PASSWORD_REAL"),
            'database': os.getenv("DB_NAME_REAL")
        }

    def _get_connection(self, config):
        """DB 연결 헬퍼 함수"""
        return mysql.connector.connect(**config)

    def _sync_process(self):
        """실제 동기화 로직이 실행되는 함수 (별도 스레드에서 실행됨)"""
        print(">>> 동기화 시작...")
        
        conn_a = None
        conn_b = None
        
        try:
            # 1. A 컴퓨터에서 데이터 가져오기
            conn_a = self._get_connection(self.config_a)
            cursor_a = conn_a.cursor(dictionary=True)
            
            # A의 모든 데이터 조회
            cursor_a.execute(f"SELECT * FROM {self.table_name}")
            rows = cursor_a.fetchall()
            
            if not rows:
                print(">>> A 컴퓨터에 동기화할 데이터가 없습니다.")
                return

            # 컬럼 이름 추출 (동적 쿼리 생성을 위해)
            columns = list(rows[0].keys())
            
            # 2. B 컴퓨터에 데이터 반영하기
            conn_b = self._get_connection(self.config_b)
            cursor_b = conn_b.cursor()

            # INSERT INTO ... ON DUPLICATE KEY UPDATE 구문 생성
            # (PK가 중복되면 UPDATE, 아니면 INSERT)
            cols_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            update_str = ", ".join([f"{col}=VALUES({col})" for col in columns])
            
            sql = f"""
                INSERT INTO {self.table_name} ({cols_str}) 
                VALUES ({placeholders}) 
                ON DUPLICATE KEY UPDATE {update_str}
            """

            # 데이터 변환 (딕셔너리 값들을 튜플 리스트로)
            data_values = [tuple(row.values()) for row in rows]

            # 배치 실행 (executemany로 성능 최적화)
            cursor_b.executemany(sql, data_values)
            conn_b.commit()
            
            print(f">>> 동기화 완료: {cursor_b.rowcount}개의 행이 처리되었습니다.")

        except mysql.connector.Error as err:
            print(f"!!! 에러 발생: {err}")
        
        finally:
            if conn_a and conn_a.is_connected(): conn_a.close()
            if conn_b and conn_b.is_connected(): conn_b.close()

    def start_sync(self):
        """
        관리자 버튼 클릭 시 호출되는 함수.
        UI 프리징 방지를 위해 스레드(비동기)로 실행합니다.
        """
        sync_thread = threading.Thread(target=self._sync_process)
        sync_thread.start()

# --- 사용 예시 ---
if __name__ == "__main__":
    # 실제 프로그램에서는 이 부분이 '동기화 버튼' 클릭 이벤트에 해당합니다.
    sync_manager = DBSynchronizer()
    
    print("메인 프로그램 실행 중 (UI 안 멈춤)")
    sync_manager.start_sync() # 비동기 실행
    print("메인 프로그램은 계속 다른 작업을 수행합니다...")