"""
===============================================================================
Script Name: General Landbase Update v1
Description: 
    This script automates the process of updating ArcGIS Online (AGOL) Webmaps 
    with a specific General Landbase Map Service. It ensures that the target 
    webmap contains the most up-to-date General landbase layer while preserving existing 
    webmap configurations and specific sublayer styles.

Key Operations:
    1. AGOL Search: Dynamically searches the AGOL portal for a target Webmap 
       and its corresponding General Landbase Map Service based on utility 
       and location codes.
    2. Sublayer Preservation: Extracts and retains any existing sublayer 
       configurations currently saved in the Webmap so they are not overwritten.
    3. Targeted Label Update: Dynamically locates the "CITIES" sublayer and 
       updates its label visibility range (minScale) to the 'States' level 
       (6,000,000) WITHOUT altering its existing font, color, or symbol styling.
    4. Webmap JSON Injection: Safely inserts or replaces the General Landbase 
       layer within the webmap's 'operationalLayers' JSON definition.
    5. Logging: Generates an automatic, time-stamped log file tracking 
       successful updates, skipped items, and critical errors.

Dependencies: arcgis (ArcGIS API for Python), json, logging, os, copy
===============================================================================
"""

import json
import logging
import os
import copy
from typing import Optional, Any

from arcgis.gis import GIS, Item

# --- Logging Configuration ---
LOG_DIR = "PY_Logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE_PATH = os.path.join(LOG_DIR, 'general_landbase_updates.log')

logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Configuration Constants ---
UTILITY = "ALECTRA"
LAC_AREAS_ALL = ["OW01", "GN01", "GW01"]

# LAC_AREAS_ONTARIO = ["GE01", "GN01", "GN02", "GW01", "GW02", "HN01", "OE01", 
#                   "ONE01", "ONW01", "OS01", "OW01", "T01"]

# Alberta_Territory= ["EastAB", "SouthAB", "NorthAB", "Calgary", "CapitalNorth", "NorthCentral",
#                   "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]

LANDBASE = "GENLANDBASEON_LANDBASE"  # Use "GENLANDBASEAB_LANDBASE" for Alberta

# Extracted Map & Layer Constants
STATES_SCALE = 6000000
MAX_ZOOM_SCALE = 50000
LAYER_OPACITY = 0.65
SUBLAYER_TARGET_NAME = "CITIES"


def search_agol(gis_conn: GIS, query: str, feature_type: str) -> Optional[Item]:
    """Searches AGOL for an exact title match of a specific feature type."""
    try:
        search_text = f'title:\"{query}\" AND type:\"{feature_type}\"'
        print(f"Searching for: {search_text}")
        
        search_results = gis_conn.content.search(query=search_text, max_items=10)
        
        if not search_results:
            print(f"    '{query}' - Not Found in AGOL.")
            return None

        for item in search_results:
            if item.title == query:
                return item
        
        print(f"    '{query}' - No exact title match found in search results.")
        return None
    
    except Exception as e:
        error_msg = f"Error Searching Layers: {e}"
        print(error_msg)
        logging.error(error_msg)
        return None


