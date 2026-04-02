import pymysql
import os
import sys
import math
import time
from dotenv import load_dotenv

load_dotenv()

# 설정: 배치 사이즈
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
    cursor.execute("SELECT MAX(num) as max_num FROM ko_word")
    max_result = cursor.fetchone()
    if not max_result or not max_result['max_num']:
        return 0

    max_num = max_result['max_num']
    total_batches = math.ceil(max_num / BATCH_SIZE)
    
    pass_revived = 0
    pass_killed = 0
    
    print(f"\n🔄 [Pass {pass_num}] 전체 {max_num}개 데이터 스캔 시작 (Batch Size: {BATCH_SIZE})")

    # [수정됨] 부활 로직: 이어지는 단어가 살아있고, 지정된 source 중 하나여야 함
    sql_revive = """
        UPDATE ko_word w1
        INNER JOIN ko_word w2 
            ON w2.start_char = w1.end_char 
            AND w2.can_use = TRUE
            AND w2.source IN ('URI', 'Standard', 'naver_wiki', 'admin', 'subway', 'wikipedia')
        SET w1.can_use = TRUE
        WHERE w1.num BETWEEN %s AND %s
        AND w1.can_use = FALSE
    """

    # [수정됨] 제거 로직: 위 조건을 만족하는 이어지는 단어가 하나도 없으면 제거
    sql_kill = """
        UPDATE ko_word w1
        LEFT JOIN ko_word w2 
            ON w2.start_char = w1.end_char 
            AND w2.can_use = TRUE
            AND w2.source IN ('URI', 'Standard', 'naver_wiki', 'admin', 'subway', 'wikipedia')
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

            conn.commit()

            if i % 5 == 0 or i == total_batches or (r_cnt + k_cnt) > 0:
                progress = (i / total_batches) * 100
                sys.stdout.write(f"\r   📍 진행률: {progress:.1f}% ({i}/{total_batches}) | +{pass_revived} / -{pass_killed}")
                sys.stdout.flush()

        except Exception as e:
            conn.rollback()
            print(f"\n❌ Batch Error ({start_num}~{end_num}): {e}")
            return -1

    elapsed = time.time() - start_time
    print(f"\n   ⏱️ [Pass {pass_num}] 완료: {elapsed:.2f}초 소요 | 🟢부활: {pass_revived} | 🔴제거: {pass_killed}")
    
    return pass_revived + pass_killed

def optimize_word_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SET SQL_SAFE_UPDATES = 0;")
        
        print("--- 🚀 끝말잇기 DB 상태 완전 동기화 (Source 필터링 적용) ---")
        
        pass_count = 1
        while True:
            total_changed = run_synchronization_pass(conn, cursor, pass_count)
            
            if total_changed == -1:
                break
            
            if total_changed == 0:
                print(f"\n✅ [수렴 완료] 더 이상 상태가 변하는 단어가 없습니다.")
                break
            
            print(f"   👉 상태 변경이 감지되었습니다. 연쇄 작용 반영을 위해 재검사합니다...")
            pass_count += 1
            
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