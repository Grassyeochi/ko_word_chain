# src/network.py
import os
import asyncio
import threading
import requests
from .signals import GameSignals

try:
    import pytchat
except ImportError:
    pytchat = None
    print("[경고] pytchat 라이브러리가 설치되지 않았습니다. 유튜브 연동이 불가능합니다.")

try:
    import chzzkpy
    from chzzkpy import Client, UserPermission
except ImportError:
    chzzkpy = None
    print("[경고] chzzkpy 라이브러리가 설치되지 않았습니다. 치지직 연동이 불가능합니다.")

class ChzzkMonitor:
    def __init__(self, signals: GameSignals):
        self.platform_name = "치지직"
        self.signals = signals
        self.running = True
        
        self.client_id = os.getenv("CHZZK_CLIENT_ID")
        self.client_secret = os.getenv("CHZZK_CLIENT_SECRET")
        self.channel_id = os.getenv("CHZZK_CHANNEL_ID")
        
        self.client = None
        self.user_client = None

    def stop(self):
        self.running = False
        if self.user_client:
            try:
                asyncio.create_task(self.user_client.close())
            except: pass

    def check_live_status_sync(self):
        """사전 준비 단계에서 호출되어 동기적으로 인증 및 상태를 검사합니다."""
        if not chzzkpy: return False, "chzzkpy 모듈 미설치"
        if not self.client_id or not self.client_secret: return False, "Client ID/Secret 누락"

        # 프로그램 사전 준비 단계에서 미리 인증을 수행하는 비동기 함수
        async def _do_auth():
            temp_client = chzzkpy.Client(self.client_id, self.client_secret)
            try:
                # 브라우저를 열어 인증 수행 및 토큰 캐싱
                user_client = await temp_client.login()
                
                # 상태 확인은 폴링 API 우회 사용 (가장 빠르고 정확함)
                status_url = f"https://api.chzzk.naver.com/polling/v2/channels/{self.channel_id}/live-status"
                res = requests.get(status_url, timeout=5)
                is_live = False
                status_msg = "인증 성공 (상태 확인 불가)"
                if res.status_code == 200:
                    data = res.json()
                    is_live = data.get('content', {}).get('status') == 'OPEN'
                    status_msg = "방송 중" if is_live else "방송 종료"
                
                try: await temp_client.close()
                except: pass
                
                return is_live, status_msg
            except Exception as e:
                try: await temp_client.close()
                except: pass
                return False, f"인증 실패: {e}"

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_do_auth())
            loop.close()
            return result
        except Exception as e:
            return False, f"실행 오류: {e}"

    async def run(self):
        """게임이 시작된 후 백그라운드에서 실시간 채팅을 수신합니다."""
        if not chzzkpy or not self.client_id or not self.client_secret:
            return

        self.client = chzzkpy.Client(self.client_id, self.client_secret)

        @self.client.event
        async def on_chat(message):
            if not self.running: return
            msg = message.content.strip()
            nickname = message.profile.nickname if message.profile else "익명"
            if "클린봇" in msg: return
            
            if msg.startswith("!"):
                content_msg = msg[1:].strip()
                if content_msg:
                    self.signals.word_detected.emit(self.platform_name, nickname, content_msg.split()[0])

        @self.client.event
        async def on_disconnect():
            self.signals.stream_offline.emit(self.platform_name)

        while self.running:
            try:
                self.user_client = await self.client.login()
                
                # 소켓에 연결하여 채팅 이벤트만 특정하여 구독
                connect_task = asyncio.create_task(self.user_client.connect(UserPermission(chat=True)))
                
                # [수정] 이벤트 리스너 미작동 방어: 연결 스케줄링 후 명시적으로 GUI에 신호 발송
                await asyncio.sleep(2)
                if not connect_task.done() and self.running:
                    self.signals.stream_connected.emit(self.platform_name)
                    self.signals.gui_log_message.emit(f"[{self.platform_name}] 공식 API 채팅 소켓 및 리스너 연결 성공!")
                
                while self.running:
                    await asyncio.sleep(1)
                    if connect_task.done():
                        if connect_task.exception():
                            raise connect_task.exception()
                        break
                        
                if not self.running:
                    try: await self.user_client.close()
                    except: pass
                    connect_task.cancel()
                    break
                    
            except Exception as e:
                self.signals.stream_offline.emit(self.platform_name)
                self.signals.gui_log_message.emit(f"[{self.platform_name}] 연결 오류: {e}. 10초 후 재시도...")
                for _ in range(10):
                    if not self.running: break
                    await asyncio.sleep(1)
                continue


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