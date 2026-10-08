# Script to turn on/off labels for specific layers in ArcGIS Web Maps based on LAC areas.
# Labels are disabled for the "General LLD" layer in each Web Map corresponding to the LAC area.

import json
from arcgis.gis import GIS

UTILITY = "ATCO_ELECTRIC"
webmap_owner = "migration_tool" # "abdillahi.hassan@planview.ca"

LAC_AREAS_ALL = ["EastAB", "SouthAB", "NorthAB", "Calgary", "CapitalNorth", "NorthCentral", "Northeast",
                     "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]
                #  "GN01", "GW01", "GW02", "HN01", "OE01", 
                #    "ONE01", "ONW01", "OS01", "OW01", "T01", "ON"]


def search_AGOL(query, feature_type):
    try:
        search_text = f"title:'{query}' AND type:'{feature_type}' AND owner:{webmap_owner}"
        search_results = gis.content.search(query=search_text, max_items=10)
        
        if not search_results:
            return None

        for item in search_results:
            if item.title == query:
                return item
        
        return None
    
    except Exception as e:
        print(f"  [ERROR] AGOL search failed: {e}")
        return None


def enable_target_layer_label(webmap_item, layer_name):
    """
    Searches operationalLayers and nested sublayers for layer_name
    and sets 'showLabels': True inside the Web Map JSON data.
    """
    def update_layers_recursive(layers):
        modified_count = 0
        for layer in layers:
            if layer.get("title") == layer_name:
                layer["showLabels"] = True
                modified_count += 1
                print(f"  [UPDATED] Enabled labels on layer -> '{layer_name}'")

            if "layers" in layer and isinstance(layer["layers"], list):
                modified_count += update_layers_recursive(layer["layers"])

        return modified_count

    try:
        data = webmap_item.get_data()
        if not data or "operationalLayers" not in data:
            print(f"  [WARNING] No operational layers found in Web Map: {webmap_item.title}")
            return False

        updated_count = update_layers_recursive(data["operationalLayers"])

        if updated_count > 0:
            webmap_item.update(data=json.dumps(data))
            print(f"  [SUCCESS] Changes saved to Web Map: '{webmap_item.title}'")
            return True
        else:
            print(f"  [WARNING] Layer '{layer_name}' was not found in Web Map JSON.")
            return False

    except Exception as e:
        print(f"  [ERROR] Failed to update JSON for '{webmap_item.title}': {e}")
        return False


# --- Main Execution Block ---
try:
    gis = GIS("home")
    
    # Header Banner
    print("\n" + "=" * 65)
    print("  ARCGIS ENTERPRISE - WEB MAP LABEL UPDATER")
    print("=" * 65)
    print(f"  Portal User : {gis.properties.user.username}")
    print(f"  Portal Name : {gis.properties.portalName}")
    print(f"  Utility     : {UTILITY}")
    print(f"  Target LACs : {len(LAC_AREAS_ALL)} area(s)")
    print("=" * 65 + "\n")

    stats = {"success": 0, "skipped": 0, "warning": 0}

    for idx, lac in enumerate(LAC_AREAS_ALL, 1):
        map_title = f"{UTILITY} {lac} WebMap" 
        target_layer_name = f"General LLD {lac}"

        print(f"[{idx}/{len(LAC_AREAS_ALL)}] Processing LAC Area: {lac}")
        print(f"  Searching   : '{map_title}'")

        webmap_update = search_AGOL(map_title, "Web Map")        
        
        if webmap_update:
            print(f"  Item Found  : '{webmap_update.title}' (ID: {webmap_update.id})")
            print(f"  Target Layer: '{target_layer_name}'")
            
            if enable_target_layer_label(webmap_update, target_layer_name):
                stats["success"] += 1
            else:
                stats["warning"] += 1
        else:
            print(f"  [SKIP] Web Map '{map_title}' was not found.")
            stats["skipped"] += 1

        print("-" * 65)

    # Final Summary Report
    print("\n" + "=" * 65)
    print("  EXECUTION SUMMARY")
    print("=" * 65)
    print(f"  Successfully Updated : {stats['success']}")
    print(f"  Skipped (Not Found)  : {stats['skipped']}")
    print(f"  Warnings / No Match  : {stats['warning']}")
    print("=" * 65 + "\n")

except Exception as e:
    print(f"\n[CRITICAL ERROR] Execution failed: {e}")