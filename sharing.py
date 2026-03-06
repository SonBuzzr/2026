import arcpy
from arcgis.gis import GIS
import os
import getpass # For secure password handling

# Define Your Variables ---

# Portal Connection
PORTAL_URL = "https://gis-sandbox.planview.ca/portal" # Your portal URL
PORTAL_USER = "sameer.bajracharya@planview.ca"
# Use getpass to securely prompt for password instead of hardcoding
PORTAL_PASS = getpass.getpass(prompt="Enter password for {}: ".format(PORTAL_USER))

# ArcGIS Pro Project
PROJECT_PATH = r"C:\Users\sameer.bajracharya\Documents\ArcGIS\Projects\PythonPublishLayer\PythonPublishLayer.aprx"
MAP_NAME = "Map" # The exact name of the map in the .aprx

print(f"Logged in as '{PORTAL_USER}'")
# Service Details
SERVICE_NAME = "My_Vector_Tile_Service"
SUMMARY = "This is a vector tile service published with Python."
TAGS = "python, automation, vector, demo"

# Create a file-safe version of the map name (e.g., replace spaces)
safe_map_name = MAP_NAME.replace(" ", "_")

# Temporary file paths now use the map name
SD_DRAFT_PATH = os.path.join(os.getcwd(), f"{safe_map_name}_temp_vectordraft.sddraft")
SD_PATH = os.path.join(os.getcwd(), f"{safe_map_name}_temp_vector.sd")

'''
# Connect to GIS using credentials ---

try:
    print(f"Connecting to {PORTAL_URL} as {PORTAL_USER}...")
    gis = GIS(PORTAL_URL, PORTAL_USER, PORTAL_PASS)
    print("Successfully connected.")
except Exception as e:
    print(f"Failed to connect: {e}")
    exit()
'''

# PVconnecConnect to GIS using ArcGIS Pro's active portal ---
try:
    # This connects to the active portal in your ArcGIS Pro session.
    print("Connecting to the active portal in ArcGIS Pro...")
    gis = GIS("pro")
    print(f"Successfully connected to: {gis.url} as {gis.properties.user.username}")
except Exception as e:
    print("Failed to connect using ArcGIS Pro's active portal.")
    print("Please ensure you are signed into your target ArcGIS Enterprise portal in ArcGIS Pro.")
    print(f"Error details: {e}")
    exit()

# --- Reference the Map ---
print(f"Opening project: {PROJECT_PATH}")
aprx = arcpy.mp.ArcGISProject(PROJECT_PATH)

print(f"Finding map: {MAP_NAME}")
# Find the map by name
map_to_publish_list = aprx.listMaps(MAP_NAME)
if not map_to_publish_list:
    print(f"Error: Map '{MAP_NAME}' not found in project.")
    exit()
map_to_publish = map_to_publish_list[0]

# This is a more robust way to handle inaccessible basemap errors.
print("Checking for and removing basemap layers...")
for lyr in map_to_publish.listLayers():
    if lyr.isBasemapLayer:
        print(f"Removing basemap layer: {lyr.name}")
        map_to_publish.removeLayer(lyr)
# --- END NEW SECTION ---

# --- 4. Create SDDraft ---
print("Creating Service Definition Draft...")
# We use 'HOSTING_SERVER' to publish to the portal's hosted content for 'FEATURE', 'TILE'
# 'FEDERATED_SERVER' for the 'MAP_IMAGE'
# 'STANDALONE_SERVER' for the 'MAP_SERVICE'

# We specify 'VECTOR_TILE' as the service type
sharing_draft = map_to_publish.getWebLayerSharingDraft(
    server_type="HOSTING_SERVER",
    service_type="FEATURE",
    service_name=SERVICE_NAME
)

# Set properties for the service
sharing_draft.summary = SUMMARY
sharing_draft.tags = TAGS
sharing_draft.description = "Published via arcpy and ArcGIS API for Python."

# Create the .sddraft file on disk
sharing_draft.exportToSDDraft(SD_DRAFT_PATH)
print(f"SDDraft created at: {SD_DRAFT_PATH}")

# --- Stage the Service ---
print("Staging service (creating .sd file)...")
# This analyzes the map and packages it into a .sd file
arcpy.StageService_server(SD_DRAFT_PATH, SD_PATH)
print(f".sd file created at: {SD_PATH}")

# --- Upload and Publish ---
try:
    print(f"Uploading {SD_PATH} to portal...")
    # Add the .sd file to your portal content
    sd_item = gis.content.add({}, data=SD_PATH)
    
    print(f"Publishing service: {SERVICE_NAME}...")
    # Publish the .sd item to create the service
    published_item = sd_item.publish()
    
    print(f"Successfully published! New Item ID: {published_item.id}")

    # (Optional) Share the new item
    # published_item.share(groups=['My_GIS_Group'])

except Exception as e:
    print(f"Error during upload or publish: {e}")

finally:
    # --- Clean Up ---
    print("Cleaning up local files...")
    if os.path.exists(SD_DRAFT_PATH):
        os.remove(SD_DRAFT_PATH)
    if os.path.exists(SD_PATH):
        os.remove(SD_PATH)
    print("Done.")
