import pymysql
import os
import sys
import math
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=60,
        read_timeout=600,
        write_timeout=600
    )

def synchronize_word_states_fixed():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        print("--- 🔄 끝말잇기 DB 상태 동기화 (에러 수정판) 🔄 ---")
        
        # 1. 전체 데이터 개수 확인
        cursor.execute("SELECT MAX(num) as max_num FROM ko_word")
        max_result = cursor.fetchone()
        
        if not max_result or not max_result['max_num']:
            print("❌ 데이터가 없습니다.")
            return

        max_num = max_result['max_num']
        batch_size = 1000
        total_batches = math.ceil(max_num / batch_size)

        print(f"ℹ️ 전체 데이터: {max_num}개")
        print(f"ℹ️ 총 {total_batches}개 구간을 전수 검사합니다.\n")

        total_revived = 0
        total_killed = 0

        # 2. 배치 루프 (전수 조사)
        for i, start_num in enumerate(range(1, max_num + 1, batch_size), 1):
            end_num = min(start_num + batch_size - 1, max_num)
            
            sys.stdout.write(f"\r🚀 [Batch {i}/{total_batches}] {start_num}~{end_num} 검사 중... ")
            sys.stdout.flush()

            try:
                cursor.execute("SET SQL_SAFE_UPDATES = 0;")

                # =========================================================
                # [1. 부활 로직] 서브쿼리 제거 -> INNER JOIN 사용
                # 설명: 내 끝글자(end_char)로 시작하는 w2가 '존재하면(JOIN 성공)' 부활
                # w2.can_use 상태는 따지지 않음 (구조적 연결 확인)
                # =========================================================
                sql_revive = """
                    UPDATE ko_word w1
                    INNER JOIN ko_word w2 
                        ON w2.start_char = w1.end_char
                    SET w1.can_use = TRUE
                    WHERE w1.num BETWEEN %s AND %s
                    AND w1.can_use = FALSE
                """
                cursor.execute(sql_revive, (start_num, end_num))
                revived_cnt = cursor.rowcount
                total_revived += revived_cnt

                # =========================================================
                # [2. 제거 로직] LEFT JOIN 사용 (기존과 동일, 정상 작동)
                # 설명: 내 끝글자로 시작하는 '살아있는(True)' w2가 없으면 제거
                # =========================================================
                sql_kill = """
                    UPDATE ko_word w1
                    LEFT JOIN ko_word w2 
                        ON w2.start_char = w1.end_char 
                        AND w2.can_use = TRUE
                    SET w1.can_use = FALSE
                    WHERE w1.num BETWEEN %s AND %s
                    AND w1.can_use = TRUE
                    AND w2.num IS NULL
                """
                cursor.execute(sql_kill, (start_num, end_num))
                killed_cnt = cursor.rowcount
                total_killed += killed_cnt

                conn.commit()

                # 로그 상세 출력
                if revived_cnt > 0 or killed_cnt > 0:
                    msg_parts = []
                    if revived_cnt > 0: msg_parts.append(f"🟢{revived_cnt}개 부활")
                    if killed_cnt > 0: msg_parts.append(f"🔴{killed_cnt}개 제거")
                    sys.stdout.write(" -> " + ", ".join(msg_parts))

            except Exception as e:
                conn.rollback()
                print(f"\n❌ [Error] 구간 {start_num}~{end_num} 처리 중 오류: {e}")
                continue

        # 3. 최종 결과
        print(f"\n\n{'='*40}")
        print(f"✅ 모든 검사가 완료되었습니다.")
        print(f"🟢 총 부활 (구조적 구제): {total_revived}개")
        print(f"🔴 총 제거 (연결 끊김): {total_killed}개")
        
        cursor.execute("SELECT count(*) as cnt FROM ko_word WHERE can_use = TRUE")
        final_cnt = cursor.fetchone()['cnt']
        print(f"🔥 최종 생존 단어 수: {final_cnt}개")

    except Exception as e:
        print(f"\n❌ 시스템 오류 발생: {e}")
    finally:
        if conn:
            cursor.execute("SET SQL_SAFE_UPDATES = 1;")
            cursor.close()
            conn.close()

if __name__ == "__main__":
    synchronize_word_states_fixed()