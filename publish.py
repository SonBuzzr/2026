# Open the ArcGIS Project, read all the maps, select the map. List all the geodatabase and select the particular gdb
import os
import arcpy

def list_feature_classes(geodatabase_path: str) -> list:
    """
    Lists all feature classes within a given geodatabase. This function
    remains as it is self-contained and efficient.
    """
    if not arcpy.Exists(geodatabase_path):
        print(f"Error: Geodatabase not found at '{geodatabase_path}'")
        return []

    original_workspace = arcpy.env.workspace
    try:
        arcpy.env.workspace = geodatabase_path
        feature_classes = arcpy.ListFeatureClasses()
        return feature_classes if feature_classes else []
    except Exception as e:
        print(f"An error occurred while listing feature classes: {e}")
        return []
    finally:
        # Crucially, restore the original workspace
        arcpy.env.workspace = original_workspace

# --- Main execution block ---
if __name__ == "__main__":
    project_path = r"C:\Users\sameer.bajracharya\Documents\ArcGIS\Projects\PythonPublishLayer\PythonPublishLayer.aprx"
    target_map_name = "Map"
    target_gdb_name = "PythonPublishLayer.gdb"

    print(f"--- Analyzing ArcGIS Pro Project ---\nPath: {project_path}\n")

    # --- 1. Open Project and Read All Info in One Pass ---
    aprx = None
    all_map_names = []
    selected_map = None
    found_gdbs = []

    try:
        if not os.path.exists(project_path):
            raise FileNotFoundError(f"Project file not found at '{project_path}'")

        aprx = arcpy.mp.ArcGISProject(project_path)

        # Get all map objects and names simultaneously
        all_maps = aprx.listMaps()
        all_map_names = [m.name for m in all_maps]
        
        # Find the target map object from the list we just created.
        # This is more efficient than re-opening the project.
        selected_map = next((m for m in all_maps if m.name == target_map_name), None)

        # Get all geodatabase paths
        found_gdbs = [db['databasePath'] for db in aprx.databases]

    except Exception as e:
        print(f"An error occurred during project analysis: {e}")
    finally:
        if aprx:
            print("Closing project file and releasing lock.")
            del aprx

    # --- 2. Process the Gathered Information ---
    # The project file is now closed, and we work with the data in memory.
    
    print("\n--- Available Maps in Project ---")
    if all_map_names:
        for name in all_map_names:
            print(f"  - {name}")
    else:
        print("  No maps found.")

    print("-" * 20)

    print(f"Processing target map: '{target_map_name}'...")
    if selected_map:
        print(f"  -> Success: Selected map '{selected_map.name}'")
        layers = selected_map.listLayers()
        if layers:
            print(f"     Found {len(layers)} layer(s):")
            for layer in layers:
                print(f"       - {layer.name}")
        else:
            print("     This map contains no layers.")
    else:
        print(f"  -> WARNING: Map '{target_map_name}' not found.")

    print("-" * 20)

    # --- 3. Select Geodatabase (No changes to this logic) ---
    selected_gdb = None
    if not found_gdbs:
        print("No geodatabases were found.")
    elif len(found_gdbs) == 1:
        selected_gdb = found_gdbs[0]
        print(f"One geodatabase found. Automatically selected:\n  -> {selected_gdb}")
    else:
        print(f"Found {len(found_gdbs)} geodatabases. Searching for '{target_gdb_name}'...")
        selected_gdb = next((gdb for gdb in found_gdbs if os.path.basename(gdb) == target_gdb_name), None)
        if selected_gdb:
            print(f"  -> Match found and selected:\n     {selected_gdb}")
        else:
            print(f"  -> WARNING: Could not find '{target_gdb_name}'.")
    
    # --- 4. List Feature Classes (No changes to this logic) ---
    if selected_gdb:
        print("-" * 20)
        print(f"Listing contents of {os.path.basename(selected_gdb)}:")
        fcs_in_gdb = list_feature_classes(selected_gdb)
        if fcs_in_gdb:
            print(f"  Found {len(fcs_in_gdb)} feature class(es):")
            for fc_name in fcs_in_gdb:
                print(f"    - {fc_name}")
        else:
            print("  No feature classes were found in this geodatabase.")
    else:
        print("\nHalting further steps because no target geodatabase was selected.")