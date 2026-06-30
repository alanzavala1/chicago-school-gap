// MapView draws the MapLibre map: the community-area choropleth, school pins,
// the CTA rail/bus context layers, the click-to-route lines with time labels, and
// the community-area name labels. App owns the data and state; this just renders
// it and forwards hover/click events back up.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, { Source, Layer, Marker, Popup, type MapRef, type ViewState, type MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { Map as MaplibreMap } from "maplibre-gl";
import type { FeatureCollection, Point } from "geojson";
import { fillColor, type LayerDef } from "../layers";

const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

type SchoolFeatureProps = {
  school_id?: string | number;
  name?: string;
  type?: string;
  is_selective?: boolean | string;
  sat_g11?: number | null;
  grad_4yr?: number | null;
  pct_low_income?: number | null;
  [key: string]: unknown;
};

type HoverSchool = { id: string; lng: number; lat: number; props: SchoolFeatureProps };
type CommunityLabelProps = { name: string; area_weight: number; tract_count: number; label_rank: number };
type ClusterLegendItem = { id: string; label: string; color: string };
// Loose enough that panning never rubber-bands against the city; just keeps you near Chicago.
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [-88.25, 41.45], [-87.20, 42.20],
];
const HOVER_CLEAR_MS = 80;
const OTHER_PIN_MIN_ZOOM = 10.95;
const COMMUNITY_LABEL_MAJOR_MAX_RANK = 18;
const COMMUNITY_LABEL_MID_MAX_RANK = 44;
const isSelectiveSchool = (value: unknown) => value === true || value === "true";
const schoolIdFor = (props: SchoolFeatureProps, coords: [number, number]) =>
  String(props.school_id ?? props.name ?? `${coords[0]},${coords[1]}`);

function ringCentroid(ring: [number, number][]) {
  let twiceArea = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    const cross = x1 * y2 - x2 * y1;
    twiceArea += cross;
    cx += (x1 + x2) * cross;
    cy += (y1 + y2) * cross;
  }

  if (Math.abs(twiceArea) < 1e-12) {
    const sums = ring.reduce((acc, [lng, lat]) => ({ lng: acc.lng + lng, lat: acc.lat + lat }), { lng: 0, lat: 0 });
    const count = Math.max(ring.length, 1);
    return { lng: sums.lng / count, lat: sums.lat / count, weight: 1 };
  }

  return { lng: cx / (3 * twiceArea), lat: cy / (3 * twiceArea), weight: Math.abs(twiceArea / 2) };
}

function buildCommunityLabels(tracts: FeatureCollection): FeatureCollection<Point, CommunityLabelProps> {
  const buckets = new globalThis.Map<string, { lng: number; lat: number; weight: number; tractCount: number }>();

  for (const feature of tracts.features) {
    const name = feature.properties?.community_area;
    const geometry = feature.geometry as any;
    if (typeof name !== "string" || !geometry) continue;

    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
    if (!polygons.length) continue;

    const bucket = buckets.get(name) ?? { lng: 0, lat: 0, weight: 0, tractCount: 0 };
    bucket.tractCount += 1;

    for (const polygon of polygons) {
      const outerRing = polygon?.[0] as [number, number][] | undefined;
      if (!outerRing?.length) continue;
      const centroid = ringCentroid(outerRing);
      bucket.lng += centroid.lng * centroid.weight;
      bucket.lat += centroid.lat * centroid.weight;
      bucket.weight += centroid.weight;
    }

    buckets.set(name, bucket);
  }

  const features = [...buckets.entries()]
    .filter(([, bucket]) => bucket.weight > 0)
    .sort(([, a], [, b]) => b.weight - a.weight)
    .map(([name, bucket], index) => ({
      type: "Feature" as const,
      geometry: {
        type: "Point" as const,
        coordinates: [bucket.lng / bucket.weight, bucket.lat / bucket.weight],
      },
      properties: { name, area_weight: bucket.weight, tract_count: bucket.tractCount, label_rank: index + 1 },
    }));

  return { type: "FeatureCollection", features };
}

