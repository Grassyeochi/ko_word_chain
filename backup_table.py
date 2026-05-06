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
        print("[오류] .env 파일에서 필요한 경로 및 설정값을 불러오지 못했습니다.")
        return

    # 백업 디렉터리가 존재하지 않을 경우 자동 생성
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    file_name = os.path.basename(source_path)
    temp_copied_path = os.path.join(backup_dir, file_name)
    
    # 2. 지시하신 YYMMDD 형식의 날짜 문자열 및 압축 파일명 생성
    today_str = datetime.now().strftime("%y%m%d")
    zip_filename = f"backup_{today_str}.zip"
    zip_filepath = os.path.join(backup_dir, zip_filename)

    try:
        # 3. 사전 작업: MySQL 서비스 중지 (데이터 일관성 확보를 위한 콜드 백업 프로세스)
        print(f"[보고] {service_name} 서비스를 중지합니다.")
        subprocess.run(["net", "stop", service_name], check=True)
        
        # 4. .ibd 파일 복사 (동일 파일 존재 시 shutil.copy2가 자동으로 덮어씀)
        print(f"[보고] {file_name} 파일을 백업 폴더로 복사합니다.")
        shutil.copy2(source_path, temp_copied_path)
        
    except subprocess.CalledProcessError:
        print("[오류] MySQL 서비스 제어에 실패했습니다. 관리자 권한으로 실행되었는지 확인해 주십시오.")
        return
    except Exception as e:
        print(f"[오류] 파일 복사 중 문제가 발생했습니다: {e}")
        return
    finally:
        # 5. 사후 작업: MySQL 서비스 재시작 (복사 완료 후 또는 오류 발생 시에도 반드시 실행)
        print(f"[보고] {service_name} 서비스를 재시작합니다.")
        try:
            subprocess.run(["net", "start", service_name], check=True)
        except subprocess.CalledProcessError:
            print("[오류] MySQL 서비스 재시작에 실패했습니다. 수동 확인이 필요합니다.")

    # 6. 복사된 파일을 압축하여 최종 저장
    try:
        print(f"[보고] 복사된 파일을 {zip_filename} 이름으로 압축합니다.")
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 아카이브 내에서 전체 경로가 아닌 파일명만 유지하도록 arcname 지정
            zipf.write(temp_copied_path, arcname=file_name)
        
        print("[보고] 콜드 백업 및 압축 작업이 성공적으로 완료되었습니다.")
        
    except Exception as e:
        print(f"[오류] 파일 압축 중 문제가 발생했습니다: {e}")

if __name__ == "__main__":
    perform_cold_backup()