from arcgis.gis import GIS
from arcgis.features import FeatureLayer
import json

# GLOBAL VARIABLES & CONFIGURATION
LAC_FEATURE_ID = "309bb51e0c0740c0b38488046a844a2d"
UTILITY = "VIDEOTRON"
ARCGIS_CONNECTION = "home"

# Update the LAC areas separated by comma to create webmap
LAC_AREAS = ["GW01"]

MIN_SCALE = 1000000 # Cities
MAX_SCALE = 10000 # Streets

# A Simple Fill Symbol for a transparent polygon 
BLUE_OUTLINE = {
    "type": "esriSFS",
    "style": "esriSFSSolid",
    "color": [255, 255, 255, 0], 
    "outline": {
        "type": "esriSLS",
        "style": "esriSLSSolid",
        "color": [2, 135, 252, 190],  
        "width": 1                  
    }
}

POLYGON_RENDERER = {
    "type": "simple",
    "symbol": BLUE_OUTLINE,
    "label": "Outline",
    "description": "Custom Style: No fill, outline"
}

# Function to Search AGOL
def Search_AGOL(gis_conn, Search_Query, Feature_Type):
    try:
        Exact_Title = Search_Query.replace(" ", "_")
        
        Search_Text = f"title:'{Exact_Title}' AND type:'{Feature_Type}'"
        Search_Result = gis_conn.content.search(query=Search_Text, max_items=1)
        
        if not Search_Result:
            print(f"[-] ! {Search_Query} ({Feature_Type}) ! -> Layer not found in AGOL.\n")
            return None
        
        # We extract the single item here
        Searched_Item = Search_Result[0]
        print(f" Searching for '{Search_Query}' - ({Feature_Type}) :   \n   Found: -- {Searched_Item.title} --\n")
        return Searched_Item
    
    except Exception as e:
        print (f" \nError Searching Layers: '{e}'")
        return None

# Function to format the title text   
def Format_Title(title_text):
    text_part = title_text.split('_')
    formatted = []

    for i, part in enumerate(text_part):
        # If it's the last part and looks like a code (letters + numbers)
        if i == len(text_part) - 1:
            formatted.append(part.upper())
        else:
            formatted.append(part.capitalize())
            
    return " ".join(formatted)

# Function to Get all folders for the current user
def Get_Or_Create_Folder(gis_conn, folder_name):
    """Retrieves an actual Folder object using the folders manager."""
    user = gis_conn.users.me
     
    # Note: user.folders returns dicts, but we use the title to find the right one
    all_folders_dicts = user.folders
    
    target_folder_id = None
    for f in all_folders_dicts:
        if f['title'].lower() == folder_name.lower():
            target_folder_id = f['id']
            break
            
    if target_folder_id:
        # 2. Use the ID to get the actual Folder OBJECT
        print(f"\n [*] Found existing folder: {folder_name}")
        return gis_conn.content.folders.get(target_folder_id)
    
    # If not found, create it (create returns the Folder object automatically)
    print(f"\n [*] Creating new folder: {folder_name}")
    return gis_conn.content.folders.create(folder_name)

