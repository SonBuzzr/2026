import datetime
import logging
from pathlib import Path
import sys
from arcgis.gis import GIS
import pandas as pd

# Configure enterprise logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def connect_gis() -> GIS:
    """Connect to ArcGIS Pro active portal safely."""
    try:
        gis = GIS("pro")
        logging.info(
            f"Connected to {gis.url} as {getattr(gis.users.me, 'username', 'Active User')}"
        )
        return gis
    except Exception as e:
        logging.error(
            f"Failed to authenticate using ArcGIS Pro connection: {e}"
        )
        raise


def fetch_portal_items(
    gis: GIS, query: str, max_items: int = 500
) -> list[dict]:
    """Search portal items and extract metadata safely."""
    logging.info(f"Searching items matching query: '{query}'...")
    try:
        items = gis.content.search(
            query=query,
            max_items=max_items,
            sort_field="modified",
            sort_order="desc",
        )
    except Exception as e:
        logging.error(f"Search query execution failed: {e}")
        raise

    logging.info(f"Retrieved {len(items)} items. Extracting metadata...")
    data = []

    for item in items:
        try:
            mod = getattr(item, "modified", None)
            mod_date = (
                datetime.datetime.fromtimestamp(
                    mod / 1000.0, tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S")
                if mod
                else "N/A"
            )

            raw_url = getattr(item, "url", None)
            item_url = (
                raw_url
                if raw_url
                else f"{gis.url.rstrip('/')}/home/item.html?id={item.id}"
            )

            data.append(
                {
                    "Title": getattr(item, "title", "Untitled"),
                    "Item ID": getattr(item, "id", "Unknown"),
                    "Item URL": item_url,
                    "Item Type": getattr(item, "type", "Unknown"),
                    "Date Modified": mod_date,
                }
            )
        except Exception as item_err:
            logging.warning(
                f"Skipping item ID {getattr(item, 'id', 'N/A')} due to parsing error: {item_err}"
            )

    return data


def export_to_excel(data: list[dict], output_path: Path) -> None:
    """Export list of dictionaries to Excel with path verification."""
    if not data:
        logging.warning("No items found. Skipping file creation.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        logging.info(
            f"Successfully exported {len(df)} records to '{output_path.resolve()}'"
        )
    except PermissionError:
        logging.error(
            f"Permission denied. Close '{output_path.name}' if it is open in Excel."
        )
        raise
    except Exception as e:
        logging.error(f"Failed to save Excel workbook: {e}")
        raise


def main():
    SEARCH_QUERY = "Tiles Views GN02"
    MAX_ITEMS = 500

    # Locate the script directory dynamically
    try:
        script_dir = Path(__file__).resolve().parent
    except NameError:
        # Fallback for interactive environments (e.g., Jupyter Notebooks inside ArcGIS Pro)
        script_dir = Path.cwd()

    output_file = script_dir / "agol_gis_items.xlsx"

    try:
        gis = connect_gis()
        results = fetch_portal_items(
            gis, query=SEARCH_QUERY, max_items=MAX_ITEMS
        )
        export_to_excel(results, output_file)
    except Exception as fatal_err:
        logging.critical(
            f"Pipeline terminated prematurely: {fatal_err}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()