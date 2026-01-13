# src/commands.py
import time
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

        if cmd == "chcw": return self._handle_chcw(full_command)
        elif cmd == "random": return self._handle_random()
        elif cmd == "rwt": return self._handle_rwt()
        elif cmd == "restart": return self._handle_restart()
        elif cmd == "ac": return self._handle_ac(args)
        elif cmd == "log": return self._handle_log(args)
        else: return f"[오류] 알 수 없는 명령어: {cmd}"

    def _handle_chcw(self, full_command):
        try:
            target_word = full_command[len("chcw"):].strip().replace('"', '').replace("'", "")
        except:
            return "[오류] 파싱 실패"
            
        if not target_word: return "[오류] 단어를 입력하세요."

        admin_nick = "console-admin"
        if self.db.admin_force_use_word(target_word, admin_nick):
            self.gui.current_word_text = target_word
            self.gui.set_responsive_text(target_word)
            self.gui.last_change_time = time.time()
            self.gui.email_sent_flag = False
            self.gui.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {admin_nick}")
            self.gui.update_hint(target_word[-1])
            msg = f"[관리자] 단어가 '{target_word}'(으)로 변경됨."
            self.gui.log_message(msg)
            return f"[성공] {msg}"
        else:
            return f"[실패] 단어 '{target_word}' DB 없음."

    def _handle_random(self):
        admin_nick = "console-random"
        new_word = self.db.get_and_use_random_available_word(admin_nick)
        if not new_word: return "[실패] 남은 단어 없음."
        
        self.gui.current_word_text = new_word
        self.gui.set_responsive_text(new_word)
        self.gui.last_change_time = time.time()
        self.gui.email_sent_flag = False
        self.gui.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {admin_nick}")
        self.gui.update_hint(new_word[-1])
        msg = f"[관리자] 무작위 단어 '{new_word}'(으)로 변경됨."
        self.gui.log_message(msg)
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

    def _handle_ac(self, args):
        if not args: return "[오류] ac start/stop"
        action = args[0].lower()
        if action == "stop":
            self.gui.answer_check_enabled = False
            self.gui.lbl_pause_status.show()
            self.gui.log_message("[관리자] 정답 체크 중지.")
            return "[알림] 중지됨"
        elif action == "start":
            self.gui.answer_check_enabled = True
            self.gui.lbl_pause_status.hide()
            self.gui.log_message("[관리자] 정답 체크 시작.")
            return "[알림] 시작됨"
        return "[오류] ac start 또는 ac stop"

    def _handle_log(self, args):
        if not args: return "[오류] log save/all/game"
        sub = args[0].lower()
        if sub == "save":
            suc, ts = self.db.export_all_data_to_csv()
            return f"[성공] 백업 완료: {ts}" if suc else "[실패] 백업 오류"
        elif sub in ["all", "game"]:
            try:
                lim = int(args[1]) if len(args)>1 else 10
                logs = self.db.get_recent_logs(sub, lim)
                return "\n".join([str(r) for r in logs])
            except: return "[오류] 조회 실패"
        return "[오류] 알 수 없는 옵션"