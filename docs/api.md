# API reference

Auto-generated from docstrings. These are the stable, load-bearing public functions; internal
helpers are omitted on purpose.

## The HARD-RULE filter

::: tracelines.models.is_official_panoid
    options:
      show_root_heading: true
      heading_level: 3

## Data model

::: tracelines.models.Pano
    options:
      heading_level: 3
      members: []

::: tracelines.models.CoverageSegment
    options:
      heading_level: 3
      members: [length_m, n_points, to_geojson_feature]

::: tracelines.models.Source
    options:
      heading_level: 3

## Extraction

::: tracelines.pipeline.extract
    options:
      heading_level: 3

::: tracelines.nearest.find_nearest_coverage
    options:
      heading_level: 3

::: tracelines.nearest.nearest_official
    options:
      heading_level: 3

::: tracelines.probe.density_probe
    options:
      heading_level: 3

## Export

::: tracelines.export.write_geojson
    options:
      heading_level: 3

::: tracelines.export.summary_stats
    options:
      heading_level: 3

## Configuration

::: tracelines.config.Settings
    options:
      heading_level: 3
      members: []
