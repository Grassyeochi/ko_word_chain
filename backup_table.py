import os
import shutil
import subprocess
import zipfile
from datetime import datetime
import pymysql
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = int(os.getenv("DB_PORT", 3306))

BACKUP_TARGET_TABLE = os.getenv("BACKUP_TARGET_TABLE")
MYSQL_SERVICE_NAME = os.getenv("MYSQL_SERVICE_NAME")
SOURCE_IBD_PATH = os.getenv("SOURCE_IBD_PATH")
BACKUP_TARGET_DIR = os.getenv("BACKUP_TARGET_DIR")

def backup_and_zip():
    # 1. 타임스탬프 및 경로 설정 (YYMMDD_HH24MISS)
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    
    # 개별 파일명 설정
    sql_filename = f"{BACKUP_TARGET_TABLE}.sql"
    ibd_filename = f"{BACKUP_TARGET_TABLE}.ibd"
    zip_filename = f"{BACKUP_TARGET_TABLE}({timestamp}).zip"
    
    # 절대 경로 설정
    sql_path = os.path.join(BACKUP_TARGET_DIR, sql_filename)
    ibd_path = os.path.join(BACKUP_TARGET_DIR, ibd_filename)
    zip_path = os.path.join(BACKUP_TARGET_DIR, zip_filename)

    print(f"[{datetime.now()}] 백업 및 압축 프로세스를 시작합니다.")

    try:
        # --- [STEP 1] 스키마(DDL) 백업 ---
        conn = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
            database=DB_NAME, port=DB_PORT, charset='utf8mb4'
        )
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW CREATE TABLE {BACKUP_TARGET_TABLE}")
            create_table_stmt = cursor.fetchone()[1]
            with open(sql_path, "w", encoding="utf-8") as f:
                f.write(create_table_stmt + ";\n")
        conn.close()
        print(f" - 스키마 생성 완료: {sql_filename}")

        # --- [STEP 2] MySQL 서비스 중지 및 .ibd 복사 ---
        print(f" - 서비스 '{MYSQL_SERVICE_NAME}' 중지 중...")
        subprocess.run(["net", "stop", MYSQL_SERVICE_NAME], check=True, capture_output=True)
        
        shutil.copy2(SOURCE_IBD_PATH, ibd_path)
        print(f" - 물리 파일 복사 완료: {ibd_filename}")

        # --- [STEP 3] MySQL 서비스 재시작 ---
        print(f" - 서비스 '{MYSQL_SERVICE_NAME}' 재시작 중...")
        subprocess.run(["net", "start", MYSQL_SERVICE_NAME], check=True, capture_output=True)

        # --- [STEP 4] 압축 파일 생성 (ZIP) ---
        print(f" - 압축 진행 중: {zip_filename}")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
            backup_zip.write(sql_path, arcname=sql_filename)
            backup_zip.write(ibd_path, arcname=ibd_filename)
        
        # --- [STEP 5] 임시 파일 정리 ---
        if os.path.exists(zip_path):
            os.remove(sql_path)
            os.remove(ibd_path)
            print(f"[{datetime.now()}] 모든 작업 완료. 최종 파일: {zip_path}")

    except subprocess.CalledProcessError as e:
        print(f"[오류] 서비스 제어 실패 (관리자 권한 필요): {e}")
    except Exception as e:
        print(f"[오류] 백업 중 예외 발생: {e}")
        # 오류 발생 시 서비스가 중지되어 있다면 다시 시작 시도
        subprocess.run(["net", "start", MYSQL_SERVICE_NAME], capture_output=True)

if __name__ == "__main__":
    if not os.path.exists(BACKUP_TARGET_DIR):
        os.makedirs(BACKUP_TARGET_DIR)
    backup_and_zip()