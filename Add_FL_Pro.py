import arcpy
import sys
import os
import re
from arcgis.gis import GIS

def is_project_locked(aprx_path):
    """
    Checks if the .aprx file is locked by another process (like ArcGIS Pro)
    by attempting to open it in append mode.
    """
    if not os.path.exists(aprx_path):
        print(f"Error: Project file not found at {aprx_path}")
        return True

    try:
        # Try to open the file in append mode just to check permissions
        # We don't write anything, just open and close.
        with open(aprx_path, 'a'):
            pass
        return False # It is NOT locked
    except PermissionError:
        return True # It IS locked (Permission Denied)
    except IOError as e:
        print(f"File access error: {e}")
        return True

def clear_map(aprx_proj):
    """  
    aprx_file: ArcGIS Pro file

    Finds the map, unchecks basemaps (Topo/Hillshade), and removes all other operational layers and tables.
    """
    try:
        print(f"\n--- Cleaning '{aprx_proj.name}' layers ---\n")

        for lyr in aprx_proj.listLayers()[::-1]:
            try:
                # Check if it is a Basemap or Topographic or Hillshade
                is_basemap = (lyr.isBasemapLayer) or \
                             ("topographic" in lyr.name.lower()) or \
                             ("hillshade" in lyr.name.lower())

                if is_basemap:
                    # Keep it, but uncheck it (make invisible)
                    if lyr.visible:
                        lyr.visible = False
                        print(f" [Unchecked] Basemap layer: {lyr.name}")
                else:
                    # Remove everything else
                    print(f"  Removing Layer: {lyr.name}") 
                    aprx_proj.removeLayer(lyr)
                    

            except Exception as e:
                print(f" [ERROR] Could not process {lyr.name}: {e}")

        # Remove all standalone tables
        for tbl in map_item.listTables()[::-1]:
            print(f"  [REMOVE] Table: {tbl.name}")
            map_item.removeTable(tbl)  
        
        print("\nCleaning existing layers completed.")
        return map_item  # Return the map object so the next function can use it
    
    except IndexError:
        print(f"Error: Map '{map_name}' not found in project.")
        return None
    

def add_layers(gis_obj, map_obj, search_query, search_type):
    """
    Searches for a Feature Service, looks inside it for sub-layers
    matching the name_filter, and adds them individually.
    """
    if not map_obj:
        print("Skipping add_layer: No valid map object provided.")
        return

    print(f"--- Searching & Adding Data ---")

    # Search for the service
    items = gis_obj.content.search(query=search_query, item_type=search_type)

    if items:
        target_item = items[0]
        print(f"Found Item: {target_item.title}")
        target_layers_url = target_item.url
        print(target_layers_url)
        
        # found_count = 0

        map_obj.addDataFromPath(target_layers_url)

        updated_layer = map_obj.listLayers()[0]

        print(f"Original Name: {updated_layer.name}")

        # 3. Rename the layer
        if re.match(pattern, updated_layer.name):
            old_name = updated_layer.name

            # Substitute the pattern with an empty string ""
            new_name = re.sub(pattern, "", old_name)

            updated_layer.name = new_name
        # Iterate through the service's sub-layers
        # This prevents adding the "Group/Folder" layer
        # for layer in target_item.layers:
        #     # Check if the sub-layer name matches your filter criteria
        #     if name_filter.lower() in layer.properties.name.lower():
        #         print(f"  [Adding] {layer.properties.name}")
                
        #         # addDataFromPath handles the URL connection
        #         map_obj.addDataFromPath(layer.url)
        #         found_count += 1
        
        # if found_count == 0:
        #     print(f"  No sub-layers matched the filter .")
        # else:
        #     print(f"Successfully added {found_count} layer(s).")
    else:
        print(f"No items found in Portal matching: {search_query}")

# ==========================================
# MAIN EXECUTION
# ==========================================

if __name__ == "__main__":

    # Project Path
    aprx_path = r"C:\\Users\\sameer.bajracharya\\Documents\\ArcGIS\\Projects\\Publish_Maps\\Publish_Maps.aprx"

    # If this returns True, we stop immediately.
    if is_project_locked(aprx_path):
        print("\n" + "="*50)
        print("CRITICAL ERROR: The project file is currently OPEN.")
        print("Please close ArcGIS Pro and run this script again.")
        print("="*50 + "\n")
        sys.exit() # Stop the script

    # Connect to the active portal in ArcGIS Pro
    gis = GIS("pro")

    # This confirms you've connected successfully and prints your username
    print(f"Successfully connected to '{gis.properties.portalHostname}' as '{gis.properties.user.username}'")

    search_text = f" title:Telus Network GN01"
    search_type = "Feature Layer"
    map_name = "Map"
    pattern = r"^mv\\"

    # Open project
    aprx = arcpy.mp.ArcGISProject(aprx_path)

    map_item = aprx.listMaps(map_name)[0]

    # clear Functions
    clear_map(map_item)

    # Add Layers
    add_layers(gis, map_item, search_text, search_type)

    # Save the project
    aprx.save()
    print("\nProject saved and complete.\n")

    del aprx