# Function to create webmap using the search result layers.
def Create_WebMap(gis_conn, FL, GENERAL_LANDBASE, FEATURE_NETWORK_SEARCH, TILE_NETWORK_SEARCH, TILE_LANDBASE_SEARCH, MAP_IMAGE_SEARCH, query_string):
    LAC_CODE = query_string.split()[1]

    Where_Clause = f"UPPER(LAC) = '{LAC_CODE.upper()}'"
    LAC_Query_Result = FL.query(where=Where_Clause, return_extent_only=True, out_sr=102100)

    Target_Extent = LAC_Query_Result['extent']

    Base_URL = FL.url
    Layer_URL = Base_URL if Base_URL.split('/')[-1].isdigit() else f"{Base_URL}/0"

    webmap_data = {
        "operationalLayers": [{
            "type": "ArcGISFeatureLayer",
            "url": Layer_URL,
            "itemId": LAC_FEATURE_ID,
            "title": "Lac Area",
            "visibility": True,
            "opacity": 1,
            "popupEnabled": False,
            "showPopup": False,
            "popupInfo": None, 
            "capabilities": "Query",    
            "showLabels": False,
            "layerDefinition": {                
                "definitionExpression": Where_Clause,
                "drawingInfo": {
                    "renderer": POLYGON_RENDERER
                }
            }
        }],
        "baseMap": {
            "baseMapLayers": [{
                "id": "defaultBasemap",
                "layerType": "ArcGISTiledMapServiceLayer",
                "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer"
            }],
            "title": "Topographic"
        },
        "initialState": {
            "viewpoint": {
                "targetGeometry": Target_Extent
            }
        },
        "extent": Target_Extent,
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "version": "2.29"
    }

    if TILE_LANDBASE_SEARCH:
        
        Landbase_item = TILE_LANDBASE_SEARCH

        webmap_data["baseMap"] = {
            "baseMapLayers": [
                {
                    "id": f"basemap_{Landbase_item.id}",
                    "layerType": "VectorTileLayer",
                    "type": "VectorTileLayer",
                    "url": Landbase_item.url,
                    "itemId": Landbase_item.id,
                    "title": Format_Title(Landbase_item.title),
                    "visibility": True,
                    "opacity": 1,
                    "maxScale": 0
                }
            ],
            "title": Format_Title(Landbase_item.title)
        }
        print("   [+] Successfully set the Vector Tile service as the Web Map basemap.\n")
    else:
        print(f"   [!] Warning: Could not find '{UTILITY}' Vector Tile Service. Using fallback Topographic basemap.\n")    

    if GENERAL_LANDBASE:
        General_layer = {
            "id": f"MapService_{GENERAL_LANDBASE.id}",
            "layerType": "ArcGISMapServiceLayer",
            "url": GENERAL_LANDBASE.url,
            "itemId": GENERAL_LANDBASE.id,
            "title": Format_Title(GENERAL_LANDBASE.title),
            "visibility": True,
            "opacity": 1,
            "maxScale": 50000
        }
        webmap_data["operationalLayers"].append(General_layer)
        print(f"   [+] Successfully added Map Image Layer: '{GENERAL_LANDBASE.title}'")
    
    # Add Map Image Layer (Dynamic Map Service)
    if MAP_IMAGE_SEARCH:
        map_layer = {
            "id": f"MapService_{MAP_IMAGE_SEARCH.id}",
            "layerType": "ArcGISMapServiceLayer",
            "url": MAP_IMAGE_SEARCH.url,
            "itemId": MAP_IMAGE_SEARCH.id,
            "title": Format_Title(MAP_IMAGE_SEARCH.title),
            "visibility": True,
            "opacity": 1
        }
        webmap_data["operationalLayers"].append(map_layer)
        print(f"   [+] Successfully added Map Image Layer: '{MAP_IMAGE_SEARCH.title}'")
        

    # Add Feature Layer (Enable this for loading feature layers)
    # Add Feature Layer as a Group
    
    # if FEATURE_NETWORK_SEARCH:
    #     Feature_Network_item = FEATURE_NETWORK_SEARCH

    #     # 1. Construct the Parent Group Layer
    #     group_layer = {
    #         "id": f"GroupLayer_{Feature_Network_item.id}",
    #         "layerType": "GroupLayer",
    #         "title": Format_Title(Feature_Network_item.title),
    #         "visibility": True,
    #         "opacity": 1,
    #         "itemId": Feature_Network_item.id, 
    #         "layers": [] 
    #     }

    #     # 2. Loop through all sublayers IN REVERSE ORDER to fix the stacking
    #     for sublayer in reversed(Feature_Network_item.layers):
    #         sublayer_index = sublayer.properties.get('id', 0)
    #         sublayer_name = sublayer.properties.get('name', f"Layer_{sublayer_index}")

    #         child_layer = {
    #             "id": f"FeatureLayer_{Feature_Network_item.id}_{sublayer_index}",
    #             "layerType": "ArcGISFeatureLayer",
    #             "url": sublayer.url, 
    #             "title": sublayer_name, 
    #             "visibility": True,
    #             "opacity": 1
    #         }

    #         # Append the child layer to the Group Layer
    #         group_layer["layers"].append(child_layer)

    #     # Add the entire Group Layer to the Web Map's operational layers
    #     if "operationalLayers" not in webmap_data:
    #         webmap_data["operationalLayers"] = []
            
    #     webmap_data["operationalLayers"].append(group_layer)
        
    #     print(f"   [+] Successfully added '{Feature_Network_item.title}' as a Group Layer.")

    # else:
    #     print(f"   [!] Warning: Could not find '{UTILITY}' Feature Service.")

    # Add Tile Layer 
    if  TILE_NETWORK_SEARCH:
        Network_item = TILE_NETWORK_SEARCH

        Network_Tile_Layer = {
            "id": f"VectorTile_{Network_item.id}",
            "layerType": "VectorTileLayer",
            "type": "VectorTileLayer",
            "url": Network_item.url,
            "itemId": Network_item.id,
            "title": Format_Title(Network_item.title),
            "visibility": True,
            "opacity": 1,
            "maxScale": MAX_SCALE
        }

        # Append it to the operational layers list so it sits above the basemap
        webmap_data["operationalLayers"].append(Network_Tile_Layer)
        print(f"   [+] Successfully added '{Network_item.title}' as an operational layer.")

    else:
        print(f"   [!] Warning: Could not find '{UTILITY}' Vector Tile Service.")

    target_folder = Get_Or_Create_Folder(gis_conn, "Web Maps")

    # Create and Save the Web Map Item
    item_properties = {
        "title": f"{query_string} - {LAC_CODE}",
        "type": "Web Map",
        "snippet": f"Filter applied: {LAC_CODE}. Custom Vector Tile Basemap applied.", 
        "tags": ["LAC", "Automation", "Basemap", UTILITY],
        "text": json.dumps(webmap_data) 
    }

    new_item = target_folder.add(item_properties)

    print(f"\n   [+] Successfully created Web Map for {UTILITY} {LAC_CODE}!")
    # print(f"   [+] Item ID: {new_item.id}")
    # print(f"   [+] URL: {new_item.homepage}")


