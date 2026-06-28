import type { ReactNode } from "react";
import { type TractProps, type SchoolProps } from "../layers";

export type ClusterDriver = {
  key: string;
  label: string;
  metric: string;
  direction: "high" | "low";
  z: number;
  tone: "bad" | "good" | "neutral";
};

export type CommunityCluster = {
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

export type CommunitySummary = {
  name: string;
  cluster: CommunityCluster | null;
  tractCount: number;
  assignedSchools: { name: string; count: number; share: number }[];
  schools: SchoolProps[];
  schoolTypeCounts: { label: string; count: number }[];
  schoolMetrics: Pick<SchoolProps,
    "sat_g11" | "grad_4yr" | "college_enroll" | "freshman_ontrack" |
    "attendance" | "truancy"
  >;
  metrics: Pick<TractProps,
    "median_hh_income" | "poverty_rate" | "pct_black" | "pct_hispanic" | "pct_white" |
    "assigned_sat" | "assigned_grad" | "assigned_college" | "assigned_ontrack" |
    "assigned_attendance" | "assigned_truancy" | "nearest_selective_mi" |
    "sat_of_nearest_selective" | "miles_to_nearest_elite" | "n_selective_within_3mi" |
    "drive_min_to_nearest_elite" | "transit_min_to_nearest_elite" |
    "n_selective_within_30min_transit" |
    "national_gap" | "default_index" | "access_index"
  >;
  flags: { label: string; tone: "bad" | "warn" | "good" }[];
};

export type Selection =
  | {
    kind: "hood";
    props: TractProps;
    community: CommunitySummary | null;
    nearest: { name: string; sat: number | null; miles: number } | null;
    nearestStrong: { name: string; sat: number | null; miles: number } | null;
    address: string | null;
    assignedMiles: number | null;
  }
  | { kind: "school"; props: SchoolProps };

const fmtPct = (v: number | null) => (v == null ? "-" : `${Number(v).toFixed(v % 1 ? 1 : 0)}%`);
const fmtNum = (v: number | null) => (v == null ? "-" : Math.round(v).toLocaleString());
const fmtMoney = (v: number | null) => (v == null ? "no data" : `$${Math.round(v).toLocaleString()}`);
const fmtMiles = (v: number | null) => (v == null ? "-" : `${v.toFixed(1)} mi`);
const fmtMin = (v: number | null) => (v == null ? "-" : `${Math.round(v)} min`);
// tone for a transit time: green under `warn`, amber up to `bad`, red beyond.
const travelTone = (v: number | null, warn: number, bad: number) =>
  v == null ? "" : v >= bad ? "bad" : v >= warn ? "warn" : "good";

const NATIONAL_BENCHMARKS = {
  sat: 1010,
  grad: 87,
  college: 62,
};

export type Refs = {
  medianIncome: number | null;
  medianAssignedSat: number | null;
  schoolSats: number[];
  schoolMedians: {
    sat: number | null;
    grad: number | null;
    college: number | null;
    ontrack: number | null;
    attendance: number | null;
    truancy: number | null;
  };
};

function vsCity(
  value: number | null,
  ref: number | null,
  lower = "below",
  higher = "above",
  label = "the city median"
) {
  if (value == null || ref == null) return null;
  const diff = Math.round((Math.abs(value - ref) / ref) * 100);
  if (diff < 3) return `about ${label}`;
  return `${diff}% ${value < ref ? lower : higher} ${label}`;
}

function toneFor(value: number | null, ref: number | null, higherIsBetter = true) {
  if (value == null || ref == null) return "neutral" as const;
  const diff = (value - ref) / ref;
  if (Math.abs(diff) < 0.03) return "neutral" as const;
  const better = higherIsBetter ? diff > 0 : diff < 0;
  return better ? "good" as const : "bad" as const;
}

function Stat({ k, v, note }: { k: string; v: string; note?: string | null }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span style={{ textAlign: "right" }}>
        <span className="v">{v}</span>
        {note && <span className="statnote">{note}</span>}
      </span>
    </div>
  );
}

function MetricCard({ label, value, note, tone = "neutral" }: {
  label: string;
  value: string;
  note?: string | null;
  tone?: "neutral" | "good" | "bad" | "warn";
}) {
  return (
    <div className={`metric-card ${tone}`}>
      <span>{label}</span>
      <b>{value}</b>
      {note && <em>{note}</em>}
    </div>
  );
}

function benchmarkDelta(value: number | null, benchmark: number, unit: "pts" | "sat") {
  if (value == null) return { text: "no data", tone: "neutral" as const };
  const delta = Math.round(value - benchmark);
  if (unit === "sat") {
    if (Math.abs(delta) < 10) return { text: "near benchmark", tone: "neutral" as const };
    return {
      text: `${Math.abs(delta)} ${delta < 0 ? "below" : "above"} benchmark`,
      tone: delta < 0 ? "bad" as const : "good" as const,
    };
  }
  if (Math.abs(delta) < 2) return { text: "near benchmark", tone: "neutral" as const };
  return {
    text: `${Math.abs(delta)} pts ${delta < 0 ? "below" : "above"} benchmark`,
    tone: delta < 0 ? "bad" as const : "good" as const,
  };
}

function NationalBenchmarks({ sat, grad, college }: {
  sat: number | null;
  grad: number | null;
  college: number | null;
}) {
  const satDelta = benchmarkDelta(sat, NATIONAL_BENCHMARKS.sat, "sat");
  const gradDelta = benchmarkDelta(grad, NATIONAL_BENCHMARKS.grad, "pts");
  const collegeDelta = benchmarkDelta(college, NATIONAL_BENCHMARKS.college, "pts");
  return (
    <div className="benchmark-box">
      <div className="benchmark-head">
        <span>National benchmarks</span>
        <em>SAT, graduation, college only</em>
      </div>
      <div className="benchmark-grid">
        <div className={satDelta.tone}>
          <span>SAT 1010</span>
          <b>{fmtNum(sat)}</b>
          <em>{satDelta.text}</em>
        </div>
        <div className={gradDelta.tone}>
          <span>Grad 87%</span>
          <b>{fmtPct(grad)}</b>
          <em>{gradDelta.text}</em>
        </div>
        <div className={collegeDelta.tone}>
          <span>College 62%</span>
          <b>{fmtPct(college)}</b>
          <em>{collegeDelta.text}</em>
        </div>
      </div>
    </div>
  );
}

const COMP = [
  { key: "pct_black", label: "Black", color: "#5b9dff" },
  { key: "pct_hispanic", label: "Hispanic", color: "#ffb84d" },
  { key: "pct_white", label: "White", color: "#cfd6e2" },
] as const;

function CompositionBar({ data }: { data: { pct_black: number | null; pct_hispanic: number | null; pct_white: number | null } }) {
  const segs = COMP.map((c) => ({ ...c, v: data[c.key] ?? 0 }));
  const other = Math.max(0, 100 - segs.reduce((s, x) => s + x.v, 0));
  const all = [...segs, { key: "other", label: "Other", color: "#3a4150", v: other }];
  return (
    <div style={{ marginTop: 6 }}>
      <div className="compbar">
        {all.map((s) => s.v > 0 && (
          <span key={s.key} style={{ width: `${s.v}%`, background: s.color }} title={`${s.label} ${Math.round(s.v)}%`} />
        ))}
      </div>
      <div className="complegend">
        {all.filter((s) => s.v >= 1).map((s) => (
          <span key={s.key}><i style={{ background: s.color }} />{s.label} {Math.round(s.v)}%</span>
        ))}
      </div>
    </div>
  );
}

function EvidenceSection({ title, note, children, className = "" }: {
  title: string;
  note?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`evidence-section ${className}`.trim()}>
      <div className="evidence-head">
        <h3>{title}</h3>
        {note && <p>{note}</p>}
      </div>
      {children}
    </section>
  );
}

type FactItem = {
  label: string;
  value: string;
  note?: string | null;
  tone?: "neutral" | "good" | "bad" | "warn";
};

function FactList({ items }: { items: FactItem[] }) {
  return (
    <div className="fact-list">
      {items.map((item) => (
        <div className={`fact-row ${item.tone ?? "neutral"}`} key={item.label}>
          <span>{item.label}</span>
          <b>{item.value}</b>
          {item.note && <em>{item.note}</em>}
        </div>
      ))}
    </div>
  );
}

function HoodView({ props, community, nearestStrong, address, assignedMiles, refs, onOpenSchool }: {
  props: TractProps;
  community: CommunitySummary | null;
  nearestStrong: { name: string; sat: number | null; miles: number } | null;
  address: string | null;
  assignedMiles: number | null;
  onOpenSchool: (name: string) => void;
  refs: Refs;
}) {
  const place = community?.name ?? props.community_area ?? `Census tract ${props.geoid?.slice(-6)}`;
  const metrics = community?.metrics ?? props;
  const schoolMetrics = community?.schoolMetrics;
  const outcomeMetrics = schoolMetrics ?? {
    sat_g11: metrics.assigned_sat,
    grad_4yr: metrics.assigned_grad,
    college_enroll: metrics.assigned_college,
    freshman_ontrack: metrics.assigned_ontrack,
    attendance: metrics.assigned_attendance,
    truancy: metrics.assigned_truancy,
  };
  const schoolsInArea = community?.schools ?? [];
  const assignedSchools = community?.assignedSchools ?? (props.assigned_school ? [{ name: props.assigned_school, count: 1, share: 1 }] : []);
  const m = refs.schoolMedians;
  const HS = "the city HS median";
  const topAssigned = assignedSchools[0];

  return (
    <>
      <div className="community-head">
        <div>
          <div className="eyebrow">Community area</div>
          <h2>{place}</h2>
        </div>
        <div className="tract-count">
          <b>{community?.tractCount ?? 1}</b>
          <span>tracts</span>
        </div>
      </div>
      <div className="subline">{address ? `Clicked near ${address}` : "Click location summarized with community-area data"}</div>

      <EvidenceSection title="Area group" note="Community areas grouped by k-means clustering on four school-access measures: assigned-school strength, strength of schools located here, number of high schools, and selective access. Race and income are not inputs to the model.">
        {community?.cluster ? (
          <div className="cluster-card" style={{ borderColor: community.cluster.group_color }}>
            <div className="cluster-card-top">
              <span className="cluster-color" style={{ background: community.cluster.group_color }} />
              <b>{community.cluster.group_label}</b>
            </div>
            <p>{community.cluster.group_description}</p>
            <div className="driver-head compact">
              <span>Main group drivers</span>
            </div>
            <div className="driver-list">
              {community.cluster.drivers.map((driver) => (
                <span className={`driver-chip ${driver.tone}`} key={driver.key}>{driver.label}</span>
              ))}
            </div>
            {community.cluster.similar_communities.length > 0 && (
              <div className="similar-line">
                Similar areas: {community.cluster.similar_communities.slice(0, 3).join(", ")}
              </div>
            )}
          </div>
        ) : (
          <div className="schoolcard"><div className="sub">No community grouping loaded for this area.</div></div>
        )}
      </EvidenceSection>

      <EvidenceSection title="Schools located here" note="CPS high schools physically inside this area, with outcomes compared against the citywide high-school median.">
        {schoolsInArea.length ? (
          <>
            <FactList items={[
              { label: "High schools", value: fmtNum(schoolsInArea.length), note: community?.schoolTypeCounts.length ? community.schoolTypeCounts.map((x) => `${x.count} ${x.label}`).join(" / ") : null },
              { label: "Average SAT", value: fmtNum(outcomeMetrics.sat_g11), note: vsCity(outcomeMetrics.sat_g11, m.sat, "below", "above", HS), tone: toneFor(outcomeMetrics.sat_g11, m.sat) },
              { label: "Graduation", value: fmtPct(outcomeMetrics.grad_4yr), note: vsCity(outcomeMetrics.grad_4yr, m.grad, "below", "above", HS), tone: toneFor(outcomeMetrics.grad_4yr, m.grad) },
              { label: "College enrollment", value: fmtPct(outcomeMetrics.college_enroll), note: vsCity(outcomeMetrics.college_enroll, m.college, "below", "above", HS), tone: toneFor(outcomeMetrics.college_enroll, m.college) },
              { label: "Freshmen on-track", value: fmtPct(outcomeMetrics.freshman_ontrack), note: vsCity(outcomeMetrics.freshman_ontrack, m.ontrack, "below", "above", HS), tone: toneFor(outcomeMetrics.freshman_ontrack, m.ontrack) },
              { label: "Attendance", value: fmtPct(outcomeMetrics.attendance), note: vsCity(outcomeMetrics.attendance, m.attendance, "below", "above", HS), tone: toneFor(outcomeMetrics.attendance, m.attendance) },
              { label: "Chronic truancy", value: fmtPct(outcomeMetrics.truancy), note: vsCity(outcomeMetrics.truancy, m.truancy, "below", "above", HS), tone: toneFor(outcomeMetrics.truancy, m.truancy, false) },
            ]} />
            <NationalBenchmarks sat={outcomeMetrics.sat_g11} grad={outcomeMetrics.grad_4yr} college={outcomeMetrics.college_enroll} />
            <div className="school-table compact-list">
              {schoolsInArea.map((school) => (
                <button type="button" onClick={() => onOpenSchool(school.name)} key={school.school_id}>
                  <span>
                    <b>{school.name}</b>
                    <em>{school.type}{school.is_selective ? " - selective enrollment" : ""}</em>
                  </span>
                  <span>SAT {fmtNum(school.sat_g11)}</span>
                  <span>Grad {fmtPct(school.grad_4yr)}</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="schoolcard empty-state">
            <div className="nm">No CPS high school located in this community area</div>
            <div className="sub">Assigned schools and access measures are shown below.</div>
          </div>
        )}
      </EvidenceSection>

      <EvidenceSection title="Default (assigned) school" note="The high school assigned to an address by attendance boundary. Derived by spatial join of census tracts to boundary polygons, summarized across the area.">
        {topAssigned && (
          <button type="button" className="plain-school-link" onClick={() => onOpenSchool(topAssigned.name)}>
            <span>Most common assigned school</span>
            <b>{topAssigned.name}</b>
            <em>{Math.round(topAssigned.share * 100)}% of tracts{topAssigned.name === props.assigned_school && assignedMiles != null ? ` - ${assignedMiles.toFixed(1)} mi from clicked point` : ""}</em>
          </button>
        )}
        <FactList items={[
          { label: "Typical assigned SAT", value: fmtNum(metrics.assigned_sat), note: vsCity(metrics.assigned_sat, m.sat, "below", "above", HS), tone: toneFor(metrics.assigned_sat, m.sat) },
          { label: "Assigned graduation", value: fmtPct(metrics.assigned_grad), note: vsCity(metrics.assigned_grad, m.grad, "below", "above", HS), tone: toneFor(metrics.assigned_grad, m.grad) },
          { label: "Assigned school distance", value: fmtMiles(assignedMiles), note: props.assigned_school ?? "selected tract" },
        ]} />
        {assignedSchools.length > 1 && (
          <div className="assigned-list">
            {assignedSchools.slice(1, 4).map((school) => (
              <button type="button" onClick={() => onOpenSchool(school.name)} key={school.name}>
                <span>{school.name}</span>
                <b>{Math.round(school.share * 100)}%</b>
              </button>
            ))}
          </div>
        )}
      </EvidenceSection>

      <EvidenceSection title="Selective-school access" note="Selective-enrollment schools admit by test, outside the attendance-boundary system. Travel time by car (OSRM road routing) and by CTA (OpenTripPlanner on the bus/rail schedule, including walking, transfers, and wait time).">
        <div className="travel-compare">
          <div className="travel-row head">
            <span />
            <span className="th">By CTA</span>
            <span className="th">By car</span>
          </div>
          <div className="travel-row">
            <span className="travel-label">
              Nearest selective
              <em>{props.closest_selective ? `${props.closest_selective} · ` : ""}{fmtMiles(props.closest_selective_mi)} away</em>
            </span>
            <b className={travelTone(props.closest_selective_transit_min, 30, 45)}>{fmtMin(props.closest_selective_transit_min)}</b>
            <b className="car">{fmtMin(props.closest_selective_drive_min)}</b>
          </div>
          <div className="travel-row">
            <span className="travel-label">
              Nearest top-tier
              <em>SAT 1250+ · {fmtMiles(props.miles_to_nearest_elite)} away</em>
            </span>
            <b className={travelTone(props.transit_min_to_nearest_elite, 45, 60)}>{fmtMin(props.transit_min_to_nearest_elite)}</b>
            <b className="car">{fmtMin(props.drive_min_to_nearest_elite)}</b>
          </div>
        </div>
        <div className={`reach-line ${props.n_selective_within_30min_transit === 0 ? "bad" : "good"}`}>
          <b>{fmtNum(props.n_selective_within_30min_transit)}</b> of 11 selective schools reachable within 30 min by CTA
        </div>
        <div style={{ marginTop: 9 }}>
          <FactList items={[
            { label: "Nearest selective's SAT", value: fmtNum(props.closest_selective_sat), note: vsCity(props.closest_selective_sat, m.sat, "below", "above", HS), tone: toneFor(props.closest_selective_sat, m.sat) },
            { label: "Nearest strong school (SAT 1010+)", value: fmtMiles(nearestStrong?.miles ?? null), note: nearestStrong ? `${nearestStrong.name} - SAT ${fmtNum(nearestStrong.sat)}` : "no data", tone: nearestStrong?.miles != null && nearestStrong.miles > 5 ? "warn" : "neutral" },
          ]} />
        </div>
        <div className="route-key">
          <span><i style={{ background: "#5b9dff" }} />Route to assigned school (driving)</span>
          <span><i style={{ background: "#ffb84d" }} />Route to nearest selective (driving)</span>
          <span><i style={{ background: "#36d39b" }} />Route to nearest selective (CTA)</span>
        </div>
        <div className="transit-note">Map lines show these routes from the neighborhood center. CTA times are the median of weekday 7–8am departures. CTA only (excludes Metra and Pace).</div>
      </EvidenceSection>

      <EvidenceSection title="Demographic context" note="Race, income, and poverty, shown as context. They are not inputs to the area grouping above.">
        <CompositionBar data={metrics} />
        <div className="context-stats">
          <Stat k="Median household income" v={fmtMoney(metrics.median_hh_income)} note={vsCity(metrics.median_hh_income, refs.medianIncome)} />
          <Stat k="Poverty rate" v={fmtPct(metrics.poverty_rate)} />
        </div>
      </EvidenceSection>

      <p className="panel-caveat">
        Distances, times, and counts describe access. Selective-enrollment admission is competitive and separate from these measures.
      </p>
    </>
  );
}

function SchoolView({ s, refs }: { s: SchoolProps; refs: Refs }) {
  const m = refs.schoolMedians;
  const HS = "the city HS median";
  const pctile = s.sat_g11 != null && refs.schoolSats.length
    ? refs.schoolSats.filter((v) => v <= s.sat_g11!).length / refs.schoolSats.length
    : null;
  const tier = pctile == null ? null
    : pctile >= 0.667 ? { label: "Top third of CPS high schools", color: "#3b82f6" }
    : pctile <= 0.334 ? { label: "Bottom third of CPS high schools", color: "#e23b3b" }
    : { label: "Middle third of CPS high schools", color: "#5b6472" };
  const flags = [
    s.is_selective ? { label: "selective enrollment", tone: "good" as const } : null,
    s.sat_g11 != null && m.sat != null && s.sat_g11 < m.sat * 0.9 ? { label: "low SAT", tone: "bad" as const } : null,
    s.grad_4yr != null && m.grad != null && s.grad_4yr < m.grad * 0.9 ? { label: "low graduation", tone: "bad" as const } : null,
    s.college_enroll != null && m.college != null && s.college_enroll < m.college * 0.9 ? { label: "college gap", tone: "bad" as const } : null,
    s.truancy != null && m.truancy != null && s.truancy > m.truancy * 1.1 ? { label: "high truancy", tone: "warn" as const } : null,
    s.attendance != null && m.attendance != null && s.attendance > m.attendance * 1.05 ? { label: "strong attendance", tone: "good" as const } : null,
  ].filter((flag): flag is { label: string; tone: "bad" | "warn" | "good" } => flag != null);

  return (
    <>
      <div className="school-hero">
        <div className={`school-mark ${s.is_selective ? "selective" : ""}`}>{s.is_selective ? "SE" : "HS"}</div>
        <div>
          <div className="eyebrow">{s.type}</div>
          <h2>{s.name}</h2>
          <div className="subline">
            {s.long_name && s.long_name !== s.name ? `${s.long_name} - ` : ""}{s.community_area ?? ""}
          </div>
        </div>
      </div>
      {s.address && <div className="address-line">{s.address}, Chicago IL</div>}

      <div className="profile-row">
        {tier && <span className="statusbadge" style={{ background: tier.color }}>{tier.label}</span>}
        {flags.map((flag) => <span className={`flag ${flag.tone}`} key={flag.label}>{flag.label}</span>)}
      </div>

      <div className="section-title">Academic outcomes</div>
      <div className="metric-grid">
        <MetricCard label="SAT grade 11" value={fmtNum(s.sat_g11)} note={vsCity(s.sat_g11, m.sat, "below", "above", HS)} tone={toneFor(s.sat_g11, m.sat)} />
        <MetricCard label="4-year graduation" value={fmtPct(s.grad_4yr)} note={vsCity(s.grad_4yr, m.grad, "below", "above", HS)} tone={toneFor(s.grad_4yr, m.grad)} />
        <MetricCard label="College enrollment" value={fmtPct(s.college_enroll)} note={vsCity(s.college_enroll, m.college, "below", "above", HS)} tone={toneFor(s.college_enroll, m.college)} />
        <MetricCard label="Freshmen on-track" value={fmtPct(s.freshman_ontrack)} note={vsCity(s.freshman_ontrack, m.ontrack, "below", "above", HS)} tone={toneFor(s.freshman_ontrack, m.ontrack)} />
      </div>

      <NationalBenchmarks sat={s.sat_g11} grad={s.grad_4yr} college={s.college_enroll} />

      <div className="section-title">Attendance & climate</div>
      <div className="metric-grid compact">
        <MetricCard label="Average attendance" value={fmtPct(s.attendance)} note={vsCity(s.attendance, m.attendance, "below", "above", HS)} tone={toneFor(s.attendance, m.attendance)} />
        <MetricCard label="Chronic truancy" value={fmtPct(s.truancy)} note={vsCity(s.truancy, m.truancy, "below", "above", HS)} tone={toneFor(s.truancy, m.truancy, false)} />
      </div>

      <div className="section-title">Students</div>
      <div className="student-strip">
        <div>
          <span>Total enrollment</span>
          <b>{fmtNum(s.enrollment)}</b>
        </div>
        <div>
          <span>Low-income</span>
          <b>{fmtPct(s.pct_low_income)}</b>
        </div>
      </div>
      <div style={{ marginTop: 12 }}><CompositionBar data={s} /></div>

      <p className="panel-caveat">
        Source: CPS School Progress Report (SY2024-25) and School Profile. Outcomes reflect enrolled
        students and school programs.
      </p>
    </>
  );
}

export default function InfoPanel({
  open, selection, refs, onOpenSchool, onClose,
}: {
  open: boolean;
  selection: Selection | null;
  refs: Refs;
  onOpenSchool: (name: string) => void;
  onClose: () => void;
}) {
  return (
    <div className={`panel ${open ? "open" : ""}`}>
      <button className="close" onClick={onClose} aria-label="Close">x</button>
      {selection && (
        <div className="panel-inner">
          {selection.kind === "hood"
            ? <HoodView props={selection.props} community={selection.community} nearestStrong={selection.nearestStrong} address={selection.address} assignedMiles={selection.assignedMiles} onOpenSchool={onOpenSchool} refs={refs} />
            : <SchoolView s={selection.props} refs={refs} />}
        </div>
      )}
    </div>
  );
}
