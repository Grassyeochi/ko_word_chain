# src/network.py
import os
import json
import requests
import websockets
import traceback
import asyncio
from functools import partial
from .signals import GameSignals

try:
    import pytchat
except ImportError:
    pytchat = None
    print("[경고] pytchat 라이브러리가 설치되지 않았습니다. 유튜브 연동이 불가능합니다.")

class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "치지직"
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.ws_url = "wss://kr-ss1.chat.naver.com/chat"
        self.signals = signals
        self.running = True

    async def _async_get(self, url):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(requests.get, url, timeout=5))

    def check_live_status_sync(self):
        if not self.channel_id:
            return False, "Channel ID 누락"
        try:
            status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
            res = requests.get(status_url, timeout=5)
            if res.status_code != 200:
                return False, f"API 오류 ({res.status_code})"
            data = res.json()
            content = data.get('content', {})
            live_status = content.get('status')
            return (True, "방송 중") if live_status == 'OPEN' else (False, f"방송 종료됨 ({live_status})")
        except Exception as e:
            return False, str(e)

    async def run(self):
        if not self.channel_id:
            self.signals.log_request.emit(10, "Chzzk", "환경변수 누락", None)
            return

        while self.running:
            try:
                status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
                res_obj = await self._async_get(status_url)
                res = res_obj.json()
                content = res.get('content', {})
                live_status = content.get('status')
                
                if live_status != 'OPEN':
                    # [요구사항 3] GUI 로그에 재접속 시도 알림
                    self.signals.gui_log_message.emit(f"[{self.platform_name}] 방송 종료 감지. 10초 후 재접속 시도...")
                    self.signals.stream_offline.emit(self.platform_name)
                    await asyncio.sleep(10)
                    continue

                chat_channel_id = content['chatChannelId']
                token_url = f"https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chat_channel_id}&chatType=STREAMING"
                token_res_obj = await self._async_get(token_url)
                token_res = token_res_obj.json()
                access_token = token_res['content']['accessToken']
                
                TIMEOUT_SECONDS = float(os.getenv("WS_TIMEOUT", 600.0))

                async with websockets.connect(self.ws_url, ping_interval=None) as websocket:
                    self.signals.log_request.emit(1, "Chzzk", "채팅 서버 연결 성공", None)
                    self.signals.stream_connected.emit(self.platform_name)
                    
                    await websocket.send(json.dumps({
                        "ver": "2", "cmd": 100, "svcid": "game", "cid": chat_channel_id, "tid": 1,
                        "bdy": {"uid": None, "devType": 2001, "accTkn": access_token, "auth": "READ"}
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
                            self.signals.gui_log_message.emit(f"[{self.platform_name}] 응답 없음(Zombie). 재접속 시도...")
                            break 
                        except Exception:
                            break 
            
            except Exception as e:
                self.signals.log_request.emit(9, "Chzzk", "접속 오류", str(e))
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 접속 오류. 10초 후 재시도...")
                self.signals.stream_offline.emit(self.platform_name)
                await asyncio.sleep(10)
                continue
            
            if self.running:
                await asyncio.sleep(3)


class YouTubeMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "유튜브"
        self.video_id = os.getenv("YOUTUBE_VIDEO_ID")
        self.signals = signals
        self.running = True

    # [요구사항 1] 시작 시 방송 상태 확인을 위한 동기 함수 추가
    def check_live_status_sync(self):
        if not pytchat:
            return False, "모듈 미설치"
        if not self.video_id:
            return False, "Video ID 누락"
        
        try:
            # pytchat을 생성하여 생존 여부(방송 중 여부) 확인
            chat = pytchat.create(video_id=self.video_id)
            if chat.is_alive():
                chat.terminate()
                return True, "방송 중"
            else:
                return False, "방송 종료/대기/오류"
        except Exception as e:
            return False, f"오류: {str(e)}"

    async def run(self):
        if not pytchat:
            self.signals.gui_log_message.emit("[오류] pytchat 모듈 미설치로 유튜브 기능 비활성화")
            return

        if not self.video_id:
            self.signals.log_request.emit(10, "YouTube", "환경변수 YOUTUBE_VIDEO_ID 누락", None)
            return

        while self.running:
            try:
                chat = pytchat.create(video_id=self.video_id)
                
                # is_alive() 체크로 초기 연결 확인
                if not chat.is_alive():
                    self.signals.gui_log_message.emit(f"[{self.platform_name}] 방송을 찾을 수 없음. 10초 후 재시도...")
                    self.signals.stream_offline.emit(self.platform_name)
                    await asyncio.sleep(10)
                    continue

                self.signals.stream_connected.emit(self.platform_name)
                self.signals.log_request.emit(1, "YouTube", f"채팅 리스너 시작 ({self.video_id})", None)

                while self.running and chat.is_alive():
                    try:
                        data = chat.get()
                        for c in data.sync_items():
                            msg = c.message.strip()
                            nickname = c.author.name
                            if msg.startswith("!"):
                                content = msg[1:].strip()
                                if content:
                                    self.signals.word_detected.emit(self.platform_name, nickname, content.split()[0])
                        await asyncio.sleep(0.1)
                    except Exception:
                        break

                # 루프 탈출 = 연결 끊김
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 연결 끊김. 10초 후 재접속...")
                self.signals.stream_offline.emit(self.platform_name)
                await asyncio.sleep(10)

            except Exception as e:
                self.signals.log_request.emit(9, "YouTube", "접속 오류", str(e))
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 오류 발생. 10초 후 재시도...")
                self.signals.stream_offline.emit(self.platform_name)
                await asyncio.sleep(10)