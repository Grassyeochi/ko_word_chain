import pymysql
import os
import torch
from torch.utils.data import Dataset # <--- [추가] 데이터셋 클래스 필수
from transformers import BertForSequenceClassification, AutoTokenizer, TextClassificationPipeline
from dotenv import load_dotenv
from tqdm import tqdm
from typing import List, Dict

load_dotenv()

DEFAULT_START_NUM = 1 

# ==========================================
# [추가] 파이프라인 전용 데이터셋 래퍼 클래스
# ==========================================
class ListDataset(Dataset):
    def __init__(self, original_list):
        self.original_list = original_list
        
    def __len__(self):
        return len(self.original_list)
        
    def __getitem__(self, i):
        return self.original_list[i]

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
        print("\n>> [시스템] AI 모델 로딩 중...")
        self.device = 0 if torch.cuda.is_available() else -1
        self.device_name = "GPU(CUDA)" if self.device == 0 else "CPU"
        print(f">> [시스템] 가속 장치: {self.device_name}")

        model_name = 'smilegate-ai/kor_unsmile'
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = BertForSequenceClassification.from_pretrained(model_name)
        
        # 파이프라인 생성
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
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT COUNT(*) as cnt FROM ko_word WHERE num >= %s AND available = TRUE"
                cursor.execute(sql, (start_num,))
                return cursor.fetchone()['cnt']
        finally:
            conn.close()

    def fetch_word_batch(self, last_seen_num: int, limit: int) -> List[Dict]:
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
        """
        [수정됨] ListDataset을 사용하여 경고 제거 및 속도 최적화
        """
        results = []
        
        # 1. 리스트를 PyTorch Dataset으로 포장
        dataset = ListDataset(words)
        
        # 2. 파이프라인에 Dataset 객체 전달 (이제 경고가 뜨지 않습니다)
        # batch_size를 설정하면 내부 DataLoader가 멀티스레딩으로 데이터를 공급합니다.
        predictions = self.pipe(dataset, batch_size=self.BATCH_SIZE)
        
        # 3. 결과 순회 (Dataset을 쓰면 제너레이터가 반환됨)
        for pred in predictions:
            is_bad = False
            for label_data in pred:
                if label_data['label'] != 'clean' and label_data['score'] > 0.85:
                    is_bad = True
                    break
            results.append(is_bad)
            
        return results

    def block_words(self, target_ids: List[int]):
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
        print(f"\n>> [데이터베이스] num {start_num}번부터 조회...")
        target_count = self.get_filtered_count(start_num)
        
        if target_count == 0:
            print(f">> [알림] 데이터가 없습니다.")
            return

        print(f">> [시작] {target_count:,}건 검사 시작.")
        last_num = start_num - 1
        total_blocked = 0
        
        with tqdm(total=target_count, unit="word", ncols=100) as pbar:
            while True:
                rows = self.fetch_word_batch(last_num, self.BATCH_SIZE)
                if not rows:
                    break

                last_num = rows[-1]['num']
                word_list = [row['word'] for row in rows]
                
                is_bad_list = self.analyze_words(word_list)
                
                block_ids = []
                for i, is_bad in enumerate(is_bad_list):
                    if is_bad:
                        block_ids.append(rows[i]['num'])

                if block_ids:
                    self.block_words(block_ids)
                    total_blocked += len(block_ids)

                pbar.update(len(rows))
                pbar.set_postfix({'LastID': last_num, '차단됨': total_blocked})

        print(f"\n[완료] 총 차단: {total_blocked:,}건")

if __name__ == "__main__":
    try:
        user_input = input(f"시작 번호 입력 (기본값 {DEFAULT_START_NUM}): ").strip()
        start_num = int(user_input) if user_input else DEFAULT_START_NUM
        
        manager = LocalAIFilterManager()
        manager.run(start_num=start_num)
        
    except ValueError:
        print("숫자를 입력하세요.")
    except KeyboardInterrupt:
        print("중단됨.")