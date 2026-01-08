# src/network.py
import os
import json
import requests
import websockets
import traceback
import asyncio
from .signals import GameSignals

class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.ws_url = "wss://kr-ss1.chat.naver.com/chat"
        self.signals = signals
        self.running = True

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
            
            if live_status == 'OPEN':
                return True, "방송 중 (OPEN)"
            else:
                return False, f"방송 종료됨 ({live_status})"
        except Exception as e:
            return False, str(e)

    async def run(self):
        if not self.channel_id:
            self.signals.log_request.emit(10, "ChzzkMonitor", "환경변수 CHZZK_CHANNEL_ID 누락", None)
            return

        while self.running:
            try:
                status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
                res = requests.get(status_url).json()
                content = res.get('content', {})
                
                live_status = content.get('status')
                if live_status != 'OPEN':
                    print(f"[시스템] 방송 종료됨 (상태: {live_status}). 10초 후 재확인...")
                    self.signals.stream_offline.emit()
                    await asyncio.sleep(10)
                    continue

                chat_channel_id = content['chatChannelId']
                token_url = f"https://comm-api.game.naver.com/nng_main/v1/chats/access-token?channelId={chat_channel_id}&chatType=STREAMING"
                token_res = requests.get(token_url).json()
                access_token = token_res['content']['accessToken']

                async with websockets.connect(self.ws_url) as websocket:
                    print(f"[시스템] 채팅 서버 연결 성공 (Chat ID: {chat_channel_id})")
                    self.signals.log_request.emit(1, "ChzzkMonitor", "채팅 서버 연결 성공", None)
                    
                    await websocket.send(json.dumps({
                        "ver": "2", "cmd": 100, "svcid": "game", "cid": chat_channel_id, "tid": 1,
                        "bdy": {"uid": None, "devType": 2001, "accTkn": access_token, "auth": "READ"}
                    }))

                    while self.running:
                        try:
                            res = await websocket.recv()
                            data = json.loads(res)
                            cmd = data.get('cmd')

                            if cmd == 93101:
                                for chat in data.get('bdy', []):
                                    msg = chat.get('msg', '').strip()
                                    profile = json.loads(chat.get('profile', '{}'))
                                    nickname = profile.get('nickname', '익명')

                                    if "클린봇이 부적절한 표현을 감지했습니다" in msg:
                                        self.signals.log_request.emit(5, "ChzzkMonitor", f"클린봇 감지됨 ({nickname})", None)
                                        continue 

                                    if msg.startswith("!"):
                                        content = msg[1:].strip()
                                        if content:
                                            clean_word = content.split()[0]
                                            self.signals.word_detected.emit(nickname, clean_word)

                            elif cmd == 0:
                                await websocket.send(json.dumps({"ver": "2", "cmd": 10000}))
                                
                        except Exception as e:
                            print(f"[연결 끊김] {e}")
                            self.signals.log_request.emit(8, "ChzzkMonitor", "웹소켓 연결 끊김, 재접속 시도", traceback.format_exc())
                            break 
            
            except Exception as e:
                print(f"[접속 오류] {e}")
                self.signals.log_request.emit(9, "ChzzkMonitor", "접속 시도 중 오류", traceback.format_exc())
            
            if self.running:
                print("[시스템] 3초 후 재연결을 시도합니다...")
                await asyncio.sleep(3)