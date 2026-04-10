
import os
import sys

# Add workplace to path for safety
sys.path.append(os.getcwd())

import geopandas as gpd
from pyrosm import OSM
import pandas as pd
from shapely.ops import unary_union

# Paths
PBF_PATH = r'workplace/data/seoul.osm.pbf'
SLOPE_PATH = r'workplace/data/Vworld/slope/ASIT_SOILSLOPE_AREA.shp'
OUTPUT_DIR = r'workplace/data/processed'
OUTPUT_SHP = os.path.join(OUTPUT_DIR, 'slope_gangdong_songpa.shp')
BOUNDARY_PATH = os.path.join(OUTPUT_DIR, 'target_boundary.geojson')

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def process():
    print("1. Extracting administrative boundaries (Gangdong, Songpa)...")
    osm = OSM(PBF_PATH)
    boundaries = osm.get_boundaries()
    
    if boundaries is None:
        print("Failed to get boundaries from OSM.")
        return

    # Filter for Gangdong and Songpa
    targets = ['강동구', '송파구', 'Gangdong-gu', 'Songpa-gu']
    mask_gdf = boundaries[
        boundaries['name'].isin(targets) | 
        boundaries.get('name:en', pd.Series()).isin(targets) |
        boundaries.get('name:ko', pd.Series()).isin(targets)
    ].copy()

    if mask_gdf.empty:
        print("Could not find Gangdong-gu or Songpa-gu in OSM.")
        # Fallback: Print available names to debug
        print("Available boundaries:", boundaries['name'].unique()[:10])
        return

    print(f"Found {len(mask_gdf)} boundary polygons.")
    mask_gdf.to_file(BOUNDARY_PATH, driver='GeoJSON')
    print(f"Saved boundary to {BOUNDARY_PATH}")

    # Combine boundaries into one mask
    unified_boundary = unary_union(mask_gdf.geometry)

    print("\n2. Loading Slope Data (This may take a while)...")
    # To be memory efficient, we guess the CRS first and transform mask to match
    # Vworld slope usually EPSG:5179
    # Let's read just the metadata/first row to check CRS
    temp = gpd.read_file(SLOPE_PATH, rows=1)
    slope_crs = temp.crs
    print(f"Slope Data CRS: {slope_crs}")
    
    # Match mask CRS to slope CRS
    mask_gdf_proj = mask_gdf.to_crs(slope_crs)
    combined_mask = unary_union(mask_gdf_proj.geometry)

    # Use bbox for faster initial load
    bbox = combined_mask.bounds
    print(f"Reading slope data within bbox: {bbox}")
    
    # Read with bbox filter
    gdf_slope_clipped = gpd.read_file(SLOPE_PATH, bbox=bbox, encoding='cp949')
    print(f"Loaded {len(gdf_slope_clipped)} potential candidates from slope data.")

    # Precise clip
    print("Performing precise clip...")
    result = gpd.clip(gdf_slope_clipped, combined_mask)
    
    if result.empty:
        print("Warning: Clipped result is empty. Check if boundaries and slope data actually overlap.")
        return

    print(f"Clipping complete. Final feature count: {len(result)}")
    
    # Save output
    print(f"Saving to {OUTPUT_SHP}...")
    result.to_file(OUTPUT_SHP, encoding='cp949')
    print("Success!")

if __name__ == "__main__":
    process()
