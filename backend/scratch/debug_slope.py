import os
import sys

# Ensure backend root is in path
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from app.core.db import fetch_all
    
    query = "SELECT trail_name, avg_slope, slope_type FROM trail_features WHERE trail_name LIKE '%성내천%'"
    rows = fetch_all(query)
    
    print(f"Found {len(rows)} rows matching '성내천':")
    for row in rows:
        name = row['trail_name']
        avg = row['avg_slope']
        type_val = row['slope_type']
        
        print(f"Name: {name}")
        print(f"Avg Slope: {avg}")
        print(f"Slope Type: {type_val}")
        if type_val:
            print(f"Slope Type Characters: {[ord(c) for c in type_val]}")
except Exception as e:
    print(f"Error: {e}")
