# Output schema

The primary artifact is a **GeoJSON `FeatureCollection`** of `LineString` features in
**EPSG:4326** (coordinates are `[longitude, latitude]`). A machine-readable JSON Schema is
committed at [`docs/schema/coverage.schema.json`](schema/coverage.schema.json).

## Feature properties

| Property | Type | Always? | Meaning |
|----------|------|---------|---------|
| `source` | `"google"` \| `"mapillary"` \| `"kartaview"` | ✅ | provenance — which source produced this line |
| `length_m` | number | ✅ | great-circle length in metres |
| `n_points` | integer ≥ 2 | ✅ | vertex count |
| `id` | string | — | segment id (e.g. `google-seg-42`, or the Mapillary sequence id) |
| `capture_date` | string | — | `YYYY-MM` (Google, `--precision`) or ISO date |
| `pano_ids` | string[] | — | the official pano ids composing a Google line (provenance) |
| `is_pano` | boolean | — | Mapillary 360 flag |
| `sequence_id` | string | — | Mapillary/KartaView sequence id |

Every geometry is a `LineString` with ≥ 2 points; degenerate features are dropped on export.

## Example

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[26.050403, 44.434487], [26.050512, 44.434971]]
      },
      "properties": {
        "source": "google",
        "length_m": 390.83,
        "n_points": 39,
        "id": "google-seg-42",
        "capture_date": "2024-07"
      }
    }
  ]
}
```

## Validate downstream

```python
import json, jsonschema  # pip install jsonschema
schema = json.load(open("docs/schema/coverage.schema.json"))
data = json.load(open("bucharest.geojson"))
jsonschema.validate(data, schema)   # raises if malformed

# The HARD RULE is also checkable on the output: no Google feature should carry a photosphere id.
from tracelines.models import is_official_panoid
for f in data["features"]:
    if f["properties"]["source"] == "google":
        for pid in f["properties"].get("pano_ids", []):
            assert is_official_panoid(pid), f"non-official id in output: {pid}"
```

The `source` property is your **provenance record** — keep it, because it determines what you may do
with each line (see [Data provenance](data-provenance.md)).