def update_webmap(gis_conn: GIS, lac: str, webmap_item: Item, layer_item: Item) -> None:
    """Updates the target webmap by modifying the visible label range for CITIES while preserving styles."""
    
    webmap_definition: dict[str, Any] = webmap_item.get_data()
    operational_layers = webmap_definition.setdefault('operationalLayers', [])
    layer_id_to_check = f"General Landbase {layer_item.id}"

    # --- DYNAMIC SUB-LAYER ID & DEFAULT LABEL DISCOVERY ---
    # Efficiently find the CITIES layer using a generator expression
    target_layer = next(
        (lyr for lyr in getattr(layer_item, 'layers', []) 
         if getattr(lyr.properties, 'name', '').upper() == SUBLAYER_TARGET_NAME), 
        None
    )

    if target_layer:
        target_sublayer_id = target_layer.properties.id
        drawing_info = target_layer.properties.get('drawingInfo', {})
        service_labeling_info = copy.deepcopy(drawing_info.get('labelingInfo', []))
    else:
        logging.warning(f"'{SUBLAYER_TARGET_NAME}' sublayer not found in '{layer_item.title}'. Defaulting to ID 0.")
        target_sublayer_id = 0
        service_labeling_info = []

    # --- PRESERVE ALL EXISTING SUBLAYERS ---
    existing_index = next(
        (index for index, layer in enumerate(operational_layers) if layer.get("id") == layer_id_to_check), 
        None
    )
    
    existing_sublayers = []
    if existing_index is not None:
        existing_sublayers = copy.deepcopy(operational_layers[existing_index].get("layers", []))

    # --- EXTRACT AND UPDATE ONLY THE TARGET LABELING INFO ---
    target_sublayer = next((sl for sl in existing_sublayers if sl.get("id") == target_sublayer_id), None)
    
    if target_sublayer is None:
        target_sublayer = {"id": target_sublayer_id}
        existing_sublayers.append(target_sublayer)

    # Use webmap label styling if it exists; otherwise fallback to the service's default styling
    webmap_labeling_info = target_sublayer.get("layerDefinition", {}).get("drawingInfo", {}).get("labelingInfo")
    final_labeling_info = webmap_labeling_info if webmap_labeling_info else service_labeling_info

    # Update ONLY the minScale for the labels
    if final_labeling_info:
        for label_class in final_labeling_info:
            label_class["minScale"] = STATES_SCALE
    
    # Write the preserved style + new minScale back into the sublayer definition
    layer_def = target_sublayer.setdefault("layerDefinition", {})
    drawing_info = layer_def.setdefault("drawingInfo", {})
    drawing_info["labelingInfo"] = final_labeling_info
    
    # Ensure labels are explicitly turned on so they actually render
    target_sublayer["showLabels"] = True

    # --- CONSTRUCT PARENT LAYER ---
    general_landbase_layer = {
        "id": layer_id_to_check,
        "layerType": "ArcGISMapServiceLayer",
        "url": layer_item.url,
        "visibility": True,
        "showLabels": True, 
        "title": f"General Landbase {lac.upper()}",
        "itemId": layer_item.id,
        "opacity": LAYER_OPACITY,
        "minScale": STATES_SCALE, 
        "maxScale": MAX_ZOOM_SCALE,
        "layers": existing_sublayers
    }

    # Update or Insert Layer
    if existing_index is not None:
        operational_layers[existing_index] = general_landbase_layer
        action_msg = "Replaced Existing"
    else:
        operational_layers.insert(1, general_landbase_layer)
        action_msg = "New Inserted"
        
    # Push update back to AGOL
    webmap_item.update(item_properties={'text': json.dumps(webmap_definition)})
    
    # Log the successful update
    success_msg = f"{action_msg} layer '{layer_item.title}' ({SUBLAYER_TARGET_NAME} label minScale updated) in '{webmap_item.title}' (ID: {webmap_item.id})"
    print(f"\n>> {success_msg} <<\n")
    logging.info(success_msg)


def main() -> None:
    """Main execution function to isolate variables and improve execution speed."""
    logging.info("--- STARTED NEW SCRIPT EXECUTION ---")
    
    try:
        gis = GIS("home")
        conn_msg = f"Successfully connected to {gis.properties.portalName} as {gis.properties.user.username}"
        print(f"{conn_msg}\n")
        logging.info(conn_msg)

        for lac in LAC_AREAS_ALL:
            webmap_update = search_agol(gis, f"{UTILITY} {lac} WebMap", "Web Map")       
            general_landbase = search_agol(gis, f"{LANDBASE}__{lac}", "Map Service")

            if webmap_update and general_landbase:
                print(f"\nFound Web Map >> {webmap_update.title} (ID: {webmap_update.id})")
                print(f"Found Features >> {general_landbase.title}")
                
                update_webmap(gis, lac, webmap_update, general_landbase)          
            else:
                skip_msg = f"Skipping WebMap update for '{lac}' due to missing AGOL items."
                print(f"\n{skip_msg}\n")
                logging.warning(skip_msg)
                
    except Exception as e:
        error_msg = f"An unexpected error occurred during execution: {e}"
        print(error_msg)
        logging.critical(error_msg)
        
    finally:
        logging.info("--- FINISHED SCRIPT EXECUTION ---\n")


if __name__ == "__main__":
    main()