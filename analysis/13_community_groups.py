#!/usr/bin/env python
"""Build community-area clusters for the frontend map.

This script intentionally has no GeoJSON fallback. It requires
output/community_metrics.json, exported by analysis/12_community_metrics.sql.
That keeps the modeling path reproducible: PostGIS builds the community metrics,
then this script clusters exactly that SQL output.

No demographic fields are used as clustering inputs. They are passed through
only as context for the panel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"
METRICS_PATH = OUTPUT / "community_metrics.json"
GROUPS_PATH = OUTPUT / "community_groups.json"
DIAGNOSTICS_PATH = OUTPUT / "community_groups_diagnostics.json"
SENSITIVITY_PATH = OUTPUT / "community_groups_selective_sensitivity.json"
LABELS_PATH = ROOT / "analysis" / "community_group_labels.json"

CHOSEN_K = 5
CHOICE_REASON = (
    "k=5 is locked for the public map after checking k=3..7: it has the "
    "strongest silhouette score in this run while preserving interpretable "
    "differences across assigned quality, local school quality, local school "
    "supply, and selective access without tiny singleton groups."
)

FEATURES = [
    {
        "key": "assigned_default_index",
        "label": "Assigned default weakness",
        "high": "weaker assigned defaults",
        "low": "stronger assigned defaults",
        "source": "Median tract default_index",
    },
    {
        "key": "local_school_index",
        "label": "Local school weakness",
        "high": "weaker schools located here",
        "low": "stronger schools located here",
        "source": "Mean local high-school weakness index",
    },
    {
        "key": "selective_access_index",
        "label": "Selective access weakness",
        "high": "limited selective access",
        "low": "stronger selective access",
        "source": "Median tract access_index",
    },
    {
        "key": "local_supply_gap",
        "label": "Local school supply gap",
        "high": "few or no high schools located here",
        "low": "more high schools located here",
        "source": "1 - min(local_hs_count, 4) / 4",
    },
]

DEMOGRAPHIC_KEYS = {"median_hh_income", "poverty_rate", "pct_black", "pct_hispanic", "pct_white"}
MODEL_FEATURE_KEYS = {f["key"] for f in FEATURES}


def clean_num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def median(values: list[float | None]) -> float | None:
    xs = sorted(v for v in values if v is not None and math.isfinite(v))
    if not xs:
        return None
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2


def percentile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        return 0.0
    pos = (len(xs) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def round_or_none(value: float | None, digits: int = 3) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_metrics() -> dict[str, Any]:
    if not METRICS_PATH.exists():
        raise FileNotFoundError(
            f"{METRICS_PATH.relative_to(ROOT)} is missing. Run analysis/12_community_metrics.sql "
            "through analysis/run_all.sh before clustering."
        )
    data = load_json(METRICS_PATH)
    source = str(data.get("source", ""))
    if "fallback" in source.lower() or "geojson" in source.lower():
        raise RuntimeError(
            f"{METRICS_PATH.relative_to(ROOT)} was not produced by analysis/12_community_metrics.sql. "
            "Delete it and rerun analysis/run_all.sh with PostGIS."
        )
    return data


def assert_source_counts(metrics: list[dict[str, Any]]) -> None:
    if len(metrics) != 77:
        raise RuntimeError(f"Expected 77 community areas, found {len(metrics)}")
    tract_count = sum(int(clean_num(row.get("tract_count")) or 0) for row in metrics)
    if tract_count != 791:
        raise RuntimeError(f"Expected 791 assigned tracts in community metrics, found {tract_count}")
    school_count = sum(int(clean_num(row.get("local_hs_count")) or 0) for row in metrics)
    if school_count != 170:
        raise RuntimeError(f"Expected 170 local high schools in community metrics, found {school_count}")
    names = [r["community_area"] for r in metrics]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate community_area names in community metrics")
    if MODEL_FEATURE_KEYS & DEMOGRAPHIC_KEYS:
        raise RuntimeError("Demographic variables cannot be clustering inputs")


def model_value(row: dict[str, Any], key: str) -> float | None:
    if key == "local_supply_gap":
        return 1.0 - min(clean_num(row.get("local_hs_count")) or 0.0, 4.0) / 4.0
    return clean_num(row.get(key))


def prepare_matrix(metrics: list[dict[str, Any]]) -> tuple[list[str], list[list[float]], list[dict[str, Any]], dict[str, float]]:
    communities = [r["community_area"] for r in metrics]
    raw_rows: list[dict[str, Any]] = []
    imputes: dict[str, float] = {}
    for feature in FEATURES:
        key = feature["key"]
        values = [model_value(row, key) for row in metrics]
        fill = median(values)
        if fill is None:
            raise RuntimeError(f"No data for model feature {key}")
        imputes[key] = fill

    matrix: list[list[float]] = []
    for row in metrics:
        raw: dict[str, Any] = {}
        vector: list[float] = []
        for feature in FEATURES:
            key = feature["key"]
            value = model_value(row, key)
            raw[f"{key}_imputed"] = value is None
            if value is None:
                value = imputes[key]
            raw[key] = value
            vector.append(value)
        raw_rows.append(raw)
        matrix.append(vector)
    return communities, matrix, raw_rows, imputes


def robust_scale(matrix: list[list[float]]) -> tuple[list[list[float]], list[dict[str, float]]]:
    columns = list(zip(*matrix))
    stats: list[dict[str, float]] = []
    for col in columns:
        values = list(col)
        med = percentile(values, 0.5)
        q1 = percentile(values, 0.25)
        q3 = percentile(values, 0.75)
        iqr = q3 - q1
        if abs(iqr) < 1e-9:
            iqr = max(max(values) - min(values), 1.0)
        stats.append({"median": med, "iqr": iqr})
    scaled = [[(row[i] - stats[i]["median"]) / stats[i]["iqr"] for i in range(len(row))] for row in matrix]
    return scaled, stats


def sqdist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sqdist(a, b))


def initial_centroids(points: list[list[float]], k: int) -> list[list[float]]:
    mean_point = [sum(row[i] for row in points) / len(points) for i in range(len(points[0]))]
    first = min(range(len(points)), key=lambda i: (sqdist(points[i], mean_point), i))
    centers = [points[first][:]]
    while len(centers) < k:
        next_i = max(
            range(len(points)),
            key=lambda i: (min(sqdist(points[i], c) for c in centers), -i),
        )
        centers.append(points[next_i][:])
    return centers


def kmeans(points: list[list[float]], k: int) -> tuple[list[int], list[list[float]]]:
    centers = initial_centroids(points, k)
    labels = [-1] * len(points)
    for _ in range(200):
        changed = False
        for i, point in enumerate(points):
            label = min(range(k), key=lambda c: (sqdist(point, centers[c]), c))
            if label != labels[i]:
                labels[i] = label
                changed = True
        new_centers: list[list[float]] = []
        for c in range(k):
            members = [points[i] for i, label in enumerate(labels) if label == c]
            if not members:
                farthest = max(range(len(points)), key=lambda i: min(sqdist(points[i], center) for center in centers))
                new_centers.append(points[farthest][:])
                labels[farthest] = c
                changed = True
            else:
                new_centers.append([sum(row[j] for row in members) / len(members) for j in range(len(points[0]))])
        if not changed and all(sqdist(a, b) < 1e-12 for a, b in zip(centers, new_centers)):
            centers = new_centers
            break
        centers = new_centers
    return labels, centers


def silhouette_score(points: list[list[float]], labels: list[int]) -> float:
    clusters = sorted(set(labels))
    scores: list[float] = []
    for i, point in enumerate(points):
        same = [j for j, label in enumerate(labels) if label == labels[i] and j != i]
        a = sum(euclidean(point, points[j]) for j in same) / len(same) if same else 0.0
        b_values = []
        for cluster in clusters:
            if cluster == labels[i]:
                continue
            other = [j for j, label in enumerate(labels) if label == cluster]
            if other:
                b_values.append(sum(euclidean(point, points[j]) for j in other) / len(other))
        b = min(b_values) if b_values else 0.0
        denom = max(a, b)
        scores.append((b - a) / denom if denom > 0 else 0.0)
    return sum(scores) / len(scores)


def pca(points: list[list[float]]) -> dict[str, Any]:
    n = len(points)
    dims = len(points[0])
    means = [sum(row[i] for row in points) / n for i in range(dims)]
    centered = [[row[i] - means[i] for i in range(dims)] for row in points]
    cov = [[sum(row[i] * row[j] for row in centered) / max(n - 1, 1) for j in range(dims)] for i in range(dims)]
    total_var = sum(cov[i][i] for i in range(dims))

    components: list[list[float]] = []
    eigenvalues: list[float] = []
    work = [row[:] for row in cov]
    for comp_index in range(2):
        vec = [1.0 / (i + 1 + comp_index) for i in range(dims)]
        norm = math.sqrt(sum(v * v for v in vec))
        vec = [v / norm for v in vec]
        for _ in range(200):
            nxt = [sum(work[i][j] * vec[j] for j in range(dims)) for i in range(dims)]
            norm = math.sqrt(sum(v * v for v in nxt))
            if norm < 1e-12:
                break
            nxt = [v / norm for v in nxt]
            if euclidean(vec, nxt) < 1e-10:
                vec = nxt
                break
            vec = nxt
        eigenvalue = sum(vec[i] * sum(work[i][j] * vec[j] for j in range(dims)) for i in range(dims))
        largest_loading = max(range(dims), key=lambda i: abs(vec[i]))
        if vec[largest_loading] < 0:
            vec = [-v for v in vec]
        components.append(vec)
        eigenvalues.append(max(eigenvalue, 0.0))
        for i in range(dims):
            for j in range(dims):
                work[i][j] -= eigenvalue * vec[i] * vec[j]

    scores = [[sum(row[i] * component[i] for i in range(dims)) for component in components] for row in centered]
    explained = [value / total_var if total_var > 0 else 0.0 for value in eigenvalues]
    return {
        "explained_variance_ratio": [round(v, 4) for v in explained],
        "loadings": [
            {FEATURES[i]["key"]: round(component[i], 4) for i in range(dims)}
            for component in components
        ],
        "scores": scores,
    }


def load_label_config() -> dict[str, Any]:
    if LABELS_PATH.exists():
        return load_json(LABELS_PATH)
    return {"chosen_k": CHOSEN_K, "labels": {}}


def driver_for(feature_index: int, z: float) -> dict[str, Any]:
    feature = FEATURES[feature_index]
    high = z >= 0
    magnitude = abs(z)
    return {
        "key": feature["key"],
        "label": feature["high"] if high else feature["low"],
        "metric": feature["label"],
        "direction": "high" if high else "low",
        "z": round(z, 2),
        "tone": "bad" if high and magnitude >= 0.45 else "good" if not high and magnitude >= 0.45 else "neutral",
    }


def group_drivers(centroid: list[float], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(range(len(centroid)), key=lambda i: abs(centroid[i]), reverse=True)
    meaningful = [i for i in ranked if abs(centroid[i]) >= 0.25]
    selected = meaningful[:limit] if meaningful else ranked[:1]
    return [driver_for(i, centroid[i]) for i in selected]


def ordered_group_assignments(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    communities, raw_matrix, raw_inputs, _imputes = prepare_matrix(metrics)
    scaled, _scale_stats = robust_scale(raw_matrix)
    diagnostics_by_k = {}
    labels_by_k = {}
    centers_by_k = {}
    for k in range(3, 8):
        labels, centers = kmeans(scaled, k)
        counts = {str(cluster): labels.count(cluster) for cluster in sorted(set(labels))}
        diagnostics_by_k[str(k)] = {
            "silhouette": round(silhouette_score(scaled, labels), 4),
            "min_cluster_size": min(counts.values()),
            "cluster_sizes": counts,
        }
        labels_by_k[k] = labels
        centers_by_k[k] = centers

    labels = labels_by_k[CHOSEN_K]
    centers = centers_by_k[CHOSEN_K]
    cluster_need = {
        cluster: sum(centers[cluster]) / len(centers[cluster])
        for cluster in range(CHOSEN_K)
    }
    ordered_clusters = sorted(range(CHOSEN_K), key=lambda c: cluster_need[c], reverse=True)
    cluster_to_group = {cluster: f"group_{i + 1}" for i, cluster in enumerate(ordered_clusters)}
    assignments = {communities[i]: cluster_to_group[labels[i]] for i in range(len(communities))}
    return {
        "assignments": assignments,
        "diagnostics_by_k": diagnostics_by_k,
        "raw_inputs": {communities[i]: raw_inputs[i] for i in range(len(communities))},
        "cluster_sizes": {
            f"group_{i + 1}": labels.count(cluster)
            for i, cluster in enumerate(ordered_clusters)
        },
    }


def selective_excluded_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjusted = []
    for row in metrics:
        item = dict(row)
        item["local_hs_count"] = row.get("local_nonselective_hs_count")
        item["local_testing_hs_count"] = row.get("local_nonselective_testing_hs_count")
        item["local_school_index"] = row.get("local_nonselective_school_index")
        adjusted.append(item)
    return adjusted


def selective_sensitivity_report(metrics: list[dict[str, Any]], baseline_output: dict[str, Any]) -> dict[str, Any]:
    variant_metrics = selective_excluded_metrics(metrics)
    variant = ordered_group_assignments(variant_metrics)
    baseline = baseline_output["communities"]
    labels_by_group = {group["id"]: group["label"] for group in baseline_output["groups"]}
    changed = []
    for row in metrics:
        community = row["community_area"]
        base_group = baseline[community]["group_id"]
        variant_group = variant["assignments"][community]
        if base_group == variant_group:
            continue
        changed.append({
            "community_area": community,
            "baseline_group": base_group,
            "baseline_label": labels_by_group.get(base_group),
            "selective_excluded_group": variant_group,
            "selective_excluded_label": labels_by_group.get(variant_group),
            "local_selective_hs_count": int(clean_num(row.get("local_selective_hs_count")) or 0),
            "local_nonselective_hs_count": int(clean_num(row.get("local_nonselective_hs_count")) or 0),
        })

    communities_with_local_selective = [
        row["community_area"]
        for row in metrics
        if (clean_num(row.get("local_selective_hs_count")) or 0) > 0
    ]
    imputed_local_nonselective = [
        name for name, raw in variant["raw_inputs"].items()
        if raw.get("local_school_index_imputed")
    ]

    return {
        "schema_version": 1,
        "purpose": "Sensitivity check: remove selective-enrollment schools from local school quality and local supply before re-running the same k=5 clustering.",
        "baseline_file": str(GROUPS_PATH.relative_to(ROOT)),
        "feature_replacements": {
            "local_school_index": "local_nonselective_school_index",
            "local_supply_gap": "computed from local_nonselective_hs_count",
            "selective_access_index": "unchanged; this remains the explicit competitive-access signal",
        },
        "chosen_k": CHOSEN_K,
        "k_diagnostics": variant["diagnostics_by_k"],
        "baseline_cluster_sizes": {group["id"]: group["size"] for group in baseline_output["groups"]},
        "selective_excluded_cluster_sizes": variant["cluster_sizes"],
        "communities_with_local_selective_hs_count": len(communities_with_local_selective),
        "communities_with_local_selective_hs": communities_with_local_selective,
        "local_nonselective_quality_imputed_count": len(imputed_local_nonselective),
        "local_nonselective_quality_imputed_communities": imputed_local_nonselective,
        "changed_group_count": len(changed),
        "changed_group_share": round(len(changed) / max(len(metrics), 1), 3),
        "changed_communities": changed,
    }


def main() -> None:
    data = load_metrics()
    metrics = sorted(data["communities"], key=lambda r: r["community_area"])
    assert_source_counts(metrics)

    communities, raw_matrix, raw_inputs, imputes = prepare_matrix(metrics)
    scaled, scale_stats = robust_scale(raw_matrix)

    diagnostics_by_k = {}
    labels_by_k = {}
    centers_by_k = {}
    for k in range(3, 8):
        labels, centers = kmeans(scaled, k)
        counts = {str(cluster): labels.count(cluster) for cluster in sorted(set(labels))}
        diagnostics_by_k[str(k)] = {
            "silhouette": round(silhouette_score(scaled, labels), 4),
            "min_cluster_size": min(counts.values()),
            "cluster_sizes": counts,
        }
        labels_by_k[k] = labels
        centers_by_k[k] = centers

    labels = labels_by_k[CHOSEN_K]
    centers = centers_by_k[CHOSEN_K]
    cluster_need = {
        cluster: sum(centers[cluster]) / len(centers[cluster])
        for cluster in range(CHOSEN_K)
    }
    ordered_clusters = sorted(range(CHOSEN_K), key=lambda c: cluster_need[c], reverse=True)
    cluster_to_group = {cluster: f"group_{i + 1}" for i, cluster in enumerate(ordered_clusters)}
    group_to_cluster = {group: cluster for cluster, group in cluster_to_group.items()}

    label_config = load_label_config()
    configured_labels = label_config.get("labels", {})
    default_colors = ["#e23b3b", "#f0883e", "#d8a31a", "#5b6472", "#2fcb7e"]

    pca_result = pca(scaled)
    score_by_community = {communities[i]: pca_result["scores"][i] for i in range(len(communities))}

    groups = []
    for group_index in range(1, CHOSEN_K + 1):
        group_id = f"group_{group_index}"
        cluster = group_to_cluster[group_id]
        configured = configured_labels.get(group_id, {})
        members = [communities[i] for i, label in enumerate(labels) if label == cluster]
        drivers = group_drivers(centers[cluster])
        label = configured.get("label") or " + ".join(driver["label"] for driver in drivers[:2]).capitalize()
        groups.append({
            "id": group_id,
            "label": label,
            "color": configured.get("color") or default_colors[group_index - 1],
            "description": configured.get("description") or "Descriptive cluster based on school outcomes, supply, and access.",
            "size": len(members),
            "drivers": drivers,
        })

    group_lookup = {group["id"]: group for group in groups}
    rows_by_community = {row["community_area"]: row for row in metrics}
    scaled_by_community = {communities[i]: scaled[i] for i in range(len(communities))}

    community_output: dict[str, Any] = {}
    for i, community in enumerate(communities):
        cluster = labels[i]
        group_id = cluster_to_group[cluster]
        group = group_lookup[group_id]
        same_group = [name for name in communities if name != community and cluster_to_group[labels[communities.index(name)]] == group_id]
        similar = sorted(
            same_group,
            key=lambda name: euclidean(scaled_by_community[community], scaled_by_community[name]),
        )[:4]
        row = rows_by_community[community]
        flags = []
        if (clean_num(row.get("local_hs_count")) or 0) == 0:
            flags.append("No CPS high school located here")
        elif (clean_num(row.get("local_testing_hs_count")) or 0) == 0:
            flags.append("No local testing high school metrics")

        community_output[community] = {
            "community_area": community,
            "group_id": group_id,
            "group_label": group["label"],
            "group_color": group["color"],
            "group_description": group["description"],
            "drivers": group["drivers"],
            "flags": flags,
            "similar_communities": similar,
            "pca": {
                "x": round(score_by_community[community][0], 4),
                "y": round(score_by_community[community][1], 4),
            },
            "model_inputs": {
                **{feature["key"]: round_or_none(raw_inputs[i][feature["key"]], 4) for feature in FEATURES},
                "nearest_strong_mi": round_or_none(clean_num(row.get("nearest_strong_mi")), 2),
                "local_school_index_imputed": raw_inputs[i]["local_school_index_imputed"],
            },
            "metrics": row,
        }

    output = {
        "schema_version": 1,
        "method": "Robust-scaled KMeans over community-area school/access indices; PCA saved for explanation only.",
        "chosen_k": CHOSEN_K,
        "choice_reason": CHOICE_REASON,
        "features": FEATURES,
        "groups": groups,
        "communities": community_output,
        "notes": [
            "Groups are descriptive patterns, not causal claims.",
            "Groups are not admission odds.",
            "Distances are straight-line distances unless a future routing pipeline replaces them.",
            "Race, income, and poverty are not clustering inputs; they are displayed only as context.",
        ],
    }

    sensitivity = selective_sensitivity_report(metrics, output)

    diagnostics = {
        "schema_version": 1,
        "source_metrics": str(METRICS_PATH.relative_to(ROOT)),
        "chosen_k": CHOSEN_K,
        "choice_reason": CHOICE_REASON,
        "k_diagnostics": diagnostics_by_k,
        "pca_explained_variance_ratio": pca_result["explained_variance_ratio"],
        "pca_loadings": pca_result["loadings"],
        "features": FEATURES,
        "imputed_values": {key: round(value, 4) for key, value in imputes.items()},
        "robust_scale": {
            FEATURES[i]["key"]: {key: round(value, 4) for key, value in stat.items()}
            for i, stat in enumerate(scale_stats)
        },
        "cluster_sizes": {group["id"]: group["size"] for group in groups},
        "cluster_centroid_z_scores": {
            group["id"]: {
                FEATURES[i]["key"]: round(centers[group_to_cluster[group["id"]]][i], 3)
                for i in range(len(FEATURES))
            }
            for group in groups
        },
        "communities_by_group": {
            group["id"]: [
                name for name, item in community_output.items()
                if item["group_id"] == group["id"]
            ]
            for group in groups
        },
        "demographics_used_as_inputs": False,
    }

    for community, item in community_output.items():
        if not item.get("group_id"):
            raise RuntimeError(f"{community} did not receive a group")
    for group in groups:
        if not group.get("label") or not group.get("color"):
            raise RuntimeError(f"Missing group label/color for {group['id']}")

    write_json(GROUPS_PATH, output)
    write_json(DIAGNOSTICS_PATH, diagnostics)
    write_json(SENSITIVITY_PATH, sensitivity)
    FRONTEND_DATA.mkdir(parents=True, exist_ok=True)
    write_json(FRONTEND_DATA / "community_groups.json", output)

    print(f"wrote {GROUPS_PATH.relative_to(ROOT)}")
    print(f"wrote {DIAGNOSTICS_PATH.relative_to(ROOT)}")
    print(f"wrote {SENSITIVITY_PATH.relative_to(ROOT)}")
    print(f"wrote {(FRONTEND_DATA / 'community_groups.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
