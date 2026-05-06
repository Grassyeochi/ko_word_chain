import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from dotenv import load_dotenv

def perform_cold_backup():
    # 1. 환경 변수 로드
    load_dotenv()
    
    service_name = os.getenv("MYSQL_SERVICE_NAME")
    source_path = os.getenv("SOURCE_IBD_PATH")
    backup_dir = os.getenv("BACKUP_TARGET_DIR")
    
    if not all([service_name, source_path, backup_dir]):
        print("[오류] .env 파일 설정값을 확인해 주십시오.")
        return

    # 경로 내 역슬래시 문제 방지를 위한 정규화
    source_path = os.path.normpath(source_path)
    backup_dir = os.path.normpath(backup_dir)

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    file_name = os.path.basename(source_path)
    temp_copied_path = os.path.join(backup_dir, file_name)
    
    # 2. 지시하신 YYMMDD_HH24MISS 형식 반영
    # %y: 년(2자리), %m: 월, %d: 일, %H: 시(24시), %M: 분, %S: 초
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    zip_filename = f"backup_{timestamp}.zip"
    zip_filepath = os.path.join(backup_dir, zip_filename)

    try:
        # 3. 사전 작업: MySQL 서비스 중지
        print(f"[보고] {service_name} 서비스를 중지합니다.")
        subprocess.run(["net", "stop", service_name], check=True)
        
        # 4. 파일 복사 (기존 파일이 있다면 덮어씀)
        print(f"[보고] {file_name} 복사를 시작합니다.")
        shutil.copy2(source_path, temp_copied_path)
        
    except subprocess.CalledProcessError:
        print("[오류] 서비스 제어 권한이 없습니다. VS Code를 '관리자 권한'으로 실행했는지 확인하십시오.")
        return
    except Exception as e:
        print(f"[오류] 복사 중 예외 발생: {e}")
        return
    finally:
        # 5. 사후 작업: MySQL 서비스 재시작
        print(f"[보고] {service_name} 서비스를 다시 가동합니다.")
        subprocess.run(["net", "start", service_name], check=True)

    # 6. 지정된 형식(YYMMDD_HH24MISS)으로 압축 저장
    try:
        print(f"[보고] 압축 파일 생성 중: {zip_filename}")
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(temp_copied_path, arcname=file_name)
        
        # 압축 완료 후 임시 복사본 제거 (선택 사항, 필요 시 유지 가능)
        if os.path.exists(temp_copied_path):
            os.remove(temp_copied_path)
            
        print(f"[완료] 백업이 성공적으로 종료되었습니다. 파일명: {zip_filename}")
        
    except Exception as e:
        print(f"[오류] 압축 처리 중 예외 발생: {e}")

if __name__ == "__main__":
    perform_cold_backup()