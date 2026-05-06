import os
import subprocess
from dotenv import load_dotenv

def migrate_mysql_table():
    # 1. .env 파일의 환경변수 로드
    load_dotenv()

    # 로컬 DB 정보 할당
    local_host = os.getenv('DB_HOST')
    local_user = os.getenv('DB_USER')
    local_pwd = os.getenv('DB_PASSWORD')
    local_db = os.getenv('DB_NAME')
    # local_port = os.getenv('DB_PORT') # 필요시 추가 설정 가능

    # 원격지 DB 정보 할당
    remote_host = os.getenv('DB_HOST_REAL')
    remote_user = os.getenv('DB_USER_REAL')
    remote_pwd = os.getenv('DB_USER_PWD')
    remote_db = os.getenv('DB_NAME_REAL')

    target_table = 'ko_word'

    print("작업을 시작합니다...")

    # 2. 원격지 테이블 삭제 (Drop)
    print(f"[{target_table}] 원격지 테이블 삭제를 시도합니다.")
    drop_command = f'mysql -h {remote_host} -u {remote_user} -p{remote_pwd} {remote_db} -e "drop table {target_table};"'
    
    try:
        subprocess.run(drop_command, shell=True, check=True)
        print("원격지 테이블이 성공적으로 삭제되었습니다.")
    except subprocess.CalledProcessError:
        print("[참고] 원격지에 삭제할 테이블이 존재하지 않거나 무시할 수 있는 오류가 발생했습니다. 작업을 계속 진행합니다.")

    # 3. 테이블 복사 (mysqldump 및 파이프 전송)
    print("데이터 덤프 및 원격지 전송을 시작합니다.")
    # 지시하신 명령어를 기반으로 구성 (DB_HOST 변수 활용을 위해 -h 옵션 추가)
    copy_command = (
        f"mysqldump -h {local_host} -u {local_user} -p{local_pwd} {local_db} {target_table} | "
        f"mysql -h {remote_host} -u {remote_user} -p{remote_pwd} {remote_db}"
    )

    try:
        subprocess.run(copy_command, shell=True, check=True)
        print("테이블 복사가 완료되었습니다. 모든 프로세스를 정상 종료합니다.")
    except subprocess.CalledProcessError as e:
        print(f"[오류] 테이블 복사 과정에서 문제가 발생했습니다: {e}")

if __name__ == "__main__":
    migrate_mysql_table()