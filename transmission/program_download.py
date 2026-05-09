import os
import re
import io
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# .env 파일 로드
load_dotenv()

# .env에서 인증 정보 파일(json) 경로 가져오기
SERVICE_ACCOUNT_FILE = os.getenv('CREDENTIALS_JSON_PATH')
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# 1. 인증 및 서비스 객체 생성
def authenticate_gdrive():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

# 2. 구글 드라이브 파일 다운로드 함수
def download_file(service, file_id, file_path):
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(file_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()

# 3. 위치 A: word_chain_N.zip 파일 비교 및 다운로드
def sync_word_chain_zip(service, gdrive_folder_id, local_path):
    if not os.path.exists(local_path):
        os.makedirs(local_path)

    pattern = r"word_chain_([0-9.]+)\.zip"
    
    local_max_n = -1.0
    for file_name in os.listdir(local_path):
        match = re.match(pattern, file_name)
        if match:
            local_max_n = max(local_max_n, float(match.group(1)))

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

    if gdrive_max_n > local_max_n and latest_gdrive_file:
        print(f"[보고] 새로운 버전(v{gdrive_max_n})이 확인되어 다운로드를 시작합니다.")
        download_path = os.path.join(local_path, latest_gdrive_file['name'])
        download_file(service, latest_gdrive_file['id'], download_path)
        print(f"[완료] {latest_gdrive_file['name']} 다운로드가 완료되었습니다.")
    else:
        print("[보고] 드라이브의 zip 파일 버전이 로컬과 같거나 작으므로 아무 작업도 수행하지 않습니다.")

# 4. 위치 B: 이미지 파일 비교 및 누락분 다운로드
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

# 메인 실행부
if __name__ == '__main__':
    # .env 파일에서 환경 변수 불러오기
    GDRIVE_FOLDER_A_ID = os.getenv('GDRIVE_FOLDER_A_ID')
    LOCAL_PATH_A = os.getenv('LOCAL_PATH_A')
    
    GDRIVE_FOLDER_B_ID = os.getenv('GDRIVE_FOLDER_B_ID')
    LOCAL_PATH_B = os.getenv('LOCAL_PATH_B')

    # 환경 변수 누락 여부 검증
    if not all([SERVICE_ACCOUNT_FILE, GDRIVE_FOLDER_A_ID, LOCAL_PATH_A, GDRIVE_FOLDER_B_ID, LOCAL_PATH_B]):
        print("[경고 보고] .env 파일에 필요한 설정값이 일부 누락되었습니다. 설정을 다시 확인해 주십시오.")
    else:
        # 서비스 객체 초기화 및 동기화 실행
        try:
            drive_service = authenticate_gdrive()
            
            print("--- [Task 1] word_chain_N.zip 동기화 검토 ---")
            sync_word_chain_zip(drive_service, GDRIVE_FOLDER_A_ID, LOCAL_PATH_A)

            print("\n--- [Task 2] 이미지 폴더 누락본 동기화 검토 ---")
            sync_images(drive_service, GDRIVE_FOLDER_B_ID, LOCAL_PATH_B)
            
        except Exception as e:
            print(f"[오류 보고] 실행 중 다음 오류가 발생했습니다: {e}")