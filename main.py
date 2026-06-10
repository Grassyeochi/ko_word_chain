# main.py
import sys
import asyncio
from dotenv import load_dotenv
from qasync import QEventLoop
from PyQt6.QtWidgets import QApplication

from src.gui import ChzzkGameGUI

load_dotenv()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    window = ChzzkGameGUI()
    window.show()
    window.raise_()
    window.activateWindow()
    
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        print("[시스템] 사용자에 의해 강제 종료되었습니다.")
    finally:
        if not loop.is_closed():
            loop.close()