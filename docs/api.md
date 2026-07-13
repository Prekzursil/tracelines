# API reference

Auto-generated from docstrings. These are the stable, load-bearing public functions; internal
helpers are omitted on purpose.

## The HARD-RULE filter

::: svcoverage.models.is_official_panoid
    options:
      show_root_heading: true
      heading_level: 3

## Data model

::: svcoverage.models.Pano
    options:
      heading_level: 3
      members: []

::: svcoverage.models.CoverageSegment
    options:
      heading_level: 3
      members: [length_m, n_points, to_geojson_feature]

::: svcoverage.models.Source
    options:
      heading_level: 3

## Extraction

::: svcoverage.pipeline.extract
    options:
      heading_level: 3

::: svcoverage.nearest.find_nearest_coverage
    options:
      heading_level: 3

::: svcoverage.nearest.nearest_official
    options:
      heading_level: 3

::: svcoverage.probe.density_probe
    options:
      heading_level: 3

## Export

::: svcoverage.export.write_geojson
    options:
      heading_level: 3

::: svcoverage.export.summary_stats
    options:
      heading_level: 3

## Configuration

::: svcoverage.config.Settings
    options:
      heading_level: 3
      members: []
