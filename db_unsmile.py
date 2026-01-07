import pymysql
import os
import torch
from transformers import BertForSequenceClassification, AutoTokenizer, TextClassificationPipeline
from dotenv import load_dotenv
from tqdm import tqdm
from typing import List, Dict

# .env 파일 로드
load_dotenv()

# ==========================================
# [설정] 시작 번호 변수 (사용자 입력이 없을 시 사용됨)
# ==========================================
DEFAULT_START_NUM = 1 

class LocalAIFilterManager:
    def __init__(self):
        # 1. DB 설정
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'db': os.getenv('DB_NAME'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'charset': 'utf8mb4',
            'cursorclass': pymysql.cursors.DictCursor
        }

        # 2. 로컬 AI 모델 로드
        print("\n>> [시스템] AI 모델(smilegate-ai/kor_unsmile) 로딩 중...")
        
        self.device = 0 if torch.cuda.is_available() else -1
        self.device_name = "GPU(CUDA)" if self.device == 0 else "CPU"
        print(f">> [시스템] 가속 장치: {self.device_name}")

        model_name = 'smilegate-ai/kor_unsmile'
        # 토크나이저 병렬 처리 경고 방지
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = BertForSequenceClassification.from_pretrained(model_name)
        
        self.pipe = TextClassificationPipeline(
            model=self.model, 
            tokenizer=self.tokenizer, 
            device=self.device,
            return_all_scores=True
        )

        self.BATCH_SIZE = 64

    def get_connection(self):
        return pymysql.connect(**self.db_config)

    def get_filtered_count(self, start_num: int) -> int:
        """진행률 계산용 남은 데이터 수 조회"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT COUNT(*) as cnt FROM ko_word WHERE num >= %s AND available = TRUE"
                cursor.execute(sql, (start_num,))
                result = cursor.fetchone()
                return result['cnt']
        finally:
            conn.close()

    def fetch_word_batch(self, last_seen_num: int, limit: int) -> List[Dict]:
        """커서 기반 페이징"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                    SELECT num, word 
                    FROM ko_word 
                    WHERE num > %s AND available = TRUE 
                    ORDER BY num ASC 
                    LIMIT %s
                """
                cursor.execute(sql, (last_seen_num, limit))
                return cursor.fetchall()
        finally:
            conn.close()

    def analyze_words(self, words: List[str]) -> List[bool]:
        """AI 분석"""
        results = []
        predictions = self.pipe(words)
        
        for pred in predictions:
            is_bad = False
            for label_data in pred:
                if label_data['label'] != 'clean' and label_data['score'] > 0.85:
                    is_bad = True
                    break
            results.append(is_bad)
        return results

    def block_words(self, target_ids: List[int]):
        """DB 업데이트"""
        if not target_ids:
            return
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                format_strings = ','.join(['%s'] * len(target_ids))
                sql = f"UPDATE ko_word SET available = FALSE WHERE num IN ({format_strings})"
                cursor.execute(sql, tuple(target_ids))
                conn.commit()
        except Exception as e:
            conn.rollback()
            tqdm.write(f"!! DB Error: {e}")
        finally:
            conn.close()

    def run(self, start_num: int):
        # 1. 대상 데이터 확인
        print(f"\n>> [데이터베이스] num {start_num}번부터 데이터 조회 중...")
        target_count = self.get_filtered_count(start_num)
        
        if target_count == 0:
            print(f">> [알림] num {start_num} 이후로 검사할 데이터가 없습니다.")
            return

        print(f">> [시작] 총 {target_count:,}건의 단어 검사를 시작합니다.")

        # WHERE num > last_num 로직을 위해 시작값 - 1 설정
        last_num = start_num - 1
        total_blocked = 0
        
        # tqdm 진행바
        with tqdm(total=target_count, unit="word", desc="검사 중", ncols=100) as pbar:
            while True:
                rows = self.fetch_word_batch(last_num, self.BATCH_SIZE)
                if not rows:
                    break

                last_num = rows[-1]['num']
                word_list = [row['word'] for row in rows]
                
                # AI 분석
                is_bad_list = self.analyze_words(word_list)
                
                block_ids = []
                for i, is_bad in enumerate(is_bad_list):
                    if is_bad:
                        block_ids.append(rows[i]['num'])

                # DB 반영
                if block_ids:
                    self.block_words(block_ids)
                    total_blocked += len(block_ids)

                # 진행바 갱신
                pbar.update(len(rows))
                pbar.set_postfix({'LastID': last_num, '차단됨': total_blocked})

        print("\n" + "="*50)
        print(f"   [검사 완료]")
        print(f"   - 구간: {start_num} ~ {last_num}")
        print(f"   - 총 차단: {total_blocked:,}개")
        print("="*50)

if __name__ == "__main__":
    # ==========================================
    # [입력 방식 수정] 사용자 입력 또는 변수 사용
    # ==========================================
    print("="*50)
    print("   AI 단어 필터링 시스템 (Local Ver)")
    print("="*50)

    try:
        user_input = input(f"검사를 시작할 num 번호를 입력하세요 (엔터 시 기본값 {DEFAULT_START_NUM}부터 시작): ").strip()
        
        if user_input:
            start_num = int(user_input)
        else:
            start_num = DEFAULT_START_NUM
            print(f">> 입력이 없어 기본값({DEFAULT_START_NUM})으로 시작합니다.")
            
    except ValueError:
        print("\n!! 오류: 숫자를 입력해야 합니다. 프로그램을 종료합니다.")
        exit()

    # 실행
    manager = LocalAIFilterManager()
    manager.run(start_num=start_num)