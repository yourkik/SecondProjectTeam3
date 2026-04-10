
import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union
import os

# Paths
PBF_PATH = r'workplace/data/seoul.osm.pbf'
SLOPE_PATH = r'workplace/data/Vworld/slope/ASIT_SOILSLOPE_AREA.shp'
OUTPUT_DIR = r'workplace/data/processed'
OUTPUT_SHP = os.path.join(OUTPUT_DIR, 'slope_gangdong_songpa.shp')

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Guessed CRS for the Slope Data
# (319k, 557k) range in East Seoul strongly suggests False Easting 300,000 / False Northing 500,000 or 600,000
# Based on typical Vworld/Legacy data, we test False Easting 300,000
SLOPE_CRS = "+proj=tmerc +lat_0=38 +lon_0=127 +k=1 +x_0=300000 +y_0=500000 +ellps=bessel +units=m +no_defs"

def run_clip():
    print("1. Extracting Gangdong-gu and Songpa-gu boundaries from OSM...")
    try:
        # PBF files are complex, we filter for admin_level and names
        # Note: This might take a bit of memory/time
        gdf_osm = gpd.read_file(PBF_PATH, layer='multipolygons')
        
        target_names = ['강동구', '송파구', 'Gangdong-gu', 'Songpa-gu']
        mask_gdf = gdf_osm[
            gdf_osm['name'].isin(target_names) | 
            gdf_osm.get('name:en', pd.Series()).isin(target_names) |
            gdf_osm.get('name:ko', pd.Series()).isin(target_names)
        ].copy()
        
        if mask_gdf.empty:
            print("Error: Could not find Gangdong/Songpa polygons in OSM.")
            return

        print(f"Found {len(mask_gdf)} district polygons.")
        
        # Combine and match CRS
        mask_gdf = mask_gdf.to_crs(SLOPE_CRS)
        unified_mask = unary_union(mask_gdf.geometry)
        bbox = unified_mask.bounds
        print(f"Target Bbox in Slope CRS: {bbox}")

    except Exception as e:
        print(f"Error extracting boundaries: {e}")
        return

    print("\n2. Clipping Slope Data (Using BBox filter for efficiency)...")
    try:
        # Load slope data limited to the bbox
        # encoding='cp949' for Korean shapefiles
        clipped_gdf = gpd.read_file(SLOPE_PATH, bbox=bbox, encoding='cp949')
        
        if clipped_gdf.empty:
            print("Warning: BBox filter returned zero results. The guessed CRS might be wrong.")
            # Let's try one more guess: False Northing 600,000
            print("Trying with False Northing 600,000...")
            SLOPE_CRS_ALT = "+proj=tmerc +lat_0=38 +lon_0=127 +k=1 +x_0=300000 +y_0=600000 +ellps=bessel +units=m +no_defs"
            mask_gdf_alt = gdf_osm[gdf_osm['name'].isin(target_names)].to_crs(SLOPE_CRS_ALT)
            bbox_alt = unary_union(mask_gdf_alt.geometry).bounds
            clipped_gdf = gpd.read_file(SLOPE_PATH, bbox=bbox_alt, encoding='cp949')
            
            if clipped_gdf.empty:
                print("Error: Still no data found. Coordinate system mismatch is severe.")
                return
            else:
                final_mask = unary_union(mask_gdf_alt.geometry)
                print("Found match with False Northing 600,000!")
        else:
            final_mask = unified_mask
            print(f"Initial load found {len(clipped_gdf)} features.")

        # Precise geometric clip
        print("Performing precise geometric clip...")
        final_result = gpd.clip(clipped_gdf, final_mask)
        
        print(f"Clipping finished. Total features: {len(final_result)}")
        
        # Save
        print(f"Saving to {OUTPUT_SHP}...")
        final_result.to_file(OUTPUT_SHP, encoding='cp949')
        print("Success!")

    except Exception as e:
        print(f"Error during clipping: {e}")

if __name__ == "__main__":
    run_clip()
