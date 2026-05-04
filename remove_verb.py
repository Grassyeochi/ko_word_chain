import os
import pymysql
from dotenv import load_dotenv
from kiwipiepy import Kiwi

def process_compound_words_only():
    # 1. .env 파일에서 DB 정보 로드
    load_dotenv()
    
    db_host = os.getenv('DB_HOST')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')

    # Kiwi 형태소 분석기 초기화
    kiwi = Kiwi()
    
    # [수정 2] 지시하신 2가지 출처로 한정
    valid_sources = ['URI', 'Standard']
    
    conn = None
    try:
        # DB 연결
        conn = pymysql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            db=db_name,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # [수정 2] source가 URI, Standard인 항목 중 available이 True인 것만 조회
        sql_select = """
            SELECT word, source, can_use 
            FROM ko_word 
            WHERE source IN ('URI', 'Standard')
              AND available = True
        """
        cursor.execute(sql_select)
        results = cursor.fetchall()
        
        total_count = len(results)
        processed_count = 0
        category_updated_count = 0
        source_updated_count = 0

        if total_count == 0:
            print("[보고] 지시하신 조건(URI/Standard 출처 및 available=True)에 부합하는 대상 단어가 없습니다.")
            return

        # UPDATE 쿼리 준비
        sql_update_category = """
            UPDATE ko_word 
            SET is_use_user = %s, available = False, can_use = %s 
            WHERE word = %s
        """
        sql_update_can_use = "UPDATE ko_word SET can_use = %s WHERE word = %s"

        for row in results:
            word = row[0].strip()
            source = row[1]
            current_can_use = row[2]
            
            if not word:
                processed_count += 1
                continue
                
            # Kiwi를 활용한 단어 분석
            analysis_result = kiwi.analyze(word)
            
            if not analysis_result:
                processed_count += 1
                continue
            
            morphs = analysis_result[0][0]
            category = None
            
            # [수정 1] 동사/형용사 판별 로직 제거, 합성어 판별 로직만 단독 수행
            if len(morphs) >= 2:
                # 명사(N), 동사/형용사 어간(V) 등 실질 의미를 지닌 형태소가 2개 이상 결합되었는지 확인
                meaningful_morphs = [m for m in morphs if m[1].startswith('N') or m[1].startswith('V')]
                if len(meaningful_morphs) >= 2:
                    category = '합성어'
            
            expected_can_use = True if source in valid_sources else False
            status_msg = "해당 없음 (상태 유지)"
            
            # DB 업데이트 로직
            if category:
                cursor.execute(sql_update_category, (category, expected_can_use, word))
                category_updated_count += 1
                status_msg = f"{category} 판별 (available=False 처리)"
                
            elif current_can_use != expected_can_use:
                cursor.execute(sql_update_can_use, (expected_can_use, word))
                source_updated_count += 1
                status_msg = f"can_use 상태 교정 ({expected_can_use})"
            
            processed_count += 1
            
            # 실시간 콘솔 한 줄 출력
            print(f"\r[처리 진행률: {processed_count}/{total_count}] 단어: '{word}' -> {status_msg}" + " " * 15, end='', flush=True)
            
        # 작업 완료 후 커밋
        conn.commit()
        
        print("\n\n[보고] 합성어 전용 검수 및 DB 업데이트가 완료되었습니다.")
        print(f"- 총 검사 대상 단어: {total_count}건")
        print(f"- 합성어 필터링(available=False 처리): {category_updated_count}건")
        print(f"- 사용 가능 여부(can_use) 상태 교정: {source_updated_count}건")
        
    except Exception as e:
        if conn and conn.open:
            conn.rollback()
        print(f"\n[오류 보고] DB 처리 중 문제가 발생했습니다: {e}")
    finally:
        if conn and conn.open:
            cursor.close()
            conn.close()

if __name__ == "__main__":
    process_compound_words_only()