interface Props {
  layer: LayerDef;
  tracts: FeatureCollection;
  communityAreas: FeatureCollection | null;
  schools: FeatureCollection | null;
  cityBoundary: FeatureCollection | null;      // Chicago / CPS district outline
  clusterGroups: ClusterLegendItem[];
  showColoring: boolean;                       // toggle the community-area choropleth on/off
  showPins: boolean;
  railLines: FeatureCollection | null;         // CTA 'L' lines (context layer)
  railStations: FeatureCollection | null;      // CTA 'L' stations
  showRail: boolean;
  busLines: FeatureCollection | null;          // CTA bus routes (context layer)
  showBus: boolean;
  lineFC: FeatureCollection | null;            // connector lines (role: assigned | selective | transit)
  labels?: { lng: number; lat: number; label: string; color?: string }[]; // time pills along the routes
  viewState: Partial<ViewState>;
  onMove?: (vs: ViewState) => void;
  interactive: boolean;
  hoveredId?: string | null;
  selectedId?: string | null;
  selectedCommunity?: string | null;
  onHover?: (id: string | null) => void;
  onClick?: (e: MapLayerMouseEvent) => void;
  onSchoolClick?: (props: SchoolFeatureProps, coords: [number, number]) => void;
  onLoad?: (map: MaplibreMap) => void;
  clipLeftPx?: number; // for swipe: reveal only right of this x
}

