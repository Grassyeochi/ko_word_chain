import os
import glob
import re
import zipfile
import subprocess
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. 환경 변수 로드 (.env)
load_dotenv()

LOCAL_WORKSPACE_PATH = os.getenv("LOCAL_WORKSPACE_PATH")
GDRIVE_PATH = os.getenv("GDRIVE_PATH") # Google Drive 폴더 ID
GDRIVE_CREDENTIALS_JSON = os.getenv("GDRIVE_CREDENTIALS_JSON")

def main():
    print("[보고] 작업을 시작합니다.")

    # 4. PyInstaller 빌드 실행
    print("[진행] PyInstaller를 통해 실행 파일을 빌드합니다.")
    build_command = [
        "pyinstaller", "--noconfirm", "--onefile", "--noconsole", "--clean", 
        "--name", "ChzzkWordChain", "--collect-all", "certifi", "main.py"
    ]
    subprocess.run(build_command, cwd=LOCAL_WORKSPACE_PATH, check=True)

    # 5. 빌드 후 생성된 spec 파일 삭제
    spec_file_path = os.path.join(LOCAL_WORKSPACE_PATH, "ChzzkWordChain.spec")
    if os.path.exists(spec_file_path):
        os.remove(spec_file_path)
        print("[진행] ChzzkWordChain.spec 파일이 삭제되었습니다.")

    # 6. 실행 파일 압축 및 네이밍 (N 값 계산)
    dist_dir = os.path.join(LOCAL_WORKSPACE_PATH, "dist")
    exe_file_path = os.path.join(dist_dir, "ChzzkWordChain.exe")
    
    zip_pattern = os.path.join(dist_dir, "word_chain_0.*.zip")
    existing_zips = glob.glob(zip_pattern)
    
    max_m = 0
    for zip_file in existing_zips:
        filename = os.path.basename(zip_file)
        match = re.search(r'word_chain_0\.(\d+)\.zip', filename)
        if match:
            m = int(match.group(1))
            if m > max_m:
                max_m = m
                
    n = max_m + 1
    zip_filename = f"word_chain_0.{n}.zip"
    zip_filepath = os.path.join(dist_dir, zip_filename)

    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(exe_file_path, arcname="ChzzkWordChain.exe")
    print(f"[진행] 파일 압축 완료: {zip_filename}")

    # 7. 구글 드라이브 업로드
    print("[진행] 구글 드라이브 업로드를 시작합니다.")
    if GDRIVE_CREDENTIALS_JSON and os.path.exists(GDRIVE_CREDENTIALS_JSON):
        credentials = service_account.Credentials.from_service_account_file(
            GDRIVE_CREDENTIALS_JSON, 
            scopes=["https://www.googleapis.com/auth/drive.file"]
        )
        drive_service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': zip_filename,
            'parents': [GDRIVE_PATH]
        }
        media = MediaFileUpload(zip_filepath, mimetype='application/zip')
        
        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        print("[완료] 구글 드라이브 업로드가 완료되었습니다.")
    else:
        print("[경고] 구글 API 인증 정보(JSON)를 찾을 수 없어 드라이브 업로드를 건너뜁니다.")

    print("[보고] 모든 지시 사항의 처리가 완료되었습니다.")

if __name__ == "__main__":
    main()