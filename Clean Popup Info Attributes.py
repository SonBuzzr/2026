# Clean Popup Info Attributes for ArcGIS Web Maps
"""
Remove these attribtues from layer popup: "objectid", "shape__length", "lac_area", "shape__area", "shaper__area", "STA_CODE",
"st_length(shape)", "shape length", "globalid", "globalid_1", "mv.alberta.lac_area.area", 
"esri.gis.lac_area.area", "fid", "esri.gis.fortisalberta_network_conductors.fid
"""

import json
from arcgis.gis import GIS
from arcgis.features import FeatureLayer

UTILITY = "BELL"
LAC_AREAS_ALL = ["OE01", "T01"]
                # ["ABNORTH", "ABSOUTH", "ABWEST", "ABEAST", "ABCENTRAL"]
                #  "GN01", "GW01", "GW02", "HN01", "OE01", 
                #    "ONE01", "ONW01", "OS01", "OW01", "T01", "ON"]

# LAC_AREAS_ALBERTA = ["EastAB", "SouthAB", "NorthAB", "Calgary", "CapitalNorth", "NorthCentral", "Northeast",
#                      "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]

# LAC_AREAS_ONTARIO = ["GE01", "GN01", "GN02", "GW01", "GW02", "HN01", "OE01", 
#                    "ONE01", "ONW01", "OS01", "OW01", "T01"]

DISABLE_POPUP_LAYERS = ["TERRITORY"]
webmap_owner = "migration_tool"  #"migration_tool" #"abdillahi.hassan@planview.ca"

def search_AGOL(query, feature_type):
    try:
        search_text = f" title:'{query}' AND type:'{feature_type}' AND owner:{webmap_owner}"
        print(f"Searching for: {search_text}")
         # Increase max_items slightly in case there are multiple similar names
        search_results = gis.content.search(query=search_text, max_items=10)
        
        if not search_results:
            print(f"    {query} - Layers Not Found in AGOL.")
            return None

        # Strict Python verification: Loop through results to find the 100% match
        for item in search_results:
            print(item, query)
            if item.title == query:
                return item
        
        # If loop finishes without returning, no exact match was found
        print(f"    {query} - No exact title match found in search results.")
        return None
    
    except Exception as e:
        print(f"Error Searching Layers: {e}")
        return None 

def get_clean_label(field_name_str):
    """Helper to safely isolate the base field name, remove underscores, and make uppercase."""
    base = field_name_str.split('.')[-1]
    return base.replace('_', ' ').upper()

# --- Processing Functions ---
def clean_popup(layer_obj):
    """Fetches all layer fields from the source service and rebuilds popup configurations cleanly."""
    layer_name = layer_obj.get('title', 'Unknown Layer')
    layer_url = layer_obj.get('url')

    if not layer_url:
        print(f"  ⚠️ Skipping {layer_name}: No underlying service URL found.")
        return

    print(f"  🛠 Re-building complete field definition schema for: {layer_name}")

    # Exception list for fields that should be hidden
    exceptions = [
        "objectid", "shape__length", "lac_area", "shape__area", "shaper__area", "STA_CODE",
        "st_length(shape)", "shape length", "globalid", "globalid_1", "mv.alberta.lac_area.area", 
        "esri.gis.lac_area.area", "fid", "esri.gis.fortisalberta_network_conductors.fid"                
    ]

    try:
        # Connect to the live feature layer service to pull its structural dictionary fields
        fl = FeatureLayer(layer_url, gis=gis)
        service_fields = fl.properties.get('fields', [])
    except Exception as e:
        print(f"    Could not read service fields from URL: {e}. Falling back to existing JSON elements.")
        # Fallback to local keys if network reading fails
        service_fields = layer_obj.get('layerDefinition', {}).get('fields', [])

    if not service_fields:
        print("    ⚠️ No field definition profiles found to build.")
        return

    # Generate uniform, programmatic fieldInfo objects for ALL service fields
    complete_field_infos = []
    for f in service_fields:
        f_name = f.get('name', '')
        f_name_lower = f_name.split('.')[-1].lower()
        
        is_visible = f_name_lower not in exceptions
        clean_label = get_clean_label(f_name)

        complete_field_infos.append({
            "fieldName": f_name,
            "label": clean_label,
            "visible": is_visible,
            "isEditable": True
        })

    # ----------------------------------------------------
    # TIER 1: OVERWRITE LAYER SCHEMA DEFINITION
    # ----------------------------------------------------
    if 'layerDefinition' not in layer_obj:
        layer_obj['layerDefinition'] = {}
    
    ld = layer_obj['layerDefinition']
    
    # Overwrite fields with explicit local clean titles
    ld['fields'] = [{"name": f['fieldName'], "alias": f['label'], "type": "esriFieldTypeString"} for f in complete_field_infos]
    ld['fieldConfigurations'] = [{"name": f['fieldName'], "label": f['label'], "visible": f['visible']} for f in complete_field_infos]

    # ----------------------------------------------------
    # TIER 2: REBUILD POPUP OBJECT COMPLETELY
    # ----------------------------------------------------
    new_popup_title = layer_name.replace('_', ' ').upper()
    
    layer_obj['popupInfo'] = {
        "title": new_popup_title,
        "description": "",
        "mediaInfos": [],
        "expressionInfos": [],
        "fieldInfos": complete_field_infos, # Standard field config fallback
        "popupElements": [
            {
                "type": "fields",
                "fieldInfos": complete_field_infos # New Map Viewer strict tracking override
            }
        ]
    }
    print(f"    ✅ Success: Re-mapped all fields cleanly to uppercase with spaces.")

def find_layers_recursive(layer_list):
    """Traverses the JSON to find layers and sub-layers, disabling or updating popups."""
    for layer in layer_list:
        layer_title = layer.get('title', '').strip().upper()
        disable_this_popup = any(disable_name in layer_title for disable_name in DISABLE_POPUP_LAYERS)
        
        if disable_this_popup:
            print(f"  🚫 Disabling popup for layer: {layer.get('title')}")
            if 'popupInfo' in layer:
                del layer['popupInfo']
            layer['disablePopup'] = True
        else:
            clean_popup(layer)
        
        if 'layers' in layer:
            find_layers_recursive(layer['layers'])

def Update_Webmap_Popups(gis_conn, lac, current_webmap):
    try:
        webmap_item = current_webmap
        map_data = webmap_item.get_data()

        print(f"\nSearching for 'Layers' in Web Map: {webmap_item.title}")
        find_layers_recursive(map_data.get('operationalLayers', []))

        print("\nSaving updates to ArcGIS Online/Enterprise...")
        update_result = webmap_item.update(item_properties={'text': json.dumps(map_data)})

        print(f"Update Status: {update_result}")
        if update_result:
            print("✨ Script finished!")
            print("⚠️ IMPORTANT: Close your map viewer tab entirely and re-open it to bypass localized session storage caching.")
    except Exception as e:
        print(f"An error occurred updating popup in Webmap: {e}")
    
# --- Main Execution Block ---
try:
    gis = GIS("home")
    print(f"Successfully connected to {gis.properties.portalName} as {gis.properties.user.username}\n")

    for lac in LAC_AREAS_ALL:
        webmap_update = search_AGOL(f"{UTILITY} {lac} WebMap", "Web Map")        
        if webmap_update:
            Update_Webmap_Popups(gis, lac, webmap_update)
        else:
            print(f"Skipping update for {lac} because the Web Map was not found.")
except Exception as e:
    print(f"An error occurred while searching for Webmap: {e}")