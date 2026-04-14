import os
import sys

# Ensure backend root is in path
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from app.core.db import fetch_all
    
    # 1. 테이블 목록 조회
    tables_query = "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    tables = fetch_all(tables_query)
    
    print("--- Database Tables ---")
    for t in tables:
        table_name = t['table_name']
        
        # 2. 각 테이블의 레코드 수 조회
        count_query = f"SELECT COUNT(*) as cnt FROM {table_name}"
        count = fetch_all(count_query)[0]['cnt']
        
        print(f"Table: {table_name} (Rows: {count})")
        
except Exception as e:
    print(f"Error: {e}")
