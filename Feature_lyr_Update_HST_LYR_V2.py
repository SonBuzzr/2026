"""
ArcGIS Web Map Automated Layer Manager
--------------------------------------
Production script to search AGOL/Enterprise for Web Maps, Hosted Feature Layers,
Network Tile Layers, Landbase Tile Layers, and Optional Sublayers.

Workflow:
1. Cleans up existing operational layers from the Web Map EXCEPT configured keywords
   (default: Territory, General Landbase, General LLD).
2. Updates `baseMap` using Landbase Tile Layer (basemap title: "Landbase", 
   layer title left as default, visibility: False).
3. Searches AGOL items:
   - Main Feature Layer via `hosted_feature_templates`
   - Optional Feature Layer via `optional_feature_templates`
4. Extracts multiple sublayers specified in `optional_sublayer_names`.
5. Sets the Main Network Feature Layer top-level `minScale` to "Streets" (10000)
   while leaving all sublayer configurations untouched.
6. Injects Landbase Tile Layer -> Network Tile Layer -> Optional Sublayers -> 
   Main Network Feature Layer into `operationalLayers` in visual stacking order.
"""

import json
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS, Item

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AGOLWebMapUpdater")


# =============================================================================
# CENTRALIZED CONFIGURATION (SINGLE SOURCE OF TRUTH)
# =============================================================================
@dataclass
class UpdaterConfig:
    """Central configuration for environments, layer search templates, and types."""
    
    # Execution Settings
    utility: str = "ATCO_GAS"         # webmap naming
    utility_network: str = "ATCO"     # network naming
    utility_landbase: str = "ATCO"    # landbase naming

    webmap_owner: Union[str, List[str]] = field(
        default_factory=lambda: ["miguel.vargas@planview.ca", "migration_tool"]
    )
    lac_areas: List[str] = field(default_factory=lambda: ["EastAB", "SouthAB", "NorthAB", "CapitalNorth", "NorthCentral",
                                                            "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"])
    # ["EastAB", "SouthAB", "NorthAB", "CapitalNorth", "NorthCentral", "Northeast",
    #     "Southwest", "CapitalSouth", "Edmonton", "Central", "Northwest", "WestAB"]

    target_position: int = 0  # 0-based index (0 = top/start of operationalLayers)
    gis_connection: str = "home"
    dry_run: bool = False  # Set to True to preview JSON mutations without saving

    # Label & Scale Settings
    show_network_labels: bool = False  # Set to False to disable labels on all network sublayers
    main_network_min_scale: float = 10000  # Min scale threshold

    # Feature Type / Category Search Definitions
    webmap_category: str = "Web Map"
    hosted_feature_category: str = "Hosted Feature Layer"
    tile_layer_category: str = "Vector Tile Service"

    # Search Title Templates ({utility}, {utility_network}, {utility_landbase}, and {lac} format automatically)
    webmap_title_template: str = "{utility} {lac} Hosted WebMap"

    hosted_feature_templates: List[str] = field(default_factory=lambda: [
        "{utility_network}_NETWORK_{lac}_HOSTED",
        "{utility_network} NETWORK {lac} HOSTED",
        "{utility}_{lac}_HOSTED"
    ])

    # List of sublayer names to extract (supports two or more sublayers)
    optional_sublayer_names: List[str] = field(
        default_factory=lambda: ["CAPITAL PROJECT TRANSMISSION", "CAPITAL PROJECT DISTRIBUTION"]
    )
    
    optional_feature_templates: List[str] = field(default_factory=lambda: [
        "{utility_network}_NETWORK__{lac}",
        "{utility_network}_{lac}_UGNOTES"
    ])

    network_tile_templates: List[str] = field(default_factory=lambda: [
        "{utility_network}_NETWORK_{lac}_HOSTED",
        "{utility_network} NETWORK {lac} HOSTED",
        "{utility_network}_{lac}_TILE"
    ])

    landbase_tile_templates: List[str] = field(default_factory=lambda: [
        "{utility_landbase}_LANDBASE_{lac}_HOSTED",
        "{utility_landbase} LANDBASE {lac} HOSTED",
        "{utility_landbase} LANDBASE {lac} TILE"
    ])

    # Operational Layers to Preserve During Cleanup (case-insensitive)
    keep_layer_keywords: List[str] = field(default_factory=lambda: [
        "territory", 
        "general landbase", 
        "general lld"
    ])


