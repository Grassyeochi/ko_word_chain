# src/commands.py
import time
from .utils import apply_dueum_rule

class CommandManager:
    def __init__(self, main_window):
        """
        :param main_window: ChzzkGameGUI 인스턴스 (GUI 제어용)
        """
        self.gui = main_window
        self.db = main_window.db_manager

    def execute(self, full_command: str) -> str:
        """
        콘솔 입력을 받아 명령어를 파싱하고 실행한 뒤, 결과 메시지를 반환한다.
        """
        parts = full_command.strip().split()
        if not parts:
            return ""

        cmd = parts[0].lower()
        args = parts[1:]

        # 명령어 라우팅
        if cmd == "chcw":
            return self._handle_chcw(args, full_command)
        elif cmd == "rwt":
            return self._handle_rwt()
        elif cmd == "restart":
            return self._handle_restart()
        elif cmd == "ac":
            return self._handle_ac(args)
        elif cmd == "log":
            return self._handle_log(args)
        else:
            return f"[오류] 알 수 없는 명령어입니다: {cmd}"

    # --- 개별 명령어 처리 로직 ---

    def _handle_chcw(self, args, full_command):
        # 파싱: chcw "단어" 형태 처리
        if len(args) < 1:
             return "[오류] 사용법: chcw \"단어\""
        
        # 따옴표 제거 로직
        target_word = full_command[len("chcw"):].strip().replace('"', '').replace("'", "")
        
        if not target_word:
            return "[오류] 단어를 입력해주세요."

        admin_nick = "console-admin"
        
        # 1. DB 강제 업데이트
        if self.db.admin_force_use_word(target_word, admin_nick):
            # 2. GUI 상태 업데이트
            self.gui.current_word_text = target_word
            self.gui.set_responsive_text(target_word)
            self.gui.last_change_time = time.time()
            self.gui.email_sent_flag = False
            
            self.gui.lbl_last_winner.setText(f"현재 단어를 맞춘 사람: {admin_nick}")
            self.gui.update_hint(target_word[-1])
            
            msg = f"[관리자] 단어가 '{target_word}'(으)로 강제 변경되었습니다."
            self.gui.log_message(msg)

            # 3. 종료 조건 체크
            next_starts = apply_dueum_rule(target_word[-1])
            any_left = False
            for char in next_starts:
                if not self.db.check_remaining_words(char):
                    any_left = True
                    break
            
            if not any_left:
                self.gui.process_game_over(target_word, admin_nick)
                return f"[성공] {msg} (이후 게임 종료됨)"
            
            return f"[성공] {msg}"
        else:
            return f"[실패] 단어 '{target_word}'를 DB에서 찾을 수 없습니다."

    def _handle_rwt(self):
        self.gui.last_change_time = time.time()
        self.gui.update_runtime()
        self.gui.email_sent_flag = False
        
        msg = "[관리자] 단어 경과 시간이 초기화되었습니다."
        self.gui.log_message(msg)
        return f"[성공] {msg}"

    def _handle_restart(self):
        msg = "[관리자] 게임 강제 재시작을 요청했습니다."
        self.gui.log_message(msg)
        
        # 게임 종료 프로세스 진입
        self.gui.process_game_over(self.gui.current_word_text, "console-admin")
        return f"[성공] {msg}"

    def _handle_ac(self, args):
        if len(args) < 1:
            return "[오류] 사용법: ac start 또는 ac stop"
        
        action = args[0].lower()
        if action == "stop":
            self.gui.answer_check_enabled = False
            self.gui.lbl_pause_status.show()
            
            msg = "[관리자] 정답 체크가 중지되었습니다."
            self.gui.log_message(msg)
            return f"[알림] {msg}"
            
        elif action == "start":
            self.gui.answer_check_enabled = True
            self.gui.lbl_pause_status.hide()
            
            msg = "[관리자] 정답 체크가 다시 시작되었습니다."
            self.gui.log_message(msg)
            return f"[알림] {msg}"
        else:
            return "[오류] ac 명령어 뒤에는 start 또는 stop만 가능합니다."

    def _handle_log(self, args):
        if len(args) < 1:
            return "[오류] 사용법: log all (숫자) / log game (숫자) / log save"
        
        sub_cmd = args[0].lower()
        
        if sub_cmd == "save":
            success, timestamp = self.db.export_all_data_to_csv()
            if success:
                msg = f"[성공] 로그 저장 완료 (backups/{timestamp})"
                self.gui.log_message(msg)
                return msg
            else:
                return "[실패] 로그 저장 중 오류가 발생했습니다."
        
        elif sub_cmd in ["all", "game"]:
            try:
                limit = int(args[1]) if len(args) > 1 else 10
                logs = self.db.get_recent_logs(sub_cmd, limit)
                
                if not logs:
                    return "[알림] 로그가 없거나 조회에 실패했습니다."
                
                # 결과 문자열 포맷팅
                output = [f"--- [Log View: {sub_cmd}, Limit: {limit}] ---"]
                for row in logs:
                    output.append(str(row))
                output.append("---------------------------------------")
                
                return "\n".join(output)
            except ValueError:
                return "[오류] 숫자를 입력해주세요."
        else:
            return "[오류] 알 수 없는 log 옵션입니다."