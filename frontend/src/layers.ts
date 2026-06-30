// Single source of truth for the choropleth variables. Each entry drives the layer
// switcher, the MapLibre fill-color paint expression, and the legend — change it here,
// it changes everywhere. Colors chosen to read well on a dark basemap.

export type TractProps = {
  geoid: string;
  community_area: string | null;
  median_hh_income: number | null;
  pct_black: number | null;
  pct_hispanic: number | null;
  pct_white: number | null;
  poverty_rate: number | null;
  assigned_school: string | null;
  assigned_sat: number | null;
  assigned_attendance: number | null;
  assigned_truancy: number | null;
  assigned_grad: number | null;
  assigned_college: number | null;
  assigned_ontrack: number | null;
  nearest_selective_mi: number | null;
  sat_of_nearest_selective: number | null;
  miles_to_nearest_elite: number | null;
  n_selective_within_3mi: number | null;
  // real routed travel time (OSRM driving / OTP CTA transit); straight-line above stays for comparison
  drive_min_to_nearest_elite: number | null;
  transit_min_to_nearest_elite: number | null;
  n_selective_within_30min_transit: number | null;
  // the single CLOSEST selective (one school) + drive/CTA time to it — matches the drawn routes
  closest_selective: string | null;
  closest_selective_mi: number | null;
  closest_selective_sat: number | null;
  closest_selective_drive_min: number | null;
  closest_selective_transit_min: number | null;
  combined_status: string | null;
  distress: number | null;
  distress_rank: number | null;
  national_gap: number | null;
  default_index: number | null;
  access_index: number | null;
  cluster_group?: string | null;
};

export type SchoolProps = {
  school_id: string;
  name: string;
  long_name: string | null;
  type: string;
  is_selective: boolean;
  address: string | null;
  community_area: string | null;
  sat_g11: number | null;
  attendance: number | null;
  truancy: number | null;
  grad_4yr: number | null;
  college_enroll: number | null;
  freshman_ontrack: number | null;
  enrollment: number | null;
  pct_low_income: number | null;
  pct_black: number | null;
  pct_hispanic: number | null;
  pct_white: number | null;
};

type Stops = [number, string][];

export interface LayerDef {
  id: keyof TractProps;
  label: string;
  group: string;
  kind: "sequential" | "categorical";
  blurb: string;
  fmt: (v: number) => string;
  stops?: Stops; // sequential
  cats?: { value: string; label: string; color: string }[]; // categorical
}

// Perceptually-uniform ramps (viridis / plasma family) — colorblind-safe, vivid on dark.
const VIRIDIS: string[] = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"];
// Quality ramp: low = warm red (bad) -> high = cyan/green (good). Intuitive for schools.
const QUALITY: string[] = ["#d1495b", "#e8836b", "#edc79b", "#7fc8a9", "#2a9d8f", "#1b8a9c"];

const ramp = (vals: number[], colors: string[]): Stops =>
  vals.map((v, i) => [v, colors[i]] as [number, string]);

const pct = (v: number) => `${Math.round(v)}%`;
const dollars = (v: number) => `$${Math.round(v).toLocaleString()}`;
const sat = (v: number) => `${Math.round(v)}`;
const miles = (v: number) => `${v.toFixed(1)} mi`;

const DEMO = "Neighborhood demographics";
const SCHOOL = "Assigned high school";
const ACCESS = "Selective-enrollment access";
const VERDICT = "Combined assessment";

export const LAYERS: LayerDef[] = [
  {
    id: "pct_black", label: "Share Black", group: DEMO, kind: "sequential",
    blurb: "Percent of residents who are Black (non-Hispanic), from ACS 2020–24. In this analysis it is the single strongest correlate of assigned-school quality.",
    fmt: pct, stops: ramp([0, 20, 40, 60, 80, 100], VIRIDIS),
  },
  {
    id: "pct_hispanic", label: "Share Hispanic", group: DEMO, kind: "sequential",
    blurb: "Percent of residents who are Hispanic or Latino (any race).",
    fmt: pct, stops: ramp([0, 20, 40, 60, 80, 100], VIRIDIS),
  },
  {
    id: "pct_white", label: "Share White", group: DEMO, kind: "sequential",
    blurb: "Percent of residents who are White (non-Hispanic).",
    fmt: pct, stops: ramp([0, 20, 40, 60, 80, 100], VIRIDIS),
  },
  {
    id: "median_hh_income", label: "Median household income", group: DEMO, kind: "sequential",
    blurb: "ACS median household income. In Chicago this closely tracks racial composition, which is why it appears to predict school quality.",
    fmt: dollars, stops: ramp([20000, 45000, 70000, 100000, 140000, 200000], VIRIDIS),
  },
  {
    id: "poverty_rate", label: "Poverty rate", group: DEMO, kind: "sequential",
    blurb: "Percent of residents living below the federal poverty line.",
    fmt: pct, stops: ramp([0, 10, 20, 30, 40, 55], VIRIDIS),
  },
  {
    id: "assigned_sat", label: "Assigned-school SAT", group: SCHOOL, kind: "sequential",
    blurb: "Average grade-11 SAT score at the public high school this neighborhood is assigned to by address. Higher is stronger.",
    fmt: sat, stops: ramp([716, 800, 850, 900, 1000, 1081], QUALITY),
  },
  {
    id: "assigned_truancy", label: "Assigned-school chronic truancy", group: SCHOOL, kind: "sequential",
    blurb: "Chronic-truancy rate at the assigned high school. Lower is stronger.",
    fmt: pct, stops: ramp([15, 45, 60, 70, 80, 95], [...QUALITY].reverse()),
  },
  {
    id: "sat_of_nearest_selective", label: "Nearest selective school: SAT", group: ACCESS, kind: "sequential",
    blurb: "Average SAT of the closest selective-enrollment school — the strongest selective option within easy reach.",
    fmt: sat, stops: ramp([900, 1000, 1080, 1150, 1250, 1334], QUALITY),
  },
  {
    id: "miles_to_nearest_elite", label: "Distance to a top selective school", group: ACCESS, kind: "sequential",
    blurb: "Straight-line distance to the nearest top-scoring selective school (SAT ≥ 1250). Lower is better access.",
    fmt: miles, stops: ramp([1, 3, 5, 7, 9, 12], [...QUALITY].reverse()),
  },
  {
    id: "combined_status", label: "Combined assessment", group: VERDICT, kind: "categorical",
    blurb: "Neighborhoods ranked into thirds on assigned-school quality and on nearby selective quality. Worst third on both = least access; best third on both = most access.",
    fmt: (v) => `${v}`,
    cats: [
      { value: "double_disadvantage", label: "Weak school + weak access", color: "#e23b3b" },
      { value: "single_disadvantage", label: "Weak on one measure", color: "#f0883e" },
      { value: "middle", label: "Middle", color: "#5b6472" },
      { value: "double_advantage", label: "Strong school + strong access", color: "#3b82f6" },
    ],
  },
];

export const NULL_COLOR = "#191d27";

// Build the MapLibre fill-color expression for a layer (guards null -> NULL_COLOR).
export function fillColor(layer: LayerDef): any {
  if (layer.kind === "categorical") {
    const match: any[] = ["match", ["get", layer.id]];
    for (const c of layer.cats!) match.push(c.value, c.color);
    match.push(NULL_COLOR);
    return match;
  }
  const interp: any[] = ["interpolate", ["linear"], ["to-number", ["get", layer.id]]];
  for (const [v, c] of layer.stops!) interp.push(v, c);
  return ["case", ["==", ["typeof", ["get", layer.id]], "number"], interp, NULL_COLOR];
}