# Main Execution Block
if __name__ == "__main__":
    try:
        gis = GIS(ARCGIS_CONNECTION)
        print(f"Successfully connected to {gis.properties.portalName} as {gis.properties.user.username}")

        print("\n--- Searching for Layers ---")
        LAC_ITEM = gis.content.get(LAC_FEATURE_ID)

        if LAC_ITEM is None:
            print(f"Error: Item ID'{LAC_FEATURE_ID}' could not be found...")
        else:
            FL = FeatureLayer.fromitem(LAC_ITEM, layer_id=0)
            print(f"Feature Layer Accessed: {FL.properties.name}, URL: {FL.url}")
        
            SEARCH_ALL_LAC = [f"{UTILITY} {lac}" for lac in LAC_AREAS]

            for query_string in SEARCH_ALL_LAC:
                SEARCH_UTILITY = query_string.split(' ')[0]
                SEARCH_LAC = query_string.split(' ')[1]
                print(f"\n--- Processing: {SEARCH_UTILITY} Network {SEARCH_LAC} ---")

                try:
                    # Searching for General Landbase
                    GENERAL_LANDBASE = Search_AGOL(gis, f"GENLANDBASEON LANDBASE {SEARCH_LAC}", "Map Service")

                    # Searching for Map Images
                    MAP_IMAGE_SEARCH = Search_AGOL(gis, f"{SEARCH_UTILITY} Network {SEARCH_LAC}", "Map Service")

                    # Searching for Network feature and tile layers                    
                    FEATURE_NETWORK_SEARCH = Search_AGOL(gis, f"{SEARCH_UTILITY} Network {SEARCH_LAC}", "Feature Service")
                    TILE_NETWORK_SEARCH = Search_AGOL(gis, f"{SEARCH_UTILITY} Network {SEARCH_LAC} VTPK", "Vector Tile Service")

                    # Searching for Landbase feature and tile layers
                    FEATURE_LANDBASE_SEARCH = Search_AGOL(gis, f"{SEARCH_UTILITY} Landbase {SEARCH_LAC}", "Feature Service")
                    TILE_LANDBASE_SEARCH = Search_AGOL(gis, f"{SEARCH_UTILITY} Landbase {SEARCH_LAC} VTPK", "Vector Tile Service")

                    # Calling function to create webmap
                    Create_WebMap(
                        gis, 
                        FL, 
                        GENERAL_LANDBASE,
                        FEATURE_NETWORK_SEARCH, 
                        TILE_NETWORK_SEARCH, 
                        TILE_LANDBASE_SEARCH, 
                        MAP_IMAGE_SEARCH,
                        query_string)

                except Exception as e:
                    print(f"\n One of the Feature and Tile layers not found: {e}")

    except Exception as e:
        print(f"An error occurred while log in: {e}")