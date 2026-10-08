"""
ArcGIS Web Map Duplicator Script
--------------------------------
This script searches for Web Maps across specified LAC areas and creates exact duplicates
by copying the underlying Web Map JSON definition. 

Key Features:
1. Preserves 100% of layers, symbology, popups, labels, and map configurations.
2. References original layer URLs directly (does not clone or duplicate feature datasets).
3. Uses modern ArcGIS API for Python (v2.3+ / v3.0+ compliant syntax).
4. Replicates original sharing permissions (Private, Org, Everyone, and Group access).
"""

"""
ArcGIS Web Map Duplicator Script
--------------------------------
Duplicates Web Maps across specified LAC areas by copying their raw JSON definitions.
Compatible with ArcGIS API for Python v2.3+ and v3.0+ (handles async Future objects).
"""

import json
import os
from arcgis.gis import GIS

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
UTILITY = "ATCO_ELECTRIC"                    # Title prefix for search (e.g. "ATCO_GAS", "ATCO_ELECTRIC")
WEBMAP_OWNER = "migration_tool"         # Target owner account of source web maps
TARGET_FOLDER_NAME = "Duplicated_WebMaps" # Folder where duplicated maps will be saved

# List of LAC area codes to process
LAC_AREAS_ALL = ["EastAB", "SouthAB", "NorthAB", "CapitalNorth", "NorthCentral", "Northeast",
    "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]

# ["EastAB", "SouthAB", "NorthAB", "CapitalNorth", "NorthCentral", "Northeast",
#     "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
def get_or_create_folder(gis, folder_name):
    """
    Ensures the target folder exists in ArcGIS.
    Returns a Folder object using modern v2.3+/v3.0+ API syntax.
    """
    try:
        folder = gis.content.folders.get(folder_name)
        if not folder:
            folder = gis.content.folders.create(folder_name)
            print(f"  [INFO] Created new folder: '{folder_name}'")
        else:
            print(f"  [INFO] Located target folder: '{folder_name}'")
        return folder
    except Exception as e:
        print(f"  [ERROR] Folder check failed ({e}). Defaulting to root directory.")
        return gis.content.folders.get()


def find_webmap(gis, title, owner):
    """
    Searches AGOL/Enterprise for an exact Web Map title.
    Includes a fallback search if owner restriction returns zero results.
    """
    try:
        # Primary search with owner filter
        query = f"title:'{title}' AND type:'Web Map' AND owner:{owner}"
        results = gis.content.search(query=query, max_items=10)

        # Fallback search across all owners if primary returns empty
        if not results:
            query_fallback = f"title:'{title}' AND type:'Web Map'"
            results = gis.content.search(query=query_fallback, max_items=10)

        # Return exact title match
        for item in results:
            if item.title == title:
                return item
                
        return None
    except Exception as e:
        print(f"  [ERROR] Search failed for '{title}': {e}")
        return None


def extract_item_sharing_info(item):
    """
    Extracts sharing level (everyone, org) and group IDs robustly 
    across all ArcGIS API for Python versions.
    """
    everyone = False
    org = False
    group_ids = []

    # 1. Determine level from item.access ('public', 'org', 'shared', or 'private')
    access = getattr(item, "access", "private").lower()
    if access in ["public", "everyone"]:
        everyone = True
        org = True
    elif access in ["org", "organization"]:
        org = True

    # 2. Extract group IDs using modern API v2.3+ / v3.0+
    try:
        if hasattr(item, "sharing"):
            if hasattr(item.sharing, "groups") and hasattr(item.sharing.groups, "list"):
                group_list = item.sharing.groups.list()
            elif hasattr(item.sharing, "shared_with"):
                group_list = item.sharing.shared_with.get("groups", [])
            else:
                group_list = []

            for g in group_list:
                gid = g.id if hasattr(g, "id") else (g.get("id") if isinstance(g, dict) else str(g))
                if gid and gid not in group_ids:
                    group_ids.append(gid)
    except Exception as e:
        print(f"  [DEBUG] Error extracting groups via item.sharing: {e}")

    # 3. Fallback to legacy item.shared_with dict if group_ids is still empty
    if not group_ids and hasattr(item, "shared_with"):
        try:
            sw = item.shared_with
            if callable(sw):
                sw = sw()
            if isinstance(sw, dict):
                everyone = everyone or sw.get("everyone", False)
                org = org or sw.get("org", False)
                for g in sw.get("groups", []):
                    gid = g.id if hasattr(g, "id") else (g.get("id") if isinstance(g, dict) else str(g))
                    if gid and gid not in group_ids:
                        group_ids.append(gid)
        except Exception:
            pass

    return {"everyone": everyone, "org": org, "groups": group_ids}


def duplicate_webmap(gis, source_item, target_folder_obj, target_title):
    """
    Duplicates a Web Map by extracting/uploading its raw JSON payload as-is
    and replicating exact sharing permissions.
    """
    try:
        # Step 1: Read raw web map JSON structure
        webmap_json = source_item.get_data()
        if not webmap_json:
            print(f"  [ERROR] Could not read JSON definition from '{source_item.title}'")
            return None

        # Step 2: Define item metadata using custom target title
        item_properties = {
            "title": target_title,
            "type": "Web Map",
            "snippet": source_item.snippet or "",
            "description": source_item.description or "",
            "tags": source_item.tags or [],
            "text": json.dumps(webmap_json)  # Unmodified map JSON definition
        }

        # Step 3: Add item via Folder instance
        add_result = target_folder_obj.add(item_properties=item_properties)
        
        # Step 4: Resolve Future object to get actual Item instance (API v2.3+/v3.0+)
        if hasattr(add_result, "result") and callable(add_result.result):
            new_item = add_result.result()
        else:
            new_item = add_result

        # Step 5: Copy thumbnail image (optional)
        try:
            thumb_path = source_item.download_thumbnail()
            if thumb_path and os.path.exists(thumb_path):
                new_item.update(thumbnail=thumb_path)
                os.remove(thumb_path)
        except Exception:
            pass

        # Step 6: Replicate original sharing permissions
        try:
            sharing = extract_item_sharing_info(source_item)
            
            new_item.share(
                everyone=sharing["everyone"],
                org=sharing["org"],
                groups=sharing["groups"]
            )
            print(f"  [INFO] Shared map -> Everyone: {sharing['everyone']}, Org: {sharing['org']}, Groups: {len(sharing['groups'])}")
        except Exception as share_err:
            print(f"  [WARNING] Could not replicate sharing permissions: {share_err}")

        return new_item

    except Exception as e:
        print(f"  [ERROR] Duplication failed for '{source_item.title}': {e}")
        return None


# ==============================================================================
# 3. MAIN WORKFLOW
# ==============================================================================
def main():
    try:
        # Initialize connection using active ArcGIS session
        gis = GIS("home")

        # Header Information
        print("\n" + "=" * 65)
        print("  ARCGIS ENTERPRISE - WEB MAP DIRECT JSON DUPLICATOR")
        print("=" * 65)
        print(f"  Portal User : {gis.properties.user.username}")
        print(f"  Portal Name : {gis.properties.portalName}")
        print(f"  Utility     : {UTILITY}")
        print(f"  Total LACs  : {len(LAC_AREAS_ALL)} areas")
        print("=" * 65)

        # Step 1: Initialize/get target folder
        target_folder = get_or_create_folder(gis, TARGET_FOLDER_NAME)
        print("=" * 65 + "\n")

        stats = {"success": 0, "skipped": 0, "warning": 0}

        # Step 2: Loop through each LAC area
        for idx, lac in enumerate(LAC_AREAS_ALL, 1):
            source_map_title = f"{UTILITY} {lac} WebMap"
            target_map_title = f"{UTILITY} {lac} Hosted WebMap"

            print(f"[{idx}/{len(LAC_AREAS_ALL)}] Processing LAC Area: {lac}")
            print(f"  Searching   : '{source_map_title}'")

            # Find original item
            webmap_item = find_webmap(gis, title=source_map_title, owner=WEBMAP_OWNER)

            if webmap_item:
                print(f"  Found Item  : '{webmap_item.title}' (ID: {webmap_item.id})")

                # Perform direct JSON duplicate with exact sharing replication
                cloned_item = duplicate_webmap(
                    gis=gis,
                    source_item=webmap_item,
                    target_folder_obj=target_folder,
                    target_title=target_map_title
                )

                if cloned_item:
                    print(f"  [SUCCESS] Duplicated to: '{cloned_item.title}' (ID: {cloned_item.id})")
                    stats["success"] += 1
                else:
                    stats["warning"] += 1
            else:
                print(f"  [SKIP] Source Web Map '{source_map_title}' was not found.")
                stats["skipped"] += 1

            print("-" * 65)

        # Step 3: Print final summary
        print("\n" + "=" * 65)
        print("  EXECUTION SUMMARY")
        print("=" * 65)
        print(f"  Successfully Duplicated : {stats['success']}")
        print(f"  Skipped (Not Found)     : {stats['skipped']}")
        print(f"  Warnings / Failures     : {stats['warning']}")
        print("=" * 65 + "\n")

    except Exception as e:
        print(f"\n[CRITICAL ERROR] Execution failed: {e}")


if __name__ == "__main__":
    main()