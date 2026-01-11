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
    
    with loop:
        loop.run_forever()