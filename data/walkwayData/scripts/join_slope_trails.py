
import geopandas as gpd
import pandas as pd
import numpy as np
import os

# Paths
SLOPE_PATH = r'workplace/data/Vworld/slope/gangnam_songpa_gangdong_soilslope.shp'
TRAIL_PATH = r'workplace/data/PTP019401/ECLGY_CLTUR_ST_2015_W_SHP/ECLGY_CLTUR_ST_2015_W.shp'
OUTPUT_DIR = r'workplace/data/processed'
OUTPUT_SHP = os.path.join(OUTPUT_DIR, 'trail_with_slope_final.shp')
OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'trail_slope_summary_final.csv')

# Slope Value Mapping (Based on SOILSLOPE strings: 0-7%, 7-15%, etc.)
# Mapping to the midpoint of the range
SLOPE_MAP = {
    '0-7%': 3.5,
    '7-15%': 11.0,
    '15-30%': 22.5,
    '30-60%': 45.0,
    '60-100%': 80.0
}

def run_integration():
    print("1. Loading datasets...")
    gdf_slope = gpd.read_file(SLOPE_PATH, encoding='cp949')
    gdf_trail = gpd.read_file(TRAIL_PATH, encoding='cp949')
    
    # Store original area for weighted average
    # Use EPSG:5181 for the slope data as identified during research
    slope_crs = 'EPSG:5181'
    gdf_slope.crs = slope_crs

    print(f"2. Projecting trail data to Slope CRS...")
    gdf_trail = gdf_trail.to_crs(slope_crs)
    
    # Calculate original area of each trail/area polygon
    gdf_trail['total_area'] = gdf_trail.geometry.area
    
    # Ensure trail has a unique ID for joining back
    if 'TRAIL_ID' not in gdf_trail.columns:
        gdf_trail['TRAIL_ID'] = range(len(gdf_trail))

    print("3. Performing Spatial Overlay (Intersection)...")
    # This cuts trails by slope polygons
    intersection = gpd.overlay(gdf_trail, gdf_slope, how='intersection')
    
    print(f"   Intersection resulted in {len(intersection)} fragments.")

    # 4. Calculate weighted average
    print("4. Calculating weighted average slope...")
    
    # Map SOILSLOPE strings to numeric values
    intersection['slope_num'] = intersection['SOILSLOPE'].map(SLOPE_MAP).fillna(0)
    
    # Calculate area of each fragment
    intersection['frag_area'] = intersection.geometry.area
    
    # Calculate (slope * area) for each fragment
    intersection['weighted_val'] = intersection['slope_num'] * intersection['frag_area']
    
    # Aggregate by Trail ID/Name
    # Group by original columns we want to keep
    keep_cols = ['NAME', 'SIGNGU_NM', 'ECLGY_NM', 'total_area', 'TRAIL_ID']
    # Filter only columns that exist
    keep_cols = [c for c in keep_cols if c in gdf_trail.columns]
    
    summary = intersection.groupby('TRAIL_ID').agg({
        'weighted_val': 'sum',
        'frag_area': 'sum'
    }).reset_index()
    
    # Calculate final average: Sum(val * area) / Sum(area)
    # We use summary['frag_area'] instead of total_area to handle cases where 
    # the trail is only partially covered by slope data
    summary['avg_slope_num'] = summary['weighted_val'] / summary['frag_area']
    
    # Merge back to original trail data
    final_gdf = gdf_trail.merge(summary[['TRAIL_ID', 'avg_slope_num', 'frag_area']], on='TRAIL_ID', how='left')
    
    # Handle "정보 없음" (No info) case
    # If frag_area is significantly less than total_area or NaN, it's missing info
    def format_slope(row):
        if pd.isna(row['avg_slope_num']) or row['frag_area'] < 1.0: # Very small overlap or no overlap
            return "정보 없음"
        return f"{row['avg_slope_num']:.1f}%"

    print("5. Formatting results...")
    final_gdf['AVG_SLOPE'] = final_gdf.apply(format_slope, axis=1)
    
    # Clean up temporary columns
    columns_to_drop = ['total_area', 'avg_slope_num', 'frag_area', 'TRAIL_ID']
    final_gdf = final_gdf.drop(columns=[c for c in columns_to_drop if c in final_gdf.columns])

    print(f"6. Saving final results to {OUTPUT_SHP}...")
    final_gdf.to_file(OUTPUT_SHP, encoding='cp949')
    final_gdf.drop(columns='geometry').to_csv(OUTPUT_CSV, encoding='cp949', index=False)
    
    print("Integration Success!")
    print(f"Result summary saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    run_integration()
