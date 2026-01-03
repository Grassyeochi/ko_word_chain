# main.py
import sys
import asyncio
from dotenv import load_dotenv
from qasync import QEventLoop
from PyQt6.QtWidgets import QApplication

# gui 모듈만 가져오면 나머지는 내부적으로 조립됨
from src.gui import ChzzkGameGUI

# .env 파일 로드 (전역 설정)
load_dotenv()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # 게임 윈도우 생성
    window = ChzzkGameGUI()
    window.show()
    
    # [수정] 프로그램 시작 시 맨 앞으로 가져오기 (하이라이트)
    window.raise_()
    window.activateWindow()
    
    # 이벤트 루프 실행
    with loop:
        loop.run_forever()