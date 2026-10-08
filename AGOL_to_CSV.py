# Script to extract the AGOL feature layer table in CSV

import arcpy
import csv
import time

# --- CONFIGURATION ---
# Works with Points, Lines, Polygons, and Standalone Tables
service_url = "https://services7.arcgis.com/HCSaTVwBOe28HDf8/arcgis/rest/services/BOW_3_3__L/FeatureServer/6"
output_csv = r"C:\Users\sameer.bajracharya\Sam_works\PyScripts\ArcGIS\Data_Extract\Pole_Attachments_4_Aug_026.csv"

# Set to True for human-readable column titles (e.g., "Building Name" instead of "BLDG_NAME")
USE_ALIASES = False  
# ---------------------

print("Connecting to service and reading schema...")
start_time = time.time()

# 1. Inspect schema from REST service
all_fields = arcpy.ListFields(service_url)

# Exclude binary/spatial types
EXCLUDE_TYPES = ['Geometry', 'Raster', 'Blob']

# Exclude virtual/calculated REST fields that cause "Cannot find field" errors
VIRTUAL_FIELDS = [
    'area', 'length', 
    'shape_area', 'shape_length', 
    'shape.area', 'shape.len', 
    'st_area(shape)', 'st_length(shape)'
]

# Filter down strictly to queryable attribute fields
valid_field_objects = [
    f for f in all_fields 
    if f.type not in EXCLUDE_TYPES and f.name.lower() not in VIRTUAL_FIELDS
]

query_fields = [f.name for f in valid_field_objects]
header_fields = [f.aliasName if USE_ALIASES else f.name for f in valid_field_objects]

print(f"Schema validated. Extracting {len(query_fields)} attribute columns...")

# 2. Write CSV with explicit headers
with open(output_csv, mode='w', newline='', encoding='utf-8-sig') as csv_file:
    writer = csv.writer(csv_file)
    
    # WRITE HEADERS FIRST
    writer.writerow(header_fields)
    
    count = 0
    print("Streaming records...")
    
    # 3. Stream attribute rows directly from service
    with arcpy.da.SearchCursor(service_url, query_fields) as cursor:
        for row in cursor:
            writer.writerow(row)
            count += 1
            
            # Progress update every 250,000 rows
            if count % 250000 == 0:
                elapsed = round(time.time() - start_time, 1)
                print(f"  Extracted {count:,} records... ({elapsed} seconds elapsed)")

total_seconds = round(time.time() - start_time, 1)
print(f"\nSUCCESS: Exported {count:,} records with headers in {total_seconds} seconds.")
print(f"File saved at: {output_csv}")