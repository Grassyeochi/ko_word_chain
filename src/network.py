# src/network.py
import os
import json
import time
import requests
import websockets
import asyncio
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from .signals import GameSignals

try:
    import pytchat
except ImportError:
    pytchat = None
    print("[경고] pytchat 라이브러리가 설치되지 않았습니다. 유튜브 연동이 불가능합니다.")

class ChzzkAuthHandler(BaseHTTPRequestHandler):
    auth_code = None
    
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        if 'code' in query:
            ChzzkAuthHandler.auth_code = query['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("<h1>인증이 완료되었습니다! 창을 닫고 콘솔을 확인해주세요.</h1>".encode('utf-8'))
        elif 'error' in query:
            self.send_response(400)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            error_msg = query.get('error_description', ['알 수 없는 오류'])[0]
            self.wfile.write(f"<h1>인증 실패: {error_msg}</h1>".encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()

class ChzzkAuthManager:
    def __init__(self):
        self.client_id = os.getenv("CHZZK_CLIENT_ID")
        self.client_secret = os.getenv("CHZZK_CLIENT_SECRET")
        self.redirect_uri = "http://localhost:8080"
        self.token_file = "chzzk_token.json"
        
        self.auth_base_url = "https://chzzk.naver.com/account-interlock"
        self.token_url = "https://openapi.chzzk.naver.com/auth/v1/token"

    def load_tokens(self):
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def save_tokens(self, data):
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get_valid_access_token(self):
        tokens = self.load_tokens()
        
        if tokens and "accessToken" in tokens:
            if tokens.get("expiresAt", 0) > time.time():
                return tokens["accessToken"]
            
            print("[시스템] 액세스 토큰이 만료되었습니다. 리프레시 토큰으로 갱신을 시도합니다.")
            new_tokens = self.refresh_token(tokens.get("refreshToken"))
            if new_tokens:
                return new_tokens["accessToken"]
        
        print("[시스템] 유효한 토큰이 없거나 리프레시가 불가합니다. 처음부터 발급을 진행합니다.")
        return self.issue_new_token()

    def refresh_token(self, refresh_token):
        if not refresh_token:
            return None
            
        data = {
            "grantType": "refresh_token",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "refreshToken": refresh_token
        }
        try:
            # OAuth2 표준에 맞춰 json=data 가 아닌 폼 데이터(data=data)로 전송
            res = requests.post(self.token_url, data=data)
            if res.status_code == 200:
                body = res.json()
                
                # 치지직 오픈 API 래퍼 구조(content) 파싱
                if body.get("code") == 200 and "content" in body:
                    token_data = body["content"]
                else:
                    token_data = body

                if "accessToken" not in token_data:
                    print(f"[오류] 리프레시 토큰 응답 내 데이터 누락: {body}")
                    return None

                token_data["expiresAt"] = time.time() + int(token_data.get("expiresIn", 3600)) - 60
                
                if "refreshToken" not in token_data:
                    token_data["refreshToken"] = refresh_token
                    
                self.save_tokens(token_data)
                print("[시스템] 토큰 리프레시 성공!")
                return token_data
            else:
                print(f"[오류] 리프레시 통신 거절: HTTP {res.status_code} - {res.text}")
                return None
        except Exception as e:
            print(f"[오류] 리프레시 프로세스 예외: {e}")
            return None

    def issue_new_token(self):
        ChzzkAuthHandler.auth_code = None
        server = HTTPServer(('localhost', 8080), ChzzkAuthHandler)
        state = "security_state_string"
        
        auth_url = f"{self.auth_base_url}?clientId={self.client_id}&redirectUri={self.redirect_uri}&state={state}"
        
        print(f"\n========== [치지직 API 인증 필요] ==========")
        print(f"브라우저가 열립니다. 치지직 로그인 및 권한 인가를 진행해주세요.")
        print(f"만약 브라우저가 자동으로 열리지 않는다면 아래 링크로 직접 접속하세요:")
        print(auth_url)
        print(f"============================================\n")
        
        webbrowser.open(auth_url)
        
        while ChzzkAuthHandler.auth_code is None:
            server.handle_request()
            
        code = ChzzkAuthHandler.auth_code
        server.server_close()
        
        data = {
            "grantType": "authorization_code",
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "code": code,
            "state": state
        }
        
        # OAuth2 표준 폼 데이터 전송
        res = requests.post(self.token_url, data=data)
        
        if res.status_code == 200:
            body = res.json()
            
            if body.get("code") == 200 and "content" in body:
                token_data = body["content"]
            else:
                token_data = body
                
            if "accessToken" in token_data:
                token_data["expiresAt"] = time.time() + int(token_data.get("expiresIn", 3600)) - 60
                self.save_tokens(token_data)
                print("[시스템] 토큰 신규 발급이 성공적으로 완료되었습니다.")
                return token_data["accessToken"]
            else:
                raise Exception(f"신규 토큰 발급 파싱 실패(API 응답 이상): {body}")
        else:
            raise Exception(f"신규 토큰 발급 통신 오류: HTTP {res.status_code} - {res.text}")


class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "치지직"
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.signals = signals
        self.running = True
        self.auth_manager = ChzzkAuthManager()
        self.access_token = None
        self.chat_channel_id = None

    def stop(self):
        self.running = False

    async def _async_get(self, url, headers=None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(requests.get, url, headers=headers, timeout=5))

    async def _async_post(self, url, json_data=None, headers=None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(requests.post, url, json=json_data, headers=headers, timeout=5))

    def check_live_status_sync(self):
        if not self.channel_id: return False, "Channel ID 누락"
        try:
            token = self.auth_manager.get_valid_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            status_url = f"https://openapi.chzzk.naver.com/open/v1/channels/{self.channel_id}/live-status"
            res = requests.get(status_url, headers=headers, timeout=5)
            if res.status_code != 200: return False, f"API 오류 ({res.status_code})"
            data = res.json()
            content = data.get('content', {})
            live_status = content.get('status')
            return (True, "방송 중") if live_status == 'OPEN' else (False, f"방송 종료 ({live_status})")
        except Exception as e: return False, str(e)

    async def send_chat(self, message: str):
        if not self.chat_channel_id or not self.access_token:
            print("[오류] 채팅 채널 ID나 액세스 토큰이 확인되지 않아 채팅을 전송할 수 없습니다.")
            return False
            
        send_url = f"https://openapi.chzzk.naver.com/open/v1/chats/send"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "chatChannelId": self.chat_channel_id,
            "message": message
        }
        
        try:
            res = await self._async_post(send_url, json_data=payload, headers=headers)
            if res.status_code == 200:
                return True
            else:
                print(f"[오류] 채팅 전송 실패: {res.text}")
                return False
        except Exception as e:
            print(f"[오류] 채팅 전송 예외 발생: {e}")
            return False

    async def run(self):
        if not self.channel_id:
            self.signals.log_request.emit(10, "Chzzk", "환경변수 누락", None)
            return
            
        try:
            self.access_token = self.auth_manager.get_valid_access_token()
        except Exception as e:
            self.signals.log_request.emit(10, "Chzzk", "인증 실패", str(e))
            self.signals.gui_log_message.emit(f"[치지직] API 인증 실패. Client ID/Secret을 확인하십시오.")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        while self.running:
            try:
                status_url = f"https://openapi.chzzk.naver.com/open/v1/channels/{self.channel_id}/live-status"
                res_obj = await self._async_get(status_url, headers=headers)
                
                if res_obj.status_code == 401:
                    self.signals.gui_log_message.emit("[치지직] 토큰 만료 감지. 백그라운드 재발급 진행...")
                    self.access_token = self.auth_manager.get_valid_access_token()
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    continue

                res = res_obj.json()
                content = res.get('content', {})
                live_status = content.get('status')
                
                if live_status != 'OPEN':
                    self.signals.gui_log_message.emit(f"[{self.platform_name}] 방송 종료 감지. 10초 후 재접속 시도...")
                    self.signals.stream_offline.emit(self.platform_name)
                    for _ in range(10): 
                        if not self.running: break
                        await asyncio.sleep(1)
                    continue

                self.chat_channel_id = content['chatChannelId']
                
                token_url = f"https://openapi.chzzk.naver.com/open/v1/chats/access-token?channelId={self.chat_channel_id}"
                token_res_obj = await self._async_get(token_url, headers=headers)
                token_res = token_res_obj.json()
                
                # 웹소켓 액세스 토큰 파싱 안전장치
                token_content = token_res.get('content', token_res)
                ws_access_token = token_content.get('accessToken')
                
                ws_url = "wss://kr-ss1.chat.naver.com/chat"
                TIMEOUT_SECONDS = float(os.getenv("WS_TIMEOUT", 600.0))

                async with websockets.connect(ws_url, ping_interval=None) as websocket:
                    self.signals.log_request.emit(1, "Chzzk", "공식 오픈 API 채팅 서버 연결 성공", None)
                    self.signals.stream_connected.emit(self.platform_name)
                    
                    await websocket.send(json.dumps({
                        "ver": "2", "cmd": 100, "svcid": "game", "cid": self.chat_channel_id, "tid": 1,
                        "bdy": {"uid": None, "devType": 2001, "accTkn": ws_access_token, "auth": "READ"}
                    }))

                    while self.running:
                        try:
                            res = await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT_SECONDS)
                            data = json.loads(res)
                            cmd = data.get('cmd')
                            
                            if cmd == 93101: 
                                for chat in data.get('bdy', []):
                                    msg = chat.get('msg', '').strip()
                                    profile = json.loads(chat.get('profile', '{}'))
                                    nickname = profile.get('nickname', '익명')
                                    if "클린봇" in msg: continue 
                                    if msg.startswith("!"):
                                        content = msg[1:].strip()
                                        if content:
                                            self.signals.word_detected.emit(self.platform_name, nickname, content.split()[0])
                                            
                            elif cmd == 0:
                                await websocket.send(json.dumps({"ver": "2", "cmd": 10000}))
                        except asyncio.TimeoutError:
                            self.signals.gui_log_message.emit(f"[{self.platform_name}] 응답 지연. 소켓을 재연결합니다...")
                            break 
                        except Exception: break 
            except Exception as e:
                self.signals.log_request.emit(9, "Chzzk", "공식 API 접속 오류", str(e))
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 공식 API 연결 오류. 10초 후 재시도...")
                self.signals.stream_offline.emit(self.platform_name)
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)
                continue
            
            if self.running: await asyncio.sleep(3)


class YouTubeMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "유튜브"
        self.video_id = os.getenv("YOUTUBE_VIDEO_ID")
        self.signals = signals
        self.running = True

    def stop(self):
        self.running = False

    def check_live_status_sync(self):
        if not pytchat: return False, "모듈 미설치"
        if not self.video_id: return False, "Video ID 누락"
        try:
            chat = pytchat.create(video_id=self.video_id, interruptable=False)
            if chat.is_alive():
                chat.terminate()
                return True, "방송 중"
            else: return False, "방송 종료/대기/오류"
        except Exception as e: return False, f"오류: {str(e)}"

    async def run(self):
        if not pytchat:
            self.signals.gui_log_message.emit("[오류] pytchat 모듈 미설치로 유튜브 기능 비활성화")
            return
        if not self.video_id:
            self.signals.log_request.emit(10, "YouTube", "환경변수 YOUTUBE_VIDEO_ID 누락", None)
            return

        while self.running:
            try:
                chat = pytchat.create(video_id=self.video_id, interruptable=False)
                if not chat.is_alive():
                    self.signals.gui_log_message.emit(f"[{self.platform_name}] 방송을 찾을 수 없음. 10초 후 재시도...")
                    self.signals.stream_offline.emit(self.platform_name)
                    for _ in range(10):
                        if not self.running: break
                        await asyncio.sleep(1)
                    continue

                self.signals.stream_connected.emit(self.platform_name)
                self.signals.log_request.emit(1, "YouTube", f"채팅 리스너 시작 ({self.video_id})", None)

                while self.running:
                    if not chat.is_alive():
                        self.signals.gui_log_message.emit(f"[{self.platform_name}] 라이브러리 연결 끊김")
                        break 
                    try:
                        data = chat.get()
                        items = data.sync_items()
                        for c in items:
                            msg = c.message.strip()
                            nickname = c.author.name
                            if msg.startswith("!"):
                                content = msg[1:].strip()
                                if content:
                                    self.signals.word_detected.emit(self.platform_name, nickname, content.split()[0])
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        print(f"[YouTube Warning] 데이터 읽기 중 경미한 오류: {e}")
                        await asyncio.sleep(1)
                        continue

                self.signals.gui_log_message.emit(f"[{self.platform_name}] 연결 끊김. 10초 후 재접속...")
                self.signals.stream_offline.emit(self.platform_name)
                try: chat.terminate()
                except: pass
                
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)

            except Exception as e:
                self.signals.log_request.emit(9, "YouTube", "접속 오류", str(e))
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 오류 발생({e}). 10초 후 재시도...")
                self.signals.stream_offline.emit(self.platform_name)
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)