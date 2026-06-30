// App is the whole thing. It loads the precomputed static GeoJSON from
// public/data (tract metrics, schools, community groups, CTA layers, and the
// click-to-route paths), keeps the map toggles and the current selection, and on
// a click pulls that tract's numbers + routes into the side panel and the map.
// There is no backend — everything here reads files the analysis pipeline baked.
import { useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection, Feature, Point } from "geojson";
import type { ViewState, MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { Map as MaplibreMap } from "maplibre-gl";
import MapView from "./components/MapView";
import InfoPanel, { type CommunitySummary, type Selection } from "./components/InfoPanel";
import { LAYERS, type LayerDef, type TractProps, type SchoolProps } from "./layers";

const median = (xs: number[]) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};

const numProp = (props: Record<string, unknown>, key: string): number | null => {
  const v = props[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
};

const medianProp = (features: Feature[], key: string) => {
  const values = features
    .map((f) => numProp((f.properties ?? {}) as Record<string, unknown>, key))
    .filter((v): v is number => v != null);
  return median(values);
};

const meanProp = (features: Feature[], key: string) => {
  const values = features
    .map((f) => numProp((f.properties ?? {}) as Record<string, unknown>, key))
    .filter((v): v is number => v != null);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
};

const meanSchoolProp = (schools: SchoolProps[], key: keyof SchoolProps) => {
  const values = schools
    .map((school) => school[key])
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
};

async function reverseGeocode(lng: number, lat: number): Promise<string | null> {
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=jsonv2&zoom=18&addressdetails=1`,
      { headers: { Accept: "application/json" } }
    );
    const d = await r.json();
    const a = d.address ?? {};
    if (a.road) return a.house_number ? `${a.house_number} ${a.road}` : a.road;
    return (d.display_name as string | undefined)?.split(",")[0] ?? null;
  } catch {
    return null;
  }
}

const DATA = import.meta.env.BASE_URL;
const byId = (id: string) => LAYERS.find((l) => l.id === id)!;
// Chicago city extent; left padding leaves room for the left-hand chrome.
const CHI_BOUNDS: [[number, number], [number, number]] = [[-87.94, 41.64], [-87.52, 42.03]];
const FIT_PADDING = { top: 90, bottom: 70, left: 290, right: 70 };
const STRONG_SCHOOL_SAT = 1010;

type ClusterDriver = {
  key: string;
  label: string;
  metric: string;
  direction: "high" | "low";
  z: number;
  tone: "bad" | "good" | "neutral";
};

type CommunityCluster = {
  community_area: string;
  group_id: string;
  group_label: string;
  group_color: string;
  group_description: string;
  drivers: ClusterDriver[];
  flags: string[];
  similar_communities: string[];
  pca: { x: number; y: number };
  model_inputs: Record<string, number | boolean | null>;
};

type CommunityGroupsData = {
  groups: { id: string; label: string; color: string; description: string; size: number; drivers: ClusterDriver[] }[];
  communities: Record<string, CommunityCluster>;
};

// Per-route map styling: color matches the drawn line; frac staggers the label
// position along each route so the pills don't stack on top of one another.
const ROUTE_STYLE: Record<string, { color: string; tag: string; frac: number }> = {
  assigned: { color: "#5b9dff", tag: "Assigned", frac: 0.5 },
  selective: { color: "#ffb84d", tag: "Drive", frac: 0.4 },
  transit: { color: "#36d39b", tag: "CTA", frac: 0.64 },
};

type RouteLabel = { lng: number; lat: number; label: string; color?: string };

// Label a precomputed route part-way along it, color-coded + tagged by mode.
function routeLabel(f: Feature): RouteLabel | null {
  const g = f.geometry;
  if (g?.type !== "LineString" || !g.coordinates.length) return null;
  const coords = g.coordinates as [number, number][];
  const minutes = (f.properties?.minutes as number | null) ?? null;
  if (minutes == null) return null;
  const st = ROUTE_STYLE[(f.properties?.role as string) ?? ""] ?? { color: undefined, tag: "", frac: 0.5 };
  const at = coords[Math.min(coords.length - 1, Math.max(0, Math.round((coords.length - 1) * st.frac)))];
  return { lng: at[0], lat: at[1], label: `${st.tag} ${Math.round(minutes)} min`.trim(), color: st.color };
}

function haversineMi(a: [number, number], b: [number, number]): number {
  const R = 3958.8, toR = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toR, dLng = (b[0] - a[0]) * toR;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * toR) * Math.cos(b[1] * toR) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(s));
}

export default function App() {
  const [tracts, setTracts] = useState<FeatureCollection | null>(null);
  const [schools, setSchools] = useState<FeatureCollection | null>(null);
  const [cityBoundary, setCityBoundary] = useState<FeatureCollection | null>(null);
  const [communityAreas, setCommunityAreas] = useState<FeatureCollection | null>(null);
  const [communityGroups, setCommunityGroups] = useState<CommunityGroupsData | null>(null);
  const [railLines, setRailLines] = useState<FeatureCollection | null>(null);
  const [railStations, setRailStations] = useState<FeatureCollection | null>(null);
  const [busLines, setBusLines] = useState<FeatureCollection | null>(null);
  const [routes, setRoutes] = useState<FeatureCollection | null>(null);
  const [activeId] = useState<LayerDef["id"]>("pct_black");
  const [showPins, setShowPins] = useState(true);
  const [showRail, setShowRail] = useState(false);
  const [showBus, setShowBus] = useState(false);
  const [showColoring, setShowColoring] = useState(true);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [connector, setConnector] = useState<FeatureCollection | null>(null);
  const [connectorLabels, setConnectorLabels] = useState<{ lng: number; lat: number; label: string; color?: string }[]>([]);
  const [viewState, setViewState] = useState<Partial<ViewState>>({ longitude: -87.72, latitude: 41.83, zoom: 9.6 });

  useEffect(() => {
    fetch(`${DATA}data/tracts.geojson`).then((r) => r.json()).then(setTracts);
    fetch(`${DATA}data/schools.geojson`).then((r) => r.json()).then(setSchools);
    fetch(`${DATA}data/city_boundary.geojson`).then((r) => r.json()).then(setCityBoundary);
    fetch(`${DATA}data/community_areas.geojson`).then((r) => r.json()).then(setCommunityAreas);
    fetch(`${DATA}data/community_groups.json`).then((r) => r.json()).then(setCommunityGroups);
    fetch(`${DATA}data/cta_rail_lines.geojson`).then((r) => r.json()).then(setRailLines).catch(() => {});
    fetch(`${DATA}data/cta_rail_stations.geojson`).then((r) => r.json()).then(setRailStations).catch(() => {});
    fetch(`${DATA}data/cta_bus_lines.geojson`).then((r) => r.json()).then(setBusLines).catch(() => {});
    fetch(`${DATA}data/routes.geojson`).then((r) => r.json()).then(setRoutes).catch(() => {});
  }, []);

  const selectiveSchools = useMemo(
    () => (schools?.features ?? []).filter((f) => f.properties?.is_selective) as Feature<Point>[],
    [schools]
  );

  // name -> school feature, for looking up the assigned school + opening cards
  const schoolsByName = useMemo(() => {
    const m = new Map<string, Feature<Point>>();
    (schools?.features ?? []).forEach((f) => {
      if (f.properties?.name) m.set(f.properties.name, f as Feature<Point>);
    });
    return m;
  }, [schools]);

  const activeLayer = byId(activeId);
  // unique CTA 'L' lines (name + official color) for the transit legend
  const railLegend = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of railLines?.features ?? []) {
      const route = f.properties?.route as string | undefined;
      const color = f.properties?.color as string | undefined;
      if (route && color && !m.has(route)) m.set(route, color);
    }
    return [...m].map(([route, color]) => ({ route, color })).sort((a, b) => a.route.localeCompare(b.route));
  }, [railLines]);
  const BUS_COLOR = "#7fb6ff";
  const communityGroupByName = useMemo(
    () => new Map(Object.entries(communityGroups?.communities ?? {})),
    [communityGroups]
  );
  const clusterLegend = communityGroups?.groups ?? [];
  // precomputed real routes grouped by tract geoid (drawn on click)
  const routesByGeoid = useMemo(() => {
    const m = new Map<string, Feature[]>();
    for (const f of routes?.features ?? []) {
      const g = f.properties?.geoid;
      if (typeof g === "string") { const a = m.get(g) ?? []; a.push(f as Feature); m.set(g, a); }
    }
    return m;
  }, [routes]);

  // city reference values for in-panel comparisons (tract-level + school-level)
  const refs = useMemo(() => {
    const tf = tracts?.features ?? [];
    const sf = schools?.features ?? [];
    const num = (arr: any[], k: string) =>
      arr.map((f) => f.properties![k]).filter((v): v is number => v != null && v > 0);
    const schoolSats = num(sf, "sat_g11").sort((a, b) => a - b);
    return {
      medianIncome: median(num(tf, "median_hh_income")),
      medianAssignedSat: median(num(tf, "assigned_sat")),
      schoolSats, // sorted, for percentile
      schoolMedians: {
        sat: median(schoolSats),
        grad: median(num(sf, "grad_4yr")),
        college: median(num(sf, "college_enroll")),
        ontrack: median(num(sf, "freshman_ontrack")),
        attendance: median(num(sf, "attendance")),
        truancy: median(num(sf, "truancy")),
      },
    };
  }, [tracts, schools]);

  const communitySummaries = useMemo(() => {
    const byCommunity = new Map<string, Feature[]>();
    for (const feature of tracts?.features ?? []) {
      const name = feature.properties?.community_area;
      if (typeof name !== "string" || !name) continue;
      const list = byCommunity.get(name) ?? [];
      list.push(feature);
      byCommunity.set(name, list);
    }

    const schoolsByCommunity = new Map<string, SchoolProps[]>();
    for (const feature of schools?.features ?? []) {
      const props = feature.properties as SchoolProps | null;
      if (!props?.community_area) continue;
      const list = schoolsByCommunity.get(props.community_area) ?? [];
      list.push({ ...props, is_selective: props.is_selective === true || String(props.is_selective) === "true" });
      schoolsByCommunity.set(props.community_area, list);
    }

    const summaries = new Map<string, CommunitySummary>();
    for (const [name, features] of byCommunity) {
      const assignmentCounts = new Map<string, number>();
      for (const feature of features) {
        const assigned = feature.properties?.assigned_school;
        if (typeof assigned === "string" && assigned) {
          assignmentCounts.set(assigned, (assignmentCounts.get(assigned) ?? 0) + 1);
        }
      }

      const assignedSchools = Array.from(assignmentCounts, ([schoolName, count]) => ({
        name: schoolName,
        count,
        share: count / features.length,
      })).sort((a, b) => b.count - a.count);

      const metrics: CommunitySummary["metrics"] = {
        median_hh_income: medianProp(features, "median_hh_income"),
        poverty_rate: meanProp(features, "poverty_rate"),
        pct_black: meanProp(features, "pct_black"),
        pct_hispanic: meanProp(features, "pct_hispanic"),
        pct_white: meanProp(features, "pct_white"),
        assigned_sat: medianProp(features, "assigned_sat"),
        assigned_grad: medianProp(features, "assigned_grad"),
        assigned_college: medianProp(features, "assigned_college"),
        assigned_ontrack: medianProp(features, "assigned_ontrack"),
        assigned_attendance: medianProp(features, "assigned_attendance"),
        assigned_truancy: medianProp(features, "assigned_truancy"),
        nearest_selective_mi: medianProp(features, "nearest_selective_mi"),
        sat_of_nearest_selective: medianProp(features, "sat_of_nearest_selective"),
        miles_to_nearest_elite: medianProp(features, "miles_to_nearest_elite"),
        n_selective_within_3mi: medianProp(features, "n_selective_within_3mi"),
        drive_min_to_nearest_elite: medianProp(features, "drive_min_to_nearest_elite"),
        transit_min_to_nearest_elite: medianProp(features, "transit_min_to_nearest_elite"),
        n_selective_within_30min_transit: medianProp(features, "n_selective_within_30min_transit"),
        national_gap: medianProp(features, "national_gap"),
        default_index: medianProp(features, "default_index"),
        access_index: medianProp(features, "access_index"),
      };

      const flags: CommunitySummary["flags"] = [];
      if (metrics.assigned_sat != null && refs.schoolMedians.sat != null && metrics.assigned_sat < refs.schoolMedians.sat * 0.9) {
        flags.push({ label: "low SAT", tone: "bad" });
      }
      if (metrics.assigned_grad != null && refs.schoolMedians.grad != null && metrics.assigned_grad < refs.schoolMedians.grad * 0.9) {
        flags.push({ label: "low graduation", tone: "bad" });
      }
      if (metrics.assigned_college != null && refs.schoolMedians.college != null && metrics.assigned_college < refs.schoolMedians.college * 0.9) {
        flags.push({ label: "college gap", tone: "bad" });
      }
      if (metrics.assigned_truancy != null && refs.schoolMedians.truancy != null && metrics.assigned_truancy > refs.schoolMedians.truancy * 1.1) {
        flags.push({ label: "high truancy", tone: "warn" });
      }
      if (metrics.n_selective_within_3mi === 0) {
        flags.push({ label: "no selective within 3 mi", tone: "warn" });
      }

      const communitySchools = (schoolsByCommunity.get(name) ?? []).sort((a, b) => (b.sat_g11 ?? 0) - (a.sat_g11 ?? 0));
      const typeCounts = new Map<string, number>();
      for (const school of communitySchools) {
        const label = school.is_selective ? "selective" : school.type.toLowerCase();
        typeCounts.set(label, (typeCounts.get(label) ?? 0) + 1);
      }
      const schoolMetrics = {
        sat_g11: meanSchoolProp(communitySchools, "sat_g11"),
        grad_4yr: meanSchoolProp(communitySchools, "grad_4yr"),
        college_enroll: meanSchoolProp(communitySchools, "college_enroll"),
        freshman_ontrack: meanSchoolProp(communitySchools, "freshman_ontrack"),
        attendance: meanSchoolProp(communitySchools, "attendance"),
        truancy: meanSchoolProp(communitySchools, "truancy"),
      };
      const cluster = communityGroupByName.get(name) ?? null;
      for (const flag of cluster?.flags ?? []) {
        flags.push({ label: flag, tone: "warn" });
      }
      if (!flags.length) flags.push({ label: "near city median", tone: "good" });

      summaries.set(name, {
        name,
        cluster,
        tractCount: features.length,
        assignedSchools,
        schools: communitySchools,
        schoolTypeCounts: Array.from(typeCounts, ([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count),
        schoolMetrics,
        metrics,
        flags,
      });
    }

    return summaries;
  }, [communityGroupByName, tracts, schools, refs]);

  const clusteredCommunityAreas = useMemo(() => {
    if (!communityAreas) return null;
    return {
      ...communityAreas,
      features: communityAreas.features.map((feature) => {
        const rawName = feature.properties?.name ?? feature.properties?.community_area;
        const communityName = typeof rawName === "string" ? rawName : null;
        const cluster = typeof communityName === "string" ? communityGroupByName.get(communityName) : null;
        return {
          ...feature,
          properties: {
            ...feature.properties,
            name: communityName,
            community_area: communityName,
            cluster_group: cluster?.group_id ?? null,
          },
        };
      }),
    } as FeatureCollection;
  }, [communityAreas, communityGroupByName]);

  function handleClick(e: MapLayerMouseEvent) {
    const f = e.features?.[0];
    if (!f) return;
    // clicked a school pin -> rich school panel + fly in
    if (typeof f.layer?.id === "string" && f.layer.id.startsWith("pins")) {
      openSchoolFromProps(f.properties);
      flyTo((f.geometry as any).coordinates as [number, number], 13);
      return;
    }
    // clicked a neighborhood -> hood panel + lines (assigned + nearest selective) + address
    const props = f.properties as TractProps;
    const here: [number, number] = [e.lngLat.lng, e.lngLat.lat];
    const mid = (c: [number, number]): [number, number] => [(here[0] + c[0]) / 2, (here[1] + c[1]) / 2];
    const lines: Feature[] = [];
    const labels: { lng: number; lat: number; label: string }[] = [];

    // line to the assigned default high school
    let assignedMiles: number | null = null;
    const assignedF = props.assigned_school ? schoolsByName.get(props.assigned_school) : undefined;
    if (assignedF) {
      const c = assignedF.geometry.coordinates as [number, number];
      assignedMiles = haversineMi(here, c);
      lines.push({ type: "Feature", properties: { role: "assigned" }, geometry: { type: "LineString", coordinates: [here, c] } });
      const m = mid(c); labels.push({ lng: m[0], lat: m[1], label: `${assignedMiles.toFixed(1)} mi` });
    }

    // fallback straight line to the nearest selective (only used if a tract has no precomputed route)
    if (selectiveSchools.length) {
      let best: Feature<Point> | null = null, bestD = Infinity;
      for (const s of selectiveSchools) {
        const d = haversineMi(here, s.geometry.coordinates as [number, number]);
        if (d < bestD) { bestD = d; best = s; }
      }
      if (best) {
        const c = best.geometry.coordinates as [number, number];
        lines.push({ type: "Feature", properties: { role: "selective" }, geometry: { type: "LineString", coordinates: [here, c] } });
        const m = mid(c); labels.push({ lng: m[0], lat: m[1], label: `${bestD.toFixed(1)} mi` });
      }
    }

    let nearestStrong: { name: string; sat: number | null; miles: number } | null = null;
    for (const school of schools?.features ?? []) {
      if (school.geometry?.type !== "Point") continue;
      const props = school.properties as SchoolProps | null;
      if (props?.sat_g11 == null || props.sat_g11 < STRONG_SCHOOL_SAT) continue;
      const d = haversineMi(here, (school as Feature<Point>).geometry.coordinates as [number, number]);
      if (!nearestStrong || d < nearestStrong.miles) {
        nearestStrong = { name: props.name, sat: props.sat_g11, miles: d };
      }
    }

    // prefer real precomputed routes for this tract; fall back to straight lines
    const tractRoutes = routesByGeoid.get(props.geoid) ?? [];
    if (tractRoutes.length) {
      setConnector({ type: "FeatureCollection", features: tractRoutes });
      setConnectorLabels(tractRoutes.map(routeLabel).filter((l): l is RouteLabel => l != null));
    } else {
      setConnector(lines.length ? { type: "FeatureCollection", features: lines } : null);
      setConnectorLabels(labels);
    }
    const community = props.community_area ? communitySummaries.get(props.community_area) ?? null : null;
    setSelection({ kind: "hood", props, community, nearestStrong, address: null, assignedMiles });
    flyTo(here, 12.2);
    // fill in the street address asynchronously (Nominatim, keyless)
    reverseGeocode(here[0], here[1]).then((addr) => {
      if (!addr) return;
      setSelection((prev) =>
        prev && prev.kind === "hood" && prev.props.geoid === props.geoid ? { ...prev, address: addr } : prev
      );
    });
  }

  function openSchoolFromProps(p: any) {
    setConnector(null);
    setConnectorLabels([]);
    setSelection({
      kind: "school",
      props: { ...p, is_selective: p.is_selective === true || p.is_selective === "true" } as SchoolProps,
    });
  }
  // open the rich school card from a clickable card in the neighborhood panel
  function openSchool(name: string) {
    const f = schoolsByName.get(name);
    if (f) {
      openSchoolFromProps(f.properties);
      flyTo(f.geometry.coordinates as [number, number], 13);
    }
  }

  // smooth fly-in on click; offset left so the target clears the right-hand panel
  const mapRef = useRef<MaplibreMap | null>(null);
  function flyTo(coords: [number, number], minZoom: number) {
    const map = mapRef.current;
    if (!map) return;
    const zoom = Math.max(map.getZoom(), minZoom);
    map.flyTo({ center: coords, zoom, duration: 850, offset: [-150, 0], essential: true });
  }

  if (!tracts || !communityAreas || !communityGroups) return <div className="loading">Loading Chicago...</div>;

  return (
    <div className="app">
      <div className="map-root">
        {/* base map = layer A (interactive) */}
        <MapView
          layer={activeLayer}
          tracts={tracts}
          communityAreas={clusteredCommunityAreas}
          schools={schools}
          cityBoundary={cityBoundary}
          clusterGroups={clusterLegend}
          showColoring={showColoring}
          showPins={showPins}
          railLines={railLines}
          railStations={railStations}
          showRail={showRail}
          busLines={busLines}
          showBus={showBus}
          lineFC={connector}
          labels={connectorLabels}
          viewState={viewState}
          onMove={setViewState}
          interactive
          hoveredId={hoveredId}
          selectedId={selection?.kind === "hood" ? selection.props.geoid : null}
          selectedCommunity={selection?.kind === "hood" ? selection.props.community_area : null}
          onHover={(id) => setHoveredId((prev) => (prev === id ? prev : id))}
          onClick={handleClick}
          onSchoolClick={(props, coords) => {
            openSchoolFromProps(props);
            flyTo(coords, 13);
          }}
          onLoad={(map) => { mapRef.current = map; map.fitBounds(CHI_BOUNDS, { padding: FIT_PADDING, duration: 0 }); }}
        />
      </div>

      <div className="controls" style={{ right: selection ? 406 : 18 }}>
        <button className={`toggle ${showColoring ? "on" : ""}`} onClick={() => setShowColoring((v) => !v)}>
          ▤ Area colors
        </button>
        <button className={`toggle ${showPins ? "on" : ""}`} onClick={() => setShowPins((v) => !v)}>
          ◍ Schools
        </button>
        <button className={`toggle ${showRail ? "on" : ""}`} onClick={() => setShowRail((v) => !v)}>
          ◆ CTA &lsquo;L&rsquo;
        </button>
        <button className={`toggle ${showBus ? "on" : ""}`} onClick={() => setShowBus((v) => !v)}>
          ▦ Buses
        </button>
      </div>

      {showColoring && (
        <div className="profile-legend">
          <div className="profile-legend-title">Community area groups</div>
          <div className="profile-legend-note">Grouped by school outcomes, school supply, and access.</div>
          {clusterLegend.map((group) => (
            <span key={group.id} title={group.description}><i style={{ background: group.color }} />{group.label}</span>
          ))}
        </div>
      )}

      {(showRail || showBus) && (
        <div className="transit-legend">
          <div className="profile-legend-title">Transit network</div>
          {showRail && (
            <>
              {railLegend.map((l) => (
                <span key={l.route}><i className="line-swatch" style={{ background: l.color }} />{l.route}</span>
              ))}
              <span><i className="station-swatch" />&lsquo;L&rsquo; station</span>
            </>
          )}
          {showBus && (
            <span><i className="line-swatch" style={{ background: `repeating-linear-gradient(90deg, ${BUS_COLOR} 0 4px, transparent 4px 7px)` }} />Bus route (all CTA)</span>
          )}
        </div>
      )}

      <InfoPanel
        open={!!selection}
        selection={selection}
        refs={refs}
        onOpenSchool={openSchool}
        onClose={() => { setSelection(null); setConnector(null); setConnectorLabels([]); }}
      />
    </div>
  );
}
