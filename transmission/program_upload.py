import os
import sys
import glob
import re
import zipfile
import subprocess
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. 환경 변수 로드 (.env)
load_dotenv()

LOCAL_WORKSPACE_PATH = os.getenv("LOCAL_WORKSPACE_PATH")
GDRIVE_PATH = os.getenv("GDRIVE_PATH") # Google Drive 폴더 ID
GDRIVE_CREDENTIALS_JSON = os.getenv("GDRIVE_CREDENTIALS_JSON") # OAuth 클라이언트 JSON 경로

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate_gdrive():
    """
    OAuth 2.0 인증 및 token.json 관리 함수
    반환값: (인증 객체, 토큰_재발급_발생_여부_부울)
    """
    creds = None
    token_renewed = False
    token_path = os.path.join(LOCAL_WORKSPACE_PATH, 'token.json')
    
    # 이전에 인증하여 저장된 토큰이 있는지 확인
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    # 유효한 인증 정보가 없거나 만료된 경우 (재발급 분기)
    if not creds or not creds.valid:
        token_renewed = True # 재발급 플래그 활성화
        
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                print("[보고] 기존 토큰이 만료되어 백그라운드에서 갱신(재발급)되었습니다.")
            except Exception as e:
                print(f"[경고] 토큰 갱신 실패. 수동 재인증을 진행합니다: {e}")
                flow = InstalledAppFlow.from_client_secrets_file(GDRIVE_CREDENTIALS_JSON, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            print("[보고] 유효한 토큰 파일이 없어 신규 발급(브라우저 인증)을 진행합니다.")
            flow = InstalledAppFlow.from_client_secrets_file(GDRIVE_CREDENTIALS_JSON, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # 새로운 인증 정보를 token.json에 저장
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            print("[보고] 새로운 토큰이 token.json 파일에 저장되었습니다.")
            
    return creds, token_renewed

def main():
    print("[보고] 작업을 시작합니다.")

    # 1. 토큰 유효성 사전 검사 및 재발급 처리
    print("[진행] 구글 드라이브 인증 토큰의 유효성을 검사합니다.")
    creds, token_renewed = authenticate_gdrive()

    # 2. 토큰이 재발급(신규 또는 갱신)된 경우, 빌드 없이 프로그램 종료
    if token_renewed:
        print("[보고] 지시하신 대로 토큰 재발급이 수행되었으므로, PyInstaller 빌드 및 업로드를 생략하고 프로그램을 종료합니다.")
        sys.exit(0)
        
    print("[보고] 토큰이 유효합니다. 후속 빌드 및 배포 작업을 계속 진행합니다.")

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

    # 7. 구글 드라이브 업로드 (유효한 creds 사용)
    print("[진행] 구글 드라이브 업로드를 시작합니다.")
    try:
        drive_service = build('drive', 'v3', credentials=creds)
        
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
        print("[완료] 구글 드라이브 업로드가 성공적으로 완료되었습니다.")
    except Exception as e:
        print(f"[오류] 드라이브 업로드 중 문제가 발생했습니다: {e}")

    print("[보고] 모든 지시 사항의 처리가 완료되었습니다.")

if __name__ == "__main__":
    main()