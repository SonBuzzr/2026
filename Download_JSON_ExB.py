import json
from pathlib import Path
from arcgis.gis import GIS

def download_config_using_pro_login(item_id):
    try:
        # 1. Dynamically find the folder where this .py file is located
        script_directory = Path(__file__).resolve().parent
        output_path = script_directory / "config.json"

        # 2. Connect using ArcGIS Pro's active session
        print("Authenticating via active ArcGIS Pro session...")
        gis = GIS("pro")
        
        # 3. Get the Experience Builder Item
        exb_item = gis.content.get(item_id)
        
        if exb_item is None:
            print(f"Error: Could not find Item ID {item_id}.")
            return

        print(f"Downloading config for: {exb_item.title}")

        # 4. Extract and save the config data
        config_data = exb_item.get_data()
        
        if config_data is None:
            print("Error: The item returned no data. Check if it is a valid Experience Builder app.")
            return
        
        # 5. Write the file to the script directory
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
            
        print(f"Success! File saved at: {output_path}")

    except Exception as e:
        print(f"An error occurred: {e}")

# Your Item ID
MY_APP_ID = "ef77009085494027a59c503d47b483ec"

if __name__ == "__main__":
    download_config_using_pro_login(MY_APP_ID)