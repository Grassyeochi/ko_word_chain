import os
import sys
import re
import io
from dotenv import load_dotenv

# 구글 API 관련 라이브러리
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ---------------------------------------------------------
# [1] 실행 경로 설정 (PyInstaller .exe 환경 완벽 호환)
# ---------------------------------------------------------
def get_base_path():
    """PyInstaller로 빌드된 환경과 일반 Python 스크립트 환경의 경로를 호환합니다."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

BASE_PATH = get_base_path()

# .env 파일 로드 (.exe 파일과 같은 폴더에 위치해야 함)
env_path = os.path.join(BASE_PATH, '.env')
load_dotenv(dotenv_path=env_path)

# 인증 파일 경로 설정 (BASE_PATH 기준)
CLIENT_SECRET_FILE = os.path.join(BASE_PATH, os.getenv('OAUTH_CLIENT_SECRET_PATH', 'client_secret.json'))
TOKEN_FILE = os.path.join(BASE_PATH, os.getenv('TOKEN_JSON_PATH', 'token.json'))
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


# ---------------------------------------------------------
# [2] 인증 및 다운로드 기본 함수
# ---------------------------------------------------------
def authenticate_gdrive():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def download_file(service, file_id, file_path):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()


# ---------------------------------------------------------
# [3] Task 1: word_chain_N.zip 동기화 로직
# ---------------------------------------------------------
def sync_word_chain_zip(service, gdrive_folder_id, local_path):
    if not os.path.exists(local_path):
        os.makedirs(local_path)

    pattern = r"word_chain_([0-9.]+)\.zip"
    
    # 로컬 경로의 가장 큰 N값 탐색
    local_max_n = -1.0
    for file_name in os.listdir(local_path):
        match = re.match(pattern, file_name)
        if match:
            local_max_n = max(local_max_n, float(match.group(1)))

    # 구글 드라이브 파일 탐색
    query = f"'{gdrive_folder_id}' in parents and name contains 'word_chain_' and mimeType='application/zip'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    gdrive_max_n = -1.0
    latest_gdrive_file = None
    for item in items:
        match = re.match(pattern, item['name'])
        if match:
            n_value = float(match.group(1))
            if n_value > gdrive_max_n:
                gdrive_max_n = n_value
                latest_gdrive_file = item

    # 비교 및 다운로드
    if gdrive_max_n > local_max_n and latest_gdrive_file:
        print(f"[보고] 새로운 버전(v{gdrive_max_n})이 확인되어 다운로드를 시작합니다.")
        download_path = os.path.join(local_path, latest_gdrive_file['name'])
        download_file(service, latest_gdrive_file['id'], download_path)
        print(f"[완료] {latest_gdrive_file['name']} 다운로드가 완료되었습니다.")
    else:
        print("[보고] 드라이브의 zip 파일 버전이 로컬과 같거나 작으므로 아무 작업도 수행하지 않습니다.")


# ---------------------------------------------------------
# [4] Task 2: 이미지 누락분 동기화 로직
# ---------------------------------------------------------
def sync_images(service, gdrive_folder_id, local_path):
    if not os.path.exists(local_path):
        os.makedirs(local_path)

    local_images = set(os.listdir(local_path))

    query = f"'{gdrive_folder_id}' in parents and mimeType contains 'image/'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    download_count = 0
    for item in items:
        if item['name'] not in local_images:
            print(f"[보고] 누락된 이미지 확인: {item['name']} 다운로드를 시작합니다.")
            download_path = os.path.join(local_path, item['name'])
            download_file(service, item['id'], download_path)
            download_count += 1
    
    if download_count == 0:
        print("[보고] 누락된 이미지 파일이 없습니다.")
    else:
        print(f"[완료] 총 {download_count}개의 이미지를 다운로드하였습니다.")


# ---------------------------------------------------------
# [5] 메인 실행부
# ---------------------------------------------------------
if __name__ == '__main__':
    # .env 파일에서 대상 폴더 정보 불러오기
    GDRIVE_FOLDER_A_ID = os.getenv('GDRIVE_FOLDER_A_ID')
    LOCAL_PATH_A = os.getenv('LOCAL_PATH_A')
    
    GDRIVE_FOLDER_B_ID = os.getenv('GDRIVE_FOLDER_B_ID')
    LOCAL_PATH_B = os.getenv('LOCAL_PATH_B')

    secret_name = os.getenv('OAUTH_CLIENT_SECRET_PATH', 'client_secret.json')

    # 설정값 누락 검증
    if not all([secret_name, GDRIVE_FOLDER_A_ID, LOCAL_PATH_A, GDRIVE_FOLDER_B_ID, LOCAL_PATH_B]):
        print("[경고 보고] .env 파일에 필요한 설정값이 일부 누락되었습니다. 설정을 다시 확인해 주십시오.")
    else:
        try:
            print("[보고] 구글 드라이브 인증을 진행합니다...")
            drive_service = authenticate_gdrive()
            
            print("\n--- [Task 1] word_chain_N.zip 동기화 검토 ---")
            sync_word_chain_zip(drive_service, GDRIVE_FOLDER_A_ID, LOCAL_PATH_A)

            print("\n--- [Task 2] 이미지 폴더 누락본 동기화 검토 ---")
            sync_images(drive_service, GDRIVE_FOLDER_B_ID, LOCAL_PATH_B)
            
            print("\n[보고] 모든 동기화 작업이 정상적으로 종료되었습니다.")
            
        except Exception as e:
            print(f"\n[오류 보고] 실행 중 다음 오류가 발생했습니다:\n{e}")
            
    # .exe 실행 시 프로그램 창이 즉시 닫히는 것을 방지
    input("\n프로그램을 종료하려면 엔터(Enter) 키를 누르십시오...")