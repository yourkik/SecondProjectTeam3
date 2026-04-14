import os
import sys
import pandas as pd
from datetime import datetime

# Ensure backend root is in path
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from app.core.db import fetch_all
    
    # 저장 폴더 생성
    export_dir = os.path.join(current_dir, "db_exports")
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    # 1. 내보낼 테이블 목록 정의
    tables_to_export = [
        "park", 
        "pet_cafe", 
        "dog_playground", 
        "trail_features", 
        "animal_hospital",
        "walk_environment"
    ]
    
    print(f"--- Azure DB Data Exporting (Destination: {export_dir}) ---")
    
    for table in tables_to_export:
        print(f"Exporting table: {table}...", end=" ", flush=True)
        try:
            # 모든 데이터 조회
            rows = fetch_all(f"SELECT * FROM {table}")
            if not rows:
                print("Skipped (No data).")
                continue
            
            # DataFrame 변환 및 저장
            df = pd.DataFrame(rows)
            filename = f"{table}_{datetime.now().strftime('%Y%m%d')}.csv"
            filepath = os.path.join(export_dir, filename)
            
            # UTF-8 with BOM for Excel compatibility
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            print(f"Done! ({len(rows)} rows)")
        except Exception as e:
            print(f"Failed ({e})")

    print("\n[SUCCESS] 모든 주요 테이블 내보내기가 완료되었습니다.")
    print(f"파일 경로: {export_dir}")

except Exception as e:
    print(f"\n[ERROR] 스크립트 실행 중 오류 발생: {e}")
