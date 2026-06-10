# src/commands.py
import time
import re
from .utils import apply_dueum_rule

class CommandManager:
    def __init__(self, main_window):
        self.gui = main_window
        self.db = main_window.db_manager

    def execute(self, full_command: str) -> str:
        parts = full_command.strip().split()
        if not parts: return ""
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "chcw": return self._handle_chcw(args)
        elif cmd == "random": return self._handle_random()
        elif cmd == "rwt": return self._handle_rwt()
        elif cmd == "restart": return self._handle_restart()
        elif cmd == "ac": return self._handle_ac(args)
        elif cmd == "log": return self._handle_log(args)
        elif cmd == "game": return self._handle_game_control(args)
        elif cmd == "network": return self._handle_network_control(args)
        elif cmd == "ban": return self._handle_ban(args)
        else: return f"[오류] 알 수 없는 명령어: {cmd}"

    def _handle_chcw(self, args):
        if not args: return "[오류] 사용법: chcw {단어}"
        new_word = args[0]
        
        if not re.fullmatch(r'[가-힣]+', new_word):
            msg = "[오류] 입력 불가: 순수 한글로만 이루어진 단어를 입력해야 합니다."
            self.gui.log_message(msg)
            return msg

        success = self.db.admin_force_use_word(new_word, "console-admin")
        if not success:
            msg = f"[오류] '{new_word}' 단어를 ko_word 테이블에서 찾을 수 없거나 이미 점유되었습니다."
            self.gui.log_message(msg)
            return msg

        self.gui.current_word_text = new_word
        self.gui.set_responsive_text(new_word)
        self.gui.update_hint(new_word[-1])
        self.gui.display_word_image(new_word)
        msg = f"현재 단어가 '{new_word}'(으)로 강제 변경되었습니다."
        self.gui.log_message(f"[성공] {msg}")
        return f"[성공] {msg}"

    def _handle_rwt(self):
        self.gui.last_change_time = time.time()
        self.gui.update_runtime()
        self.gui.email_sent_flag = False
        msg = "[관리자] 시간 초기화됨."
        self.gui.log_message(msg)
        return f"[성공] {msg}"

    def _handle_restart(self):
        msg = "[관리자] 게임 강제 재시작."
        self.gui.log_message(msg)
        self.gui.process_game_over(self.gui.current_word_text, "console-admin")
        return f"[성공] {msg}"

    def _handle_game_control(self, args):
        if not args: return "[오류] 사용법: game start 또는 game stop"
        action = args[0].lower()
        if action == "stop":
            if getattr(self.gui, 'is_paused', False):
                return "[오류] 이미 게임이 일시정지 상태입니다."
            self.gui.is_paused = True
            self.gui.lbl_pause_status.show()
            self.gui.log_message("[성공] 게임이 일시정지 되었습니다.")
            return "[성공] 게임 일시정지됨."
        elif action == "start":
            if not getattr(self.gui, 'is_paused', False):
                return "[오류] 게임이 일시정지 상태가 아닙니다."
            self.gui.is_paused = False
            self.gui.lbl_pause_status.hide()
            self.gui.log_message("[성공] 게임이 재개되었습니다.")
            return "[성공] 게임 재개됨."
        return "[오류] 사용법: game start 또는 game stop"

    def _handle_network_control(self, args):
        if not args: return "[오류] 사용법: network start 또는 network stop"
        action = args[0].lower()
        if action == "stop":
            self.gui.chzzk_monitor.stop()
            self.gui.youtube_monitor.stop()
            self.gui.log_message("[성공] 수동 제어로 인해 네트워크 통신이 정지되었습니다.")
            return "[성공] 네트워크 모니터 정지됨."
        elif action == "start":
            self.gui.chzzk_monitor.running = True
            self.gui.youtube_monitor.running = True
            self.gui.start_monitor_service()
            self.gui.log_message("[성공] 수동 제어로 인해 네트워크 통신이 재시작되었습니다.")
            return "[성공] 네트워크 모니터 재시작됨."
        return "[오류] 사용법: network start 또는 network stop"

    def _handle_ban(self, args):
        if not args or len(args[0]) != 1: return "[오류] 사용법: ban {한글자}"
        target_char = args[0]
        result_msg = self.db.toggle_banned_char(target_char)
        self.gui._update_banned_chars_gui()
        self.gui.log_message(result_msg)
        return result_msg

    def _handle_random(self):
        word = self.db.get_random_start_word()
        if word and word != "시작":
            self._handle_chcw([word])
            return f"[성공] 무작위 단어({word})로 변경되었습니다."
        return "[오류] DB에서 무작위 단어를 추출하지 못했습니다."

    def _handle_ac(self, args):
        return self._handle_game_control(args)

    def _handle_log(self, args):
        if not args: return "[오류] 사용법: log save / log all / log game"
        return "[알림] 콘솔에서는 시스템 로그 출력을 지원하지 않습니다. DB를 확인하십시오."