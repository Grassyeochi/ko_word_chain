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

    def get_valid_access_token(self, force_refresh=False, allow_interaction=True):
        tokens = self.load_tokens()
        
        if tokens and "accessToken" in tokens:
            if not force_refresh and tokens.get("expiresAt", 0) > time.time():
                return tokens["accessToken"]
            
            print("[시스템] 토큰 갱신을 시도합니다.")
            new_tokens = self.refresh_token(tokens.get("refreshToken"))
            if new_tokens:
                return new_tokens["accessToken"]
        
        if allow_interaction:
            print("[시스템] 유효한 토큰이 없거나 리프레시가 불가합니다. 신규 발급을 진행합니다.")
            return self.issue_new_token()
        else:
            raise Exception("토큰 갱신 불가. 권한을 확인하거나 재시작하십시오.")

    def refresh_token(self, refresh_token):
        if not refresh_token: return None
        data = {
            "grantType": "refresh_token", "clientId": self.client_id,
            "clientSecret": self.client_secret, "refreshToken": refresh_token
        }
        try:
            res = requests.post(self.token_url, data=data)
            if res.status_code == 200:
                body = res.json()
                token_data = body["content"] if body.get("code") == 200 and "content" in body else body
                if "accessToken" not in token_data: return None

                token_data["expiresAt"] = time.time() + int(token_data.get("expiresIn", 3600)) - 60
                if "refreshToken" not in token_data: token_data["refreshToken"] = refresh_token
                self.save_tokens(token_data)
                return token_data
            return None
        except Exception as e: return None

    def issue_new_token(self):
        ChzzkAuthHandler.auth_code = None
        server = HTTPServer(('localhost', 8080), ChzzkAuthHandler)
        state = "security_state_string"
        auth_url = f"{self.auth_base_url}?clientId={self.client_id}&redirectUri={self.redirect_uri}&state={state}"
        
        print(f"\n========== [치지직 API 인증 필요] ==========\n브라우저가 열립니다. 로그인해주세요:\n{auth_url}\n============================================\n")
        webbrowser.open(auth_url)
        while ChzzkAuthHandler.auth_code is None: server.handle_request()
        code = ChzzkAuthHandler.auth_code
        server.server_close()
        
        data = {
            "grantType": "authorization_code", "clientId": self.client_id,
            "clientSecret": self.client_secret, "code": code, "state": state
        }
        res = requests.post(self.token_url, data=data)
        if res.status_code == 200:
            body = res.json()
            token_data = body["content"] if body.get("code") == 200 and "content" in body else body
            if "accessToken" in token_data:
                token_data["expiresAt"] = time.time() + int(token_data.get("expiresIn", 3600)) - 60
                self.save_tokens(token_data)
                return token_data["accessToken"]
        raise Exception(f"신규 토큰 발급 실패: {res.text}")

class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "치지직"
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.signals = signals
        self.running = True
        self.auth_manager = ChzzkAuthManager()
        self.access_token = None
        self.chat_channel_id = None

    def stop(self): self.running = False

    async def _async_get(self, url, headers=None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(requests.get, url, headers=headers, timeout=5))

    async def _async_post(self, url, json_data=None, headers=None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(requests.post, url, json=json_data, headers=headers, timeout=5))

    def check_live_status_sync(self):
        if not self.channel_id: return False, "Channel ID 누락"
        try:
            token = self.auth_manager.get_valid_access_token(allow_interaction=True)
            headers = {"Authorization": f"Bearer {token}"}
            status_url = f"https://openapi.chzzk.naver.com/open/v1/channels/{self.channel_id}/live-status"
            res = requests.get(status_url, headers=headers, timeout=5)
            
            if res.status_code == 401:
                token = self.auth_manager.get_valid_access_token(force_refresh=True, allow_interaction=True)
                headers = {"Authorization": f"Bearer {token}"}
                res = requests.get(status_url, headers=headers, timeout=5)

            if res.status_code == 403: return False, "권한 없음(403). 계정 불일치 확인 요망."
            elif res.status_code != 200: return False, f"API 오류 ({res.status_code})"
            
            data = res.json()
            content = data.get('content', {})
            return (True, "방송 중") if content.get('status') == 'OPEN' else (False, f"방송 종료 ({content.get('status')})")
        except Exception as e: return False, str(e)

    async def run(self):
        if not self.channel_id: return
        try:
            self.access_token = self.auth_manager.get_valid_access_token(allow_interaction=True)
        except Exception as e:
            self.signals.gui_log_message.emit(f"[치지직] 인증 실패. Client ID/Secret 확인 요망.")
            return
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        while self.running:
            try:
                status_url = f"https://openapi.chzzk.naver.com/open/v1/channels/{self.channel_id}/live-status"
                res_obj = await self._async_get(status_url, headers=headers)
                
                if res_obj.status_code == 401:
                    try:
                        self.access_token = self.auth_manager.get_valid_access_token(force_refresh=True, allow_interaction=False)
                        headers = {"Authorization": f"Bearer {self.access_token}"}
                    except Exception as e:
                        self.signals.stream_offline.emit(self.platform_name)
                        await asyncio.sleep(10)
                    continue
                elif res_obj.status_code == 403:
                    self.signals.gui_log_message.emit("[치지직] 권한 오류(403). 계정-채널ID 불일치.")
                    self.signals.stream_offline.emit(self.platform_name)
                    await asyncio.sleep(10)
                    continue

                res = res_obj.json()
                content = res.get('content', {})
                if content.get('status') != 'OPEN':
                    self.signals.stream_offline.emit(self.platform_name)
                    for _ in range(10): 
                        if not self.running: break
                        await asyncio.sleep(1)
                    continue

                self.chat_channel_id = content['chatChannelId']
                token_url = f"https://openapi.chzzk.naver.com/open/v1/chats/access-token?channelId={self.chat_channel_id}"
                token_res_obj = await self._async_get(token_url, headers=headers)
                token_res = token_res_obj.json()
                ws_access_token = token_res.get('content', token_res).get('accessToken')
                
                ws_url = "wss://kr-ss1.chat.naver.com/chat"
                TIMEOUT_SECONDS = float(os.getenv("WS_TIMEOUT", 600.0))

                async with websockets.connect(ws_url, ping_interval=None) as websocket:
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
                                        content_msg = msg[1:].strip()
                                        if content_msg: self.signals.word_detected.emit(self.platform_name, nickname, content_msg.split()[0])
                            elif cmd == 0: await websocket.send(json.dumps({"ver": "2", "cmd": 10000}))
                        except asyncio.TimeoutError: break 
                        except Exception: break 
            except Exception as e:
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

    def stop(self): self.running = False

    def check_live_status_sync(self):
        if not pytchat: return False, "모듈 미설치"
        if not self.video_id: return False, "Video ID 누락"
        try:
            chat = pytchat.create(video_id=self.video_id, interruptable=False)
            if chat.is_alive():
                chat.terminate()
                return True, "방송 중"
            else: return False, "방송 종료/대기"
        except Exception as e: return False, str(e)

    async def run(self):
        if not pytchat or not self.video_id: return
        while self.running:
            try:
                chat = pytchat.create(video_id=self.video_id, interruptable=False)
                if not chat.is_alive():
                    self.signals.stream_offline.emit(self.platform_name)
                    for _ in range(10):
                        if not self.running: break
                        await asyncio.sleep(1)
                    continue

                self.signals.stream_connected.emit(self.platform_name)
                while self.running:
                    if not chat.is_alive(): break 
                    try:
                        for c in chat.get().sync_items():
                            msg = c.message.strip()
                            if msg.startswith("!"):
                                content = msg[1:].strip()
                                if content: self.signals.word_detected.emit(self.platform_name, c.author.name, content.split()[0])
                        await asyncio.sleep(0.2)
                    except Exception: await asyncio.sleep(1)

                self.signals.stream_offline.emit(self.platform_name)
                try: chat.terminate()
                except: pass
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)
            except Exception as e:
                self.signals.stream_offline.emit(self.platform_name)
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)