# Community Area Clustering

This map layer groups Chicago community areas by school/access patterns. It is descriptive only.

## What the model uses

The clustering uses four community-area inputs, all oriented so higher means more concern:

- assigned default weakness: median tract `default_index`
- local school weakness: mean weakness index for high schools physically located in the community area
- selective access weakness: median tract `access_index`
- local school supply gap: fewer CPS high schools located in the area

Race, income, and poverty are not clustering inputs. They stay in the panel as context.
Distance to the nearest strong high school remains a panel metric, but it is not a clustering input because the SAT >= 1010 threshold is mostly selective-enrollment schools in the current data.

## Method

`analysis/12_community_metrics.sql` builds one row per community area in PostGIS and exports `output/community_metrics.json`.
`analysis/13_community_groups.py` requires that SQL-exported file. There is intentionally no GeoJSON fallback. It robust-scales the four model inputs, runs deterministic KMeans for k=3 through k=7, saves PCA coordinates for explanation, and writes:

- `output/community_groups.json`
- `output/community_groups_diagnostics.json`
- `output/community_groups_selective_sensitivity.json`
- `frontend/public/data/community_groups.json`

The public map uses k=5. In the current four-input data, k=5 has the strongest silhouette score among k=3 through k=7 while keeping the groups interpretable and avoiding tiny singleton groups.

Public labels are locked in `analysis/community_group_labels.json`; they are not generated silently from each rebuild.

## Limits

These groups are not causal claims, admission odds, school effectiveness estimates, or official CPS categories. Distances are straight-line distances unless a future routing pipeline replaces them.