export default function MapView({
  layer, tracts, communityAreas, schools, cityBoundary, clusterGroups, showColoring, showPins, railLines, railStations, showRail, busLines, showBus, lineFC, labels, viewState, onMove, interactive,
  hoveredId, selectedId, selectedCommunity, onHover, onClick, onSchoolClick, onLoad, clipLeftPx,
}: Props) {
  const paint = useMemo(() => fillColor(layer), [layer]);
  const clusterColor = useMemo(() => {
    const match: any[] = ["match", ["get", "cluster_group"]];
    for (const group of clusterGroups) match.push(group.id, group.color);
    match.push("rgba(0,0,0,0)");
    return match;
  }, [clusterGroups]);
  const communityLabels = useMemo(() => buildCommunityLabels(communityAreas ?? tracts), [communityAreas, tracts]);
  const [pointer, setPointer] = useState(false); // pointer cursor over any clickable feature
  const [hoverSchool, setHoverSchool] = useState<HoverSchool | null>(null);
  const [hoveredCommunity, setHoveredCommunity] = useState<string | null>(null);
  const mapRef = useRef<MapRef | null>(null);
  const hoverClearTimer = useRef<number | null>(null);

  const cancelHoverClear = useCallback(() => {
    if (hoverClearTimer.current != null) {
      window.clearTimeout(hoverClearTimer.current);
      hoverClearTimer.current = null;
    }
  }, []);

  const showSchoolHover = useCallback((id: string, coords: [number, number], props: SchoolFeatureProps) => {
    cancelHoverClear();
    setPointer(true);
    setHoveredCommunity(null);
    setHoverSchool((p) => (p && p.id === id ? p : { id, lng: coords[0], lat: coords[1], props }));
    onHover?.(null);
  }, [cancelHoverClear, onHover]);

  const scheduleSchoolHoverClear = useCallback((delay = HOVER_CLEAR_MS) => {
    cancelHoverClear();
    hoverClearTimer.current = window.setTimeout(() => {
      setHoverSchool(null);
      hoverClearTimer.current = null;
    }, delay);
  }, [cancelHoverClear]);

  useEffect(() => () => cancelHoverClear(), [cancelHoverClear]);

  // School pins as HTML markers: SVG keeps the pin crisp and the grouped label avoids hover gaps.
  // or the zoom-band (past 11.5) changes — so panning doesn't re-render 170 markers.
  const currentZoom = viewState.zoom ?? 9;
  const showOtherPins = showPins && currentZoom >= OTHER_PIN_MIN_ZOOM;
  const showOtherLabels = currentZoom >= 11.5;
  const compactPins = currentZoom < 11.2;

  useEffect(() => {
    if (!showOtherPins && hoverSchool && !isSelectiveSchool(hoverSchool.props.is_selective)) {
      setPointer(false);
      setHoverSchool(null);
    }
  }, [hoverSchool, showOtherPins]);

  const schoolMarkers = useMemo(() => {
    return (schools?.features ?? []).map((f: any, index: number) => {
      if (f.geometry?.type !== "Point") return null;
      const props = (f.properties ?? {}) as SchoolFeatureProps;
      const sel = isSelectiveSchool(props.is_selective);
      if (!sel && !showOtherPins) return null;
      const c = f.geometry?.coordinates as [number, number];
      if (!c) return null;
      const id = schoolIdFor(props, c);
      const showLabel = sel || showOtherLabels;
      const hovered = hoverSchool?.id === id;
      const pinStyle = !sel ? ({ "--pin-delay": `${(index % 18) * 6}ms` } as React.CSSProperties) : undefined;
      return (
        <Marker
          key={id}
          longitude={c[0]}
          latitude={c[1]}
          anchor="bottom"
          offset={showLabel ? [0, 18] : [0, 0]}
          style={{ zIndex: hovered ? 4 : sel ? 3 : 2 }}
        >
          <button
            type="button"
            className={[
              "school-marker",
              sel ? "selective" : "other",
              hovered ? "hovered" : "",
              compactPins ? "compact" : "",
            ].filter(Boolean).join(" ")}
            aria-label={`${props.name ?? "School"}${sel ? ", selective enrollment" : ""}`}
            onMouseEnter={() => showSchoolHover(id, c, props)}
            onMouseMove={() => showSchoolHover(id, c, props)}
            onFocus={() => showSchoolHover(id, c, props)}
            onMouseLeave={() => { setPointer(false); scheduleSchoolHoverClear(); }}
            onBlur={() => { setPointer(false); scheduleSchoolHoverClear(0); }}
            onClick={(event) => {
              event.stopPropagation();
              onSchoolClick?.(props, c);
            }}
            style={pinStyle}
          >
            <svg className="pin-svg" viewBox="0 0 32 44" aria-hidden="true" focusable="false">
              <path
                className="pin-body"
                d="M16 42C12.2 35.7 4.5 27.8 4.5 17.4C4.5 10.5 9.7 5 16 5s11.5 5.5 11.5 12.4C27.5 27.8 19.8 35.7 16 42Z"
              />
              <circle className="pin-core" cx="16" cy="17.4" r="5.4" />
            </svg>
            {showLabel && <span className={`pin-label ${sel ? "sel" : ""}`}>{props.name}</span>}
          </button>
        </Marker>
      );
    });
  }, [compactPins, hoverSchool?.id, onSchoolClick, scheduleSchoolHoverClear, schools, showOtherLabels, showOtherPins, showSchoolHover]);

  // Community-area labels as HTML markers so they sit ABOVE the school-name markers
  // (GL symbol layers always paint under HTML markers). Same rank/zoom tiers as before;
  // bucketed so they only re-render when crossing a zoom threshold, not every frame.
  const labelBucket = currentZoom >= 12.75 ? 3 : currentZoom >= 11.65 ? 2 : currentZoom >= 9.2 ? 1 : 0;
  const communityLabelMarkers = useMemo(() => {
    return communityLabels.features
      .filter((f) => {
        const rank = f.properties.label_rank;
        if (rank <= COMMUNITY_LABEL_MAJOR_MAX_RANK) return labelBucket >= 1;
        if (rank <= COMMUNITY_LABEL_MID_MAX_RANK) return labelBucket >= 2;
        return labelBucket >= 3;
      })
      .map((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const rank = f.properties.label_rank;
        const tier = rank <= COMMUNITY_LABEL_MAJOR_MAX_RANK ? "major" : rank <= COMMUNITY_LABEL_MID_MAX_RANK ? "mid" : "local";
        return (
          <Marker key={f.properties.name} longitude={lng} latitude={lat} style={{ zIndex: 6, pointerEvents: "none" }}>
            <span className={`community-label ${tier}`}>{f.properties.name}</span>
          </Marker>
        );
      });
  }, [communityLabels, labelBucket]);

  // "marching ants" animation on the dashed selective connector line (runs while one is drawn)
  useEffect(() => {
    if (!lineFC) return;
    const seq = [
      [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5],
      [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2],
      [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5],
    ];
    let raf = 0, step = -1;
    const tick = (t: number) => {
      const map = mapRef.current?.getMap();
      if (map && map.getLayer("connector-transit")) {
        const s = Math.floor((t / 55) % seq.length);
        if (s !== step) { map.setPaintProperty("connector-transit", "line-dasharray", seq[s]); step = s; }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [lineFC]);

  const containerStyle: React.CSSProperties = {
    position: "absolute", inset: 0,
    pointerEvents: interactive ? "auto" : "none",
    ...(clipLeftPx != null ? { clipPath: `inset(0 0 0 ${clipLeftPx}px)` } : {}),
  };

  return (
    <div style={containerStyle}>
      <Map
        ref={mapRef}
        {...viewState}
        onMove={onMove ? (e) => onMove(e.viewState) : undefined}
        mapStyle={BASEMAP}
        maxBounds={MAX_BOUNDS}
        minZoom={8.5}
        maxZoom={15}
        dragRotate={false}
        touchPitch={false}
        onLoad={onLoad ? (e) => onLoad(e.target) : undefined}
        interactiveLayerIds={interactive ? ["pins-selective", "pins-other", "tract-fill"] : []}
        onMouseMove={
          interactive
            ? (e: MapLayerMouseEvent) => {
                const f = e.features?.[0];
                setPointer(!!f);
                if (f && typeof f.layer?.id === "string" && f.layer.id.startsWith("pins")) {
                  const c = (f.geometry as any).coordinates as [number, number];
                  const props = (f.properties ?? {}) as SchoolFeatureProps;
                  setHoveredCommunity(null);
                  showSchoolHover(schoolIdFor(props, c), c, props);
                } else {
                  cancelHoverClear();
                  setHoverSchool((p) => (p ? null : p));
                  setHoveredCommunity(typeof f?.properties?.community_area === "string" ? f.properties.community_area : null);
                  onHover?.(f?.properties?.geoid ?? null);
                }
              }
            : undefined
        }
        onMouseLeave={interactive ? () => { setPointer(false); setHoveredCommunity(null); onHover?.(null); setHoverSchool(null); cancelHoverClear(); } : undefined}
        onClick={interactive ? onClick : undefined}
        cursor={pointer ? "pointer" : "default"}
      >
        <Source id="tracts" type="geojson" data={tracts} promoteId="geoid">
          {/* transparent click/hover target */}
          <Layer id="tract-fill" type="fill" paint={{ "fill-color": paint, "fill-opacity": 0 }} />
          {/* hover = brighten (keeps the data color readable); skips the selected zone */}
          <Layer
            id="tract-hover-fill"
            type="fill"
            filter={["all",
              ["==", ["get", "geoid"], hoveredId ?? "__none__"],
              ["!=", ["get", "geoid"], selectedId ?? "__nosel__"],
            ]}
            paint={{ "fill-color": "#ffffff", "fill-opacity": 0.12 }}
          />
          {/* selected = stronger brighten; stays locked until close or another click */}
          <Layer
            id="tract-selected-fill"
            type="fill"
            filter={["==", ["get", "geoid"], selectedId ?? "__none__"]}
            paint={{ "fill-color": "#ffffff", "fill-opacity": 0.22 }}
          />
          <Layer
            id="tract-borders"
            type="line"
            paint={{ "line-color": "rgba(168,120,255,0.1)", "line-width": 0.4 }}
          />
          {/* hover = a bright version of the outline color */}
          <Layer
            id="tract-hover"
            type="line"
            filter={["==", ["get", "geoid"], hoveredId ?? "__none__"]}
            paint={{ "line-color": "#c29bff", "line-width": 2.2 }}
          />
          {/* selected = the brightest outline, persists while the card is open */}
          <Layer
            id="tract-selected"
            type="line"
            filter={["==", ["get", "geoid"], selectedId ?? "__none__"]}
            paint={{ "line-color": "#dcc6ff", "line-width": 3.2, "line-blur": 0.2 }}
          />
        </Source>

        {communityAreas && (
          <Source id="community-areas" type="geojson" data={communityAreas} promoteId="name">
            <Layer
              id="community-cluster-fill"
              type="fill"
              paint={{
                "fill-color": clusterColor,
                "fill-opacity": showColoring ? 0.74 : 0,
                "fill-color-transition": { duration: 450, delay: 0 },
                "fill-opacity-transition": { duration: 250, delay: 0 },
              } as any}
            />
            {/* hover/selection stay visible whether or not the choropleth is on */}
            <Layer
              id="community-hover-fill"
              type="fill"
              filter={["==", ["get", "name"], hoveredCommunity ?? "__none__"]}
              paint={{ "fill-color": "#ffffff", "fill-opacity": 0.12 }}
            />
            <Layer
              id="community-selected-fill"
              type="fill"
              filter={["==", ["get", "name"], selectedCommunity ?? "__none__"]}
              paint={{ "fill-color": "#ffffff", "fill-opacity": 0.16, "fill-opacity-transition": { duration: 150, delay: 0 } } as any}
            />
            <Layer
              id="community-cluster-borders"
              type="line"
              paint={{
                "line-color": "rgba(255,255,255,0.2)",
                "line-width": showColoring ? 1.15 : 0,
                "line-opacity": showColoring ? 0.78 : 0,
              }}
            />
            <Layer
              id="community-hover-line"
              type="line"
              filter={["==", ["get", "name"], hoveredCommunity ?? "__none__"]}
              paint={{ "line-color": "#ffffff", "line-width": 2.2, "line-opacity": 0.9 }}
            />
            {/* selected area: soft outer glow + crisp bright outline so it clearly pops */}
            <Layer
              id="community-selected-glow"
              type="line"
              filter={["==", ["get", "name"], selectedCommunity ?? "__none__"]}
              paint={{ "line-color": "#ffe27a", "line-width": 10, "line-opacity": 0.3, "line-blur": 6 } as any}
            />
            <Layer
              id="community-selected-line"
              type="line"
              filter={["==", ["get", "name"], selectedCommunity ?? "__none__"]}
              paint={{ "line-color": "#ffffff", "line-width": 3.6, "line-opacity": 1, "line-blur": 0.2 } as any}
            />
          </Source>
        )}

        {cityBoundary && (
          <Source id="city-boundary" type="geojson" data={cityBoundary}>
            <Layer
              id="city-boundary-line"
              type="line"
              paint={{ "line-color": "rgba(168,120,255,0.75)", "line-width": 2.8, "line-blur": 0.3 }}
            />
          </Source>
        )}

        {lineFC && (
          <Source id="connector" type="geojson" data={lineFC}>
            {/* The two selective routes (drive + transit) share a destination, so they're
                drawn with opposite perpendicular offsets to run parallel instead of hiding
                each other. Each colored line gets a dark casing at the same offset. */}
            <Layer id="connector-assigned-casing" type="line" filter={["==", ["get", "role"], "assigned"]}
              paint={{ "line-color": "#0a0c12", "line-width": 4.6, "line-opacity": 0.5 } as any} />
            <Layer id="connector-selective-casing" type="line" filter={["==", ["get", "role"], "selective"]}
              paint={{ "line-color": "#0a0c12", "line-width": 4.6, "line-opacity": 0.5, "line-offset": -3 } as any} />
            <Layer id="connector-transit-casing" type="line" filter={["==", ["get", "role"], "transit"]}
              paint={{ "line-color": "#0a0c12", "line-width": 4.6, "line-opacity": 0.5, "line-offset": 3 } as any} />
            {/* driving route to the assigned default school = solid blue */}
            <Layer id="connector-assigned" type="line" filter={["==", ["get", "role"], "assigned"]}
              paint={{ "line-color": "#5b9dff", "line-width": 2.6, "line-opacity": 0.98 } as any} />
            {/* driving route to the nearest selective = solid amber (offset one way) */}
            <Layer id="connector-selective" type="line" filter={["==", ["get", "role"], "selective"]}
              paint={{ "line-color": "#ffb84d", "line-width": 2.6, "line-opacity": 0.98, "line-offset": -3 } as any} />
            {/* CTA transit route to the nearest selective = animated dashed green (offset the other way) */}
            <Layer id="connector-transit" type="line" filter={["==", ["get", "role"], "transit"]}
              paint={{ "line-color": "#36d39b", "line-width": 2.6, "line-dasharray": [2, 1.5], "line-opacity": 0.98, "line-offset": 3 } as any} />
          </Source>
        )}

        {/* community-area labels are rendered as HTML markers (see communityLabelMarkers)
            so they stack above the school-name markers instead of under them */}

        {interactive && labels?.map((l, i) => (
          <Marker key={i} longitude={l.lng} latitude={l.lat} style={{ zIndex: 5 }}>
            <span className="dist-pill" style={l.color ? { borderColor: l.color } : undefined}>
              {l.color && <i className="dist-dot" style={{ background: l.color }} />}
              {l.label}
            </span>
          </Marker>
        ))}

        {/* CTA bus network — light-blue dashed; dashes read as a transit overlay, not roads */}
        {busLines && (
          <Source id="cta-bus" type="geojson" data={busLines}>
            <Layer
              id="cta-bus-line"
              type="line"
              layout={{ visibility: showBus ? "visible" : "none", "line-cap": "butt", "line-join": "round" }}
              paint={{ "line-color": "#7fb6ff", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.1, 12, 1.8, 14, 2.6], "line-opacity": 0.85, "line-dasharray": [2.5, 2] } as any}
            />
          </Source>
        )}

        {/* CTA 'L' network — context layer that makes the transit-access gap legible */}
        {railLines && (
          <Source id="cta-rail" type="geojson" data={railLines}>
            {/* dark casing under the colored line keeps it legible over the choropleth */}
            <Layer
              id="cta-rail-casing"
              type="line"
              layout={{ visibility: showRail ? "visible" : "none", "line-cap": "round", "line-join": "round" }}
              paint={{ "line-color": "#0a0c12", "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.8, 14, 7], "line-opacity": 0.55 } as any}
            />
            <Layer
              id="cta-rail-line"
              type="line"
              layout={{ visibility: showRail ? "visible" : "none", "line-cap": "round", "line-join": "round" }}
              paint={{ "line-color": ["get", "color"], "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.5, 14, 4], "line-opacity": 0.92 } as any}
            />
          </Source>
        )}
        {railStations && (
          <Source id="cta-stations" type="geojson" data={railStations}>
            <Layer
              id="cta-stations-dot"
              type="circle"
              minzoom={11}
              layout={{ visibility: showRail ? "visible" : "none" }}
              paint={{
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.8, 14, 3.8],
                "circle-color": "#ffffff",
                "circle-stroke-color": "#0a0c12",
                "circle-stroke-width": 1,
                "circle-opacity": 0.92,
              } as any}
            />
          </Source>
        )}

        {schools && (
          <Source id="schools" type="geojson" data={schools}>
            {/* selective glow halo */}
            {/* other public high schools (toggled by Schools button) */}
            <Layer
              id="pins-other"
              type="circle"
              filter={["case", ["get", "is_selective"], false, true] as any}
              layout={{ visibility: showOtherPins ? "visible" : "none" }}
              paint={{
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 11, 13, 24],
                "circle-color": "#ffffff",
                "circle-opacity": 0.01,
                "circle-stroke-opacity": 0,
              }}
            />
            {/* selective schools — gold beacons */}
            <Layer
              id="pins-selective"
              type="circle"
              filter={["case", ["get", "is_selective"], true, false] as any}
              paint={{
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 14, 13, 28],
                "circle-color": "#ffffff",
                "circle-opacity": 0.01,
                "circle-stroke-opacity": 0,
              }}
            />
          </Source>
        )}

        {/* school name labels as HTML markers (reliable; selective always, others when zoomed in) */}
        {schoolMarkers}

        {/* community-area labels on top (higher z-index than school markers) */}
        {communityLabelMarkers}

        {hoverSchool && (
          <Popup
            longitude={hoverSchool.lng}
            latitude={hoverSchool.lat}
            anchor="bottom"
            offset={34}
            closeButton={false}
            closeOnClick={false}
            className="school-hover"
          >
            <div className="sh-name">{hoverSchool.props.name}</div>
            <div className="sh-type">
              {hoverSchool.props.is_selective === true || hoverSchool.props.is_selective === "true"
                ? "★ Selective enrollment"
                : hoverSchool.props.type}
            </div>
            <div className="sh-row">
              <span>SAT <b>{hoverSchool.props.sat_g11 ? Math.round(hoverSchool.props.sat_g11) : "—"}</b></span>
              <span>Grad <b>{hoverSchool.props.grad_4yr != null ? `${Math.round(hoverSchool.props.grad_4yr)}%` : "—"}</b></span>
              <span>Low-income <b>{hoverSchool.props.pct_low_income != null ? `${Math.round(hoverSchool.props.pct_low_income)}%` : "—"}</b></span>
            </div>
            <div className="sh-hint">click for full details</div>
          </Popup>
        )}
      </Map>
    </div>
  );
}