# =============================================================================
# WORKFLOW MANAGER
# =============================================================================
class WebMapUpdater:
    def __init__(self, config: UpdaterConfig):
        self.config = config
        self.gis = GIS(config.gis_connection)
        logger.info("Connected to Portal '%s' as user '%s'", 
                    self.gis.properties.portalName, 
                    self.gis.properties.user.username)

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Strips spaces, underscores, and special characters for flexible sublayer matching."""
        return re.sub(r"[\s_]+", "", str(name)).lower()

    def _build_owner_clause(self) -> str:
        """Constructs a Lucene owner filter supporting single or multiple usernames."""
        owners = self.config.webmap_owner
        if not owners:
            return ""

        if isinstance(owners, str):
            owners = [owners]

        owners = [o.strip() for o in owners if o.strip()]
        if not owners:
            return ""

        if len(owners) == 1:
            return f' AND owner:"{owners[0]}"'
        
        owner_terms = " OR ".join([f'owner:"{o}"' for o in owners])
        return f' AND ({owner_terms})'

    def search_item(self, title: str, category: str) -> Optional[Item]:
        """
        Searches AGOL/Portal using flexible item types, title variants (underscores/spaces),
        and owner fallbacks across multiple configured users.
        """
        cat_lower = category.lower()
        if cat_lower in ["hosted feature layer", "feature service", "feature layer"]:
            type_filter = '(type:"Feature Service" OR type:"Feature Layer")'
        elif cat_lower in ["tile layer", "vector tile service", "vector tile layer", "tile service"]:
            type_filter = '(type:"Vector Tile Service" OR type:"Vector Tile Layer" OR type:"Tile Service")'
        elif cat_lower == "web map":
            type_filter = 'type:"Web Map"'
        else:
            type_filter = f'type:"{category}"'

        title_variants = [title, title.replace("_", " ")]
        owner_clause = self._build_owner_clause()

        for t_var in title_variants:
            q_owner = f'title:"{t_var}" AND {type_filter}{owner_clause}'
            results = self.gis.content.search(query=q_owner, max_items=10)

            # Fallback query without owner restriction if not found under specified users
            if not results and owner_clause:
                q_no_owner = f'title:"{t_var}" AND {type_filter}'
                results = self.gis.content.search(query=q_no_owner, max_items=10)

            if results:
                for item in results:
                    it_clean = item.title.strip().lower()
                    if it_clean in [title.strip().lower(), title.replace("_", " ").strip().lower()]:
                        logger.info("Found Match: '%s' (ID: %s | Owner: %s | Type: %s)", 
                                    item.title, item.id, item.owner, item.type)
                        return item

        return None

    def search_candidate_titles(self, templates: List[str], lac: str, category: str) -> Optional[Item]:
        """Formats title templates dynamically with all utility variables and queries AGOL for candidates."""
        candidate_titles = []
        for tmpl in templates:
            try:
                formatted_title = tmpl.format(
                    utility=self.config.utility,
                    utility_network=self.config.utility_network,
                    utility_landbase=self.config.utility_landbase,
                    lac=lac
                )
                candidate_titles.append(formatted_title)
            except KeyError as e:
                logger.error("Failed to format template '%s': missing key %s", tmpl, e)

        for title in candidate_titles:
            found = self.search_item(title, category)
            if found:
                return found
        return None

    @staticmethod
    def extract_sublayers(hosted_item: Item) -> List[Any]:
        """Extracts sublayer objects from a Hosted Feature Layer item with REST fallback."""
        sublayers: List[Any] = []
        
        # Method 1: FeatureLayerCollection SDK
        try:
            flc = FeatureLayerCollection.fromitem(hosted_item)
            if flc and getattr(flc, "layers", None):
                sublayers = list(flc.layers)
        except Exception as e:
            logger.debug("FeatureLayerCollection.fromitem failed: %s", e)

        # Method 2: Item layers property SDK
        if not sublayers and getattr(hosted_item, "layers", None):
            sublayers = list(hosted_item.layers)

        # Method 3: Direct REST endpoint inspection fallback
        if not sublayers and getattr(hosted_item, "url", None):
            try:
                rest_url = f"{hosted_item.url}?f=json"
                req = urllib.request.Request(rest_url, headers={"User-Agent": "AGOLWebMapUpdater"})
                with urllib.request.urlopen(req, timeout=15) as response:
                    service_data = json.loads(response.read().decode("utf-8"))
                    if "layers" in service_data and service_data["layers"]:
                        sublayers = service_data["layers"]
                        logger.info("Extracted %d sublayers via REST endpoint fallback for '%s'", 
                                    len(sublayers), hosted_item.title)
            except Exception as e:
                logger.warning("REST API fallback failed for item '%s': %s", hosted_item.title, e)

        return sublayers

    @staticmethod
    def _get_sublayer_name(sub: Any) -> str:
        """Helper to extract name from SDK object or dict."""
        if isinstance(sub, dict):
            return sub.get("name", "")
        if hasattr(sub, "properties"):
            return sub.properties.get("name", getattr(sub, "name", ""))
        return getattr(sub, "name", "")

    @staticmethod
    def _get_sublayer_id(sub: Any) -> int:
        """Helper to extract layer ID from SDK object or dict."""
        if isinstance(sub, dict):
            return sub.get("id", 0)
        if hasattr(sub, "properties"):
            return sub.properties.get("id", getattr(sub, "id", 0))
        return getattr(sub, "id", 0)

    @staticmethod
    def _get_sublayer_url(sub: Any, hosted_item: Item, sub_id: int) -> str:
        """Helper to extract layer URL from SDK object or dict."""
        if isinstance(sub, dict):
            return f"{hosted_item.url}/{sub_id}"
        return getattr(sub, "url", f"{hosted_item.url}/{sub_id}")

    def build_hosted_layer_json(
        self, 
        hosted_item: Item, 
        sublayer_name_filters: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Constructs JSON definition for Hosted Feature Layers with labels explicitly set.
        If `sublayer_name_filters` is specified, extracts ONLY matching sublayers from the item.
        """
        sublayers = self.extract_sublayers(hosted_item)

        discovered_names = [self._get_sublayer_name(s) for s in sublayers]
        logger.info("Discovered sublayers in '%s': %s", hosted_item.title, discovered_names)

        # Handle Sublayer Filtering for multiple target names
        if sublayer_name_filters:
            extracted_layers: List[Dict[str, Any]] = []

            for filter_name in sublayer_name_filters:
                filter_norm = self._normalize_name(filter_name)
                
                matching_sublayers = []
                for sub in sublayers:
                    sub_name_norm = self._normalize_name(self._get_sublayer_name(sub))
                    if sub_name_norm == filter_norm or filter_norm in sub_name_norm or sub_name_norm in filter_norm:
                        matching_sublayers.append(sub)

                if matching_sublayers:
                    target_sub = matching_sublayers[0]
                    sub_id = self._get_sublayer_id(target_sub)
                    sub_title = self._get_sublayer_name(target_sub) or filter_name
                    sub_url = self._get_sublayer_url(target_sub, hosted_item, sub_id)

                    extracted_layers.append({
                        "id": f"FeatureLayer_{hosted_item.id}_{sub_id}",
                        "title": sub_title,
                        "url": sub_url,
                        "itemId": hosted_item.id,
                        "layerType": "ArcGISFeatureLayer",
                        "visibility": True,
                        "opacity": 1,
                        "showLabels": self.config.show_network_labels
                    })
                    logger.info("Matched Optional Sublayer '%s' (ID: %d) from item '%s'", 
                                sub_title, sub_id, hosted_item.title)
                else:
                    logger.warning(
                        "Sublayer matching '%s' (normalized: '%s') was NOT found in item '%s'. Available names: %s", 
                        filter_name, filter_norm, hosted_item.title, discovered_names
                    )

            return extracted_layers, len(extracted_layers)

        # Standard Multi-sublayer GroupLayer Build (for Main Hosted Feature Layer)
        if len(sublayers) > 1:
            child_layers = []
            for sub in reversed(sublayers):
                sub_id = self._get_sublayer_id(sub)
                sub_title = self._get_sublayer_name(sub) or f"Layer {sub_id}"
                sub_url = self._get_sublayer_url(sub, hosted_item, sub_id)

                child_layers.append({
                    "id": f"FeatureLayer_{hosted_item.id}_{sub_id}",
                    "title": sub_title,
                    "url": sub_url,
                    "itemId": hosted_item.id,
                    "layerType": "ArcGISFeatureLayer",
                    "visibility": True,
                    "opacity": 1,
                    "showLabels": self.config.show_network_labels
                })

            group_json = {
                "id": f"GroupLayer_{hosted_item.id[:8]}",
                "title": hosted_item.title,
                "layerType": "GroupLayer",
                "itemId": hosted_item.id,
                "visibility": True,
                "opacity": 1,
                "layers": child_layers
            }
            return [group_json], len(child_layers)

        # Standard Single-sublayer Build
        sub_url = hosted_item.url
        if sublayers:
            sub_id = self._get_sublayer_id(sublayers[0])
            sub_url = self._get_sublayer_url(sublayers[0], hosted_item, sub_id)

        single_json = {
            "id": f"{hosted_item.title}_{hosted_item.id[:8]}",
            "title": hosted_item.title,
            "url": sub_url,
            "itemId": hosted_item.id,
            "layerType": "ArcGISFeatureLayer",
            "visibility": True,
            "opacity": 1,
            "showLabels": self.config.show_network_labels
        }
        return [single_json], 1

    @staticmethod
    def build_tile_layer_json(tile_item: Item) -> Dict[str, Any]:
        """Constructs Web Map JSON definition for Vector and Raster Tile Layers."""
        item_type = getattr(tile_item, "type", "")
        is_vector = "Vector" in item_type or "VectorTile" in getattr(tile_item, "typeKeywords", [])
        layer_type = "VectorTileLayer" if is_vector else "ArcGISTiledMapServiceLayer"

        return {
            "id": f"VectorTile_{tile_item.id[:8]}" if is_vector else f"Tile_{tile_item.id[:8]}",
            "title": tile_item.title,
            "url": tile_item.url,
            "itemId": tile_item.id,
            "layerType": layer_type,
            "type": layer_type,
            "visibility": True,
            "opacity": 1
        }

    def cleanup_existing_layers(self, webmap_data: Dict[str, Any]) -> bool:
        """Deletes all operational layers EXCEPT those matching keep_layer_keywords."""
        if "operationalLayers" not in webmap_data:
            return False

        original_layers = webmap_data["operationalLayers"]
        retained_layers: List[Dict[str, Any]] = []
        deleted_count = 0

        keep_keywords = [kw.lower() for kw in self.config.keep_layer_keywords]

        for layer in original_layers:
            title = (layer.get("title") or layer.get("id") or "").lower()

            if any(kw in title for kw in keep_keywords):
                retained_layers.append(layer)
                logger.info("Retained Operational Layer : '%s' [%s]", 
                            layer.get("title") or layer.get("id"), 
                            layer.get("layerType", "Layer"))
            else:
                deleted_count += 1
                logger.info("Deleted Operational Layer  : '%s' [%s]", 
                            layer.get("title") or layer.get("id"), 
                            layer.get("layerType", "Layer"))

        webmap_data["operationalLayers"] = retained_layers
        return deleted_count > 0

    def update_basemap_with_landbase(self, webmap_data: Dict[str, Any], landbase_tile_item: Optional[Item]) -> bool:
        """Sets baseMap title to 'Landbase' using Landbase Tile Layer with visibility set to False."""
        if not landbase_tile_item:
            logger.warning("Landbase Tile Layer not found; basemap remains unchanged.")
            return False

        lb_basemap_json = self.build_tile_layer_json(landbase_tile_item)
        lb_basemap_json["visibility"] = False

        webmap_data["baseMap"] = {
            "baseMapLayers": [lb_basemap_json],
            "title": "Landbase"
        }

        logger.info("Updated Web Map Basemap title to 'Landbase' (layer title: '%s', visibility: False)", 
                    lb_basemap_json.get("title"))
        return True

    def add_layers_to_webmap(
        self, 
        webmap_data: Dict[str, Any], 
        hosted_item: Optional[Item], 
        network_tile_item: Optional[Item],
        landbase_tile_item: Optional[Item] = None,
        optional_hosted_item: Optional[Item] = None
    ) -> bool:
        """
        Injects Landbase Tile, Network Tile, Optional Sublayers,
        and Main Hosted Feature Layer sequentially into webmap operationalLayers in visual stacking order.
        """
        if "operationalLayers" not in webmap_data:
            webmap_data["operationalLayers"] = []

        layers: List[Dict[str, Any]] = webmap_data["operationalLayers"]
        existing_urls: Set[str] = {l["url"] for l in layers if "url" in l and l["url"]}
        existing_item_ids: Set[str] = {l["itemId"] for l in layers if "itemId" in l}
        modified = False
        base_idx = max(0, self.config.target_position)

        def is_layer_in_map(layer_dict: Dict[str, Any]) -> bool:
            """Checks layer uniqueness by URL or itemId."""
            if "url" in layer_dict and layer_dict["url"]:
                return layer_dict["url"] in existing_urls
            if "itemId" in layer_dict and layer_dict["itemId"]:
                return layer_dict["itemId"] in existing_item_ids
            return False

        def track_layer(layer_dict: Dict[str, Any]):
            if "url" in layer_dict and layer_dict["url"]:
                existing_urls.add(layer_dict["url"])
            if "itemId" in layer_dict and layer_dict["itemId"]:
                existing_item_ids.add(layer_dict["itemId"])

        # 1. Landbase Tile Layer
        if landbase_tile_item:
            lb_json = self.build_tile_layer_json(landbase_tile_item)
            if is_layer_in_map(lb_json):
                logger.info("Landbase Tile Layer '%s' already exists in Operational Layers (Skipped)", landbase_tile_item.title)
            else:
                if base_idx >= len(layers):
                    layers.append(lb_json)
                else:
                    layers.insert(base_idx, lb_json)

                track_layer(lb_json)
                logger.info("Inserted Landbase Tile Layer '%s' into Operational Layers at position %d", landbase_tile_item.title, base_idx)
                modified = True

        # 2. Network Tile Layer (Directly above Landbase Tile Layer)
        if network_tile_item:
            net_tile_json = self.build_tile_layer_json(network_tile_item)
            if is_layer_in_map(net_tile_json):
                logger.info("Network Tile Layer '%s' already exists in Operational Layers (Skipped)", network_tile_item.title)
            else:
                lb_idx = next((i for i, l in enumerate(layers) if l.get("itemId") == (landbase_tile_item.id if landbase_tile_item else "")), None)
                net_idx = lb_idx + 1 if lb_idx is not None else base_idx

                if net_idx >= len(layers):
                    layers.append(net_tile_json)
                else:
                    layers.insert(net_idx, net_tile_json)

                track_layer(net_tile_json)
                logger.info("Inserted Network Tile Layer '%s' into Operational Layers at position %d", network_tile_item.title, net_idx)
                modified = True
        else:
            logger.warning("Network Tile Layer not found; skipping Network Tile insertion.")

        # 3. Optional Feature Sublayers (Extracted from optional_hosted_item)
        if optional_hosted_item:
            opt_layer_dicts, opt_sub_count = self.build_hosted_layer_json(
                optional_hosted_item, 
                sublayer_name_filters=self.config.optional_sublayer_names
            )

            if opt_layer_dicts:
                net_idx = next((i for i, l in enumerate(layers) if l.get("itemId") == (network_tile_item.id if network_tile_item else "")), None)
                lb_idx = next((i for i, l in enumerate(layers) if l.get("itemId") == (landbase_tile_item.id if landbase_tile_item else "")), None)

                if net_idx is not None:
                    opt_idx = net_idx + 1
                elif lb_idx is not None:
                    opt_idx = lb_idx + 1
                else:
                    opt_idx = base_idx

                for opt_layer_json in opt_layer_dicts:
                    if is_layer_in_map(opt_layer_json):
                        logger.info("Optional Sublayer '%s' already exists in Operational Layers (Skipped)", opt_layer_json.get("title"))
                    else:
                        if opt_idx >= len(layers):
                            layers.append(opt_layer_json)
                        else:
                            layers.insert(opt_idx, opt_layer_json)

                        track_layer(opt_layer_json)
                        logger.info("Inserted Optional Sublayer '%s' into Operational Layers at position %d", 
                                    opt_layer_json.get("title"), opt_idx)
                        opt_idx += 1
                        modified = True

        # 4. Main Hosted Feature Layer (Directly ABOVE Optional Sublayers / Network Tile Layer)
        if hosted_item:
            feature_jsons, sub_count = self.build_hosted_layer_json(hosted_item)

            last_opt_pos = None
            if optional_hosted_item:
                opt_indices = [i for i, l in enumerate(layers) if l.get("itemId") == optional_hosted_item.id]
                if opt_indices:
                    last_opt_pos = max(opt_indices)

            net_idx = next((i for i, l in enumerate(layers) if l.get("itemId") == (network_tile_item.id if network_tile_item else "")), None)
            lb_idx = next((i for i, l in enumerate(layers) if l.get("itemId") == (landbase_tile_item.id if landbase_tile_item else "")), None)

            if last_opt_pos is not None:
                feat_idx = last_opt_pos + 1
            elif net_idx is not None:
                feat_idx = net_idx + 1
            elif lb_idx is not None:
                feat_idx = lb_idx + 1
            else:
                feat_idx = base_idx

            for feature_json in feature_jsons:
                if is_layer_in_map(feature_json):
                    logger.info("Feature Layer '%s' already exists in Operational Layers (Skipped)", feature_json.get("title"))
                else:
                    # Explicitly set minScale for the top-level Main Network Layer
                    if self.config.main_network_min_scale:
                        feature_json["minScale"] = self.config.main_network_min_scale
                        logger.info("Applied minScale (%s) to top-level Main Network Layer '%s'", 
                                    self.config.main_network_min_scale, feature_json.get("title"))

                    if feat_idx >= len(layers):
                        layers.append(feature_json)
                    else:
                        layers.insert(feat_idx, feature_json)

                    track_layer(feature_json)
                    logger.info("Inserted Main Feature Layer '%s' (%d sublayers) into Operational Layers at position %d", 
                                feature_json.get("title"), sub_count, feat_idx)
                    feat_idx += 1
                    modified = True

        return modified

    def log_layer_tree(self, layers: List[Dict[str, Any]], indent: int = 4) -> None:
        """Logs layer hierarchy tree for diagnostic tracking."""
        for layer in layers:
            title = layer.get("title") or layer.get("id") or "Untitled Layer"
            l_type = layer.get("layerType", "Layer")
            logger.info("%s├─ %s [%s]", " " * indent, title, l_type)

            if "layers" in layer and isinstance(layer["layers"], list):
                self.log_layer_tree(layer["layers"], indent=indent + 4)

    def process_area(self, lac: str) -> str:
        """Executes layer update workflow for a single LAC region."""
        logger.info("==================================================")
        logger.info("--- Processing Target Area: %s ---", lac)
        logger.info("==================================================")

        map_title = self.config.webmap_title_template.format(
            utility=self.config.utility,
            lac=lac
        )

        webmap_item = self.search_item(map_title, self.config.webmap_category)
        if not webmap_item:
            logger.warning("Web Map '%s' was not found.", map_title)
            return "skipped"

        # Search Main Hosted Feature Item
        hosted_item = self.search_candidate_titles(
            self.config.hosted_feature_templates, lac, self.config.hosted_feature_category
        )

        # Search Optional Feature Item strictly via optional_feature_templates
        optional_hosted_item = self.search_candidate_titles(
            self.config.optional_feature_templates, lac, self.config.hosted_feature_category
        )

        network_tile_item = self.search_candidate_titles(
            self.config.network_tile_templates, lac, self.config.tile_layer_category
        )
        landbase_tile_item = self.search_candidate_titles(
            self.config.landbase_tile_templates, lac, self.config.tile_layer_category
        )

        if not hosted_item:
            logger.warning("Main Hosted Feature Layer matching configured candidates was not found.")
            return "warning"

        # Fallback to hosted_item if optional_hosted_item wasn't found separately
        if not optional_hosted_item and hosted_item:
            logger.info("Using main feature layer '%s' as source to check for optional sublayers %s.", 
                        hosted_item.title, self.config.optional_sublayer_names)
            optional_hosted_item = hosted_item

        # Read Web Map JSON Data
        data = webmap_item.get_data() or {}

        # Step 1: Clean operational layers EXCEPT keywords in keep_layer_keywords
        was_cleaned = self.cleanup_existing_layers(data)

        # Step 2: Replace Basemap title with 'Landbase' using Landbase Tile Layer
        was_basemap_updated = self.update_basemap_with_landbase(data, landbase_tile_item)

        # Step 3: Add new operational layers
        was_added = self.add_layers_to_webmap(data, hosted_item, network_tile_item, landbase_tile_item, optional_hosted_item)

        modified = was_cleaned or was_basemap_updated or was_added

        logger.info("Operational Layer Tree Structure:")
        self.log_layer_tree(data.get("operationalLayers", []))

        if modified:
            if self.config.dry_run:
                logger.info("[DRY RUN] Changes calculated but not saved to AGOL Item ID '%s'.", webmap_item.id)
            else:
                webmap_item.update(data=json.dumps(data))
                logger.info("SUCCESS: Web Map '%s' updated successfully.", webmap_item.title)
            return "success"

        return "skipped"

    def run(self) -> Dict[str, int]:
        """Executes updater across all target LAC areas with error isolation."""
        stats = {"success": 0, "skipped": 0, "warning": 0, "error": 0}

        for lac in self.config.lac_areas:
            try:
                status = self.process_area(lac)
                stats[status if status in stats else "skipped"] += 1
            except Exception as exc:
                logger.error("Failed to process area '%s': %s", lac, exc, exc_info=True)
                stats["error"] += 1

        logger.info("==================================================")
        logger.info("EXECUTION SUMMARY | Updated: %d | Skipped: %d | Warnings: %d | Errors: %d", 
                    stats["success"], stats["skipped"], stats["warning"], stats["error"])
        logger.info("==================================================")
        return stats


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    config = UpdaterConfig()

    try:
        updater = WebMapUpdater(config)
        updater.run()
    except Exception as exc:
        logger.critical("Fatal error during execution: %s", exc, exc_info=True)