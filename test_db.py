import pymysql
import os
import random
import re
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def test_simulation():
    """
    [테스트 1] 실전 시뮬레이션
    DB에서 랜덤으로 시작 단어를 뽑아 20턴 동안 끝말잇기가 매끄럽게 되는지 확인
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n========== [TEST 1] 🎮 끝말잇기 실전 시뮬레이션 ==========")
    
    try:
        # 1. 시작 단어 랜덤 추출 (can_use = TRUE 인 것 중에서)
        cursor.execute("SELECT word, end_char FROM ko_word WHERE can_use = TRUE ORDER BY RAND() LIMIT 1")
        current = cursor.fetchone()
        
        if not current:
            print("❌ DB에 사용 가능한 단어가 없습니다.")
            return

        chain = [current['word']]
        print(f"🏁 시작 단어: {current['word']}")

        for i in range(1, 21): # 20턴 진행
            prev_end = current['end_char']
            
            # 다음 단어 찾기 (이미 쓴 단어 제외 로직은 시뮬레이션이라 생략하고 연결성만 봄)
            sql = """
                SELECT word, end_char 
                FROM ko_word 
                WHERE start_char = %s 
                AND can_use = TRUE 
                ORDER BY RAND() LIMIT 1
            """
            cursor.execute(sql, (prev_end,))
            next_word = cursor.fetchone()

            if next_word:
                chain.append(next_word['word'])
                print(f"   Turn {i}: {current['word']} -> {next_word['word']}")
                current = next_word
            else:
                print(f"🛑 게임 종료! '{current['word']}'(으)로 시작하는 단어가 더 이상 없습니다.")
                print("   (참고: can_use=TRUE 였는데 끊겼다면, 방금 그 단어가 유일한 연결고리였을 수 있습니다)")
                break
        
        print(f"✅ 시뮬레이션 완료 (총 {len(chain)}개 단어 연결)")

    finally:
        cursor.close()
        conn.close()

def test_logic_integrity():
    """
    [테스트 2] 로직 무결성 검증 (거짓말 탐지)
    can_use가 FALSE인 단어를 조회해서, 진짜로 잇는 단어가 없는지 확인
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n========== [TEST 2] 🕵️ 한방 단어 로직 검증 (무결성 체크) ==========")
    
    try:
        # 1. can_use = FALSE 인 단어 5개 랜덤 추출
        cursor.execute("SELECT word, end_char FROM ko_word WHERE can_use = FALSE ORDER BY RAND() LIMIT 5")
        dead_words = cursor.fetchall()
        
        if not dead_words:
            print("ℹ️ 검사할 '한방 단어(FALSE)'가 없습니다. (데이터가 너무 적거나 모두 살아있음)")
            return

        error_count = 0
        
        for item in dead_words:
            word = item['word']
            end_char = item['end_char']
            
            # 이 단어의 꼬리를 무는 '살아있는' 단어가 있는지 조회
            sql_check = "SELECT count(*) as cnt FROM ko_word WHERE start_char = %s AND can_use = TRUE"
            cursor.execute(sql_check, (end_char,))
            cnt = cursor.fetchone()['cnt']
            
            if cnt > 0:
                print(f"❌ 오류 발견! '{word}'는 can_use=FALSE인데, 이어질 수 있는 단어가 {cnt}개나 있습니다.")
                error_count += 1
            else:
                print(f"✅ 정상: '{word}' (끝: {end_char}) -> 이어지는 단어 없음 (0개). 확실한 한방 단어임.")

        if error_count == 0:
            print("🎉 완벽합니다! 모든 한방 단어(FALSE)가 정확하게 판별되었습니다.")
        else:
            print(f"⚠️ 경고: {error_count}개의 단어가 상태가 잘못되어 있습니다. '동기화 코드'를 다시 실행하세요.")

    finally:
        cursor.close()
        conn.close()

def test_data_quality():
    """
    [테스트 3] 데이터 품질 검사
    특수문자가 포함된 단어가 있는지 확인
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n========== [TEST 3] 🧬 데이터 품질 검사 (특수문자) ==========")
    
    try:
        # 정규표현식으로 한글 완성형이 아닌 것이 섞인 단어 조회
        sql = "SELECT word FROM ko_word WHERE word NOT REGEXP '^[가-힣]+$' LIMIT 5"
        cursor.execute(sql)
        dirty_words = cursor.fetchall()
        
        if dirty_words:
            print(f"❌ 불량 데이터 발견 ({len(dirty_words)}개 예시):")
            for w in dirty_words:
                print(f"   - {w['word']}")
            print("   -> 특수문자 제거 로직을 확인하거나 DELETE 문으로 삭제하세요.")
        else:
            print("✨ 깨끗합니다! 모든 단어가 순수 한글로 이루어져 있습니다.")
            
        # 2글자 미만 확인
        cursor.execute("SELECT count(*) as cnt FROM ko_word WHERE char_length(word) < 2")
        short_cnt = cursor.fetchone()['cnt']
        if short_cnt > 0:
            print(f"⚠️ 경고: 2글자 미만 단어가 {short_cnt}개 있습니다.")
        else:
            print("✨ 모든 단어가 2글자 이상입니다.")

    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    test_simulation()
    test_logic_integrity()
    test_data_quality()