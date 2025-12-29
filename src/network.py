# src/network.py
import os
import json
import requests
import websockets
import traceback
from .signals import GameSignals

class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        self.ws_url = "wss://kr-ss1.chat.naver.com/chat"
        self.signals = signals
        self.running = True

    async def run(self):
        if not self.channel_id:
            self.signals.log_request.emit(10, "ChzzkMonitor", "환경변수 CHZZK_CHANNEL_ID 누락", None)
            return

        try:
            status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
            res = requests.get(status_url).json()
            content = res.get('content', {})
            
            live_status = content.get('status')
            if live_status != 'OPEN':
                print(f"[시스템] 현재 방송 상태: {live_status} (연결 중단)")
                self.signals.log_request.emit(5, "ChzzkMonitor", f"방송 상태 아님: {live_status}", None)
                self.signals.stream_offline.emit()
                return

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

                        if data.get('cmd') == 93101:
                            for chat in data.get('bdy', []):
                                msg = chat.get('msg', '').strip()
                                profile = json.loads(chat.get('profile', '{}'))
                                nickname = profile.get('nickname', '익명')

                                if msg.startswith("!"):
                                    content = msg[1:].strip()
                                    if content:
                                        clean_word = content.split()[0]
                                        self.signals.word_detected.emit(nickname, clean_word)

                        elif data.get('cmd') == 0:
                            await websocket.send(json.dumps({"ver": "2", "cmd": 10000}))
                            
                    except Exception as e:
                        print(f"[연결 끊김 또는 에러] {e}")
                        self.signals.log_request.emit(8, "ChzzkMonitor", "웹소켓 에러", traceback.format_exc())
                        break
        except Exception as e:
            print(f"[초기화 오류] {e}")
            self.signals.log_request.emit(9, "ChzzkMonitor", "초기화 실패", traceback.format_exc())