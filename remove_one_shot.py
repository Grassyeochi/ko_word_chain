import pymysql
import os
import sys
import math
import time
from dotenv import load_dotenv

load_dotenv()

# 설정: 배치 사이즈를 키워 DB 통신 횟수를 줄입니다. (서버 사양에 따라 조절 가능)
BATCH_SIZE = 50000 

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
        write_timeout=600,
        autocommit=False  # 트랜잭션 수동 제어
    )

def run_synchronization_pass(conn, cursor, pass_num):
    """
    DB 전체를 1회 순회하며 상태를 동기화합니다.
    변경(부활/제거)된 총 행(row) 수를 반환합니다.
    """
    cursor.execute("SELECT MAX(num) as max_num FROM ko_word")
    max_result = cursor.fetchone()
    if not max_result or not max_result['max_num']:
        return 0

    max_num = max_result['max_num']
    total_batches = math.ceil(max_num / BATCH_SIZE)
    
    pass_revived = 0
    pass_killed = 0
    
    print(f"\n🔄 [Pass {pass_num}] 전체 {max_num}개 데이터 스캔 시작 (Batch Size: {BATCH_SIZE})")

    # SQL 문 미리 정의 (가독성 및 재사용)
    # [부활] 내 끝글자로 시작하는 '살아있는' 단어가 있으면 나도 부활
    sql_revive = """
        UPDATE ko_word w1
        INNER JOIN ko_word w2 
            ON w2.start_char = w1.end_char AND w2.can_use = TRUE
        SET w1.can_use = TRUE
        WHERE w1.num BETWEEN %s AND %s
        AND w1.can_use = FALSE
    """

    # [제거] 내 끝글자로 시작하는 '살아있는' 단어가 하나도 없으면 제거
    sql_kill = """
        UPDATE ko_word w1
        LEFT JOIN ko_word w2 
            ON w2.start_char = w1.end_char AND w2.can_use = TRUE
        SET w1.can_use = FALSE
        WHERE w1.num BETWEEN %s AND %s
        AND w1.can_use = TRUE
        AND w2.num IS NULL
    """

    start_time = time.time()

    for i, start_num in enumerate(range(1, max_num + 1, BATCH_SIZE), 1):
        end_num = min(start_num + BATCH_SIZE - 1, max_num)
        
        try:
            # 1. 부활 처리
            cursor.execute(sql_revive, (start_num, end_num))
            r_cnt = cursor.rowcount
            pass_revived += r_cnt

            # 2. 제거 처리
            cursor.execute(sql_kill, (start_num, end_num))
            k_cnt = cursor.rowcount
            pass_killed += k_cnt

            conn.commit() # 배치 단위 커밋

            # 진행률 표시 (너무 잦은 출력 방지)
            if i % 5 == 0 or i == total_batches or (r_cnt + k_cnt) > 0:
                progress = (i / total_batches) * 100
                sys.stdout.write(f"\r   📍 진행률: {progress:.1f}% ({i}/{total_batches}) | +{pass_revived} / -{pass_killed}")
                sys.stdout.flush()

        except Exception as e:
            conn.rollback()
            print(f"\n❌ Batch Error ({start_num}~{end_num}): {e}")
            return -1 # 에러 발생 시 중단 신호

    elapsed = time.time() - start_time
    print(f"\n   ⏱️ [Pass {pass_num}] 완료: {elapsed:.2f}초 소요 | 🟢부활: {pass_revived} | 🔴제거: {pass_killed}")
    
    return pass_revived + pass_killed

def optimize_word_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        print("--- 🚀 끝말잇기 DB 상태 완전 동기화 (Auto-Convergence) ---")
        
        pass_count = 1
        while True:
            # 한 바퀴(Pass) 실행
            total_changed = run_synchronization_pass(conn, cursor, pass_count)
            
            if total_changed == -1: # 에러 발생
                break
            
            if total_changed == 0:
                print(f"\n✅ [수렴 완료] 더 이상 상태가 변하는 단어가 없습니다.")
                break
            
            print(f"   👉 상태 변경이 감지되었습니다. 연쇄 작용 반영을 위해 재검사합니다...")
            pass_count += 1
            
        # 최종 결과 확인
        print(f"\n{'='*40}")
        cursor.execute("SELECT count(*) as cnt FROM ko_word WHERE can_use = TRUE")
        final_cnt = cursor.fetchone()['cnt']
        print(f"🔥 최종 생존 단어 수: {final_cnt}개")

    except Exception as e:
        print(f"\n❌ 치명적 오류: {e}")
    finally:
        if conn:
            cursor.execute("SET SQL_SAFE_UPDATES = 1;")
            cursor.close()
            conn.close()

if __name__ == "__main__":
    optimize_word_database()