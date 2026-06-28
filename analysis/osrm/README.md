# OSRM — driving-time engine (build-time only)

A local [OSRM](https://project-osrm.org/) container that computes **real
road-network driving times** from each Chicago tract to each CPS high school,
replacing the straight-line distance proxy in Finding 2's access metrics.

Like the PostGIS container, this is a **build-time analysis tool**. Its results
are baked into `output/driving_*` (static files); nothing here ships to
production. The deployed map stays a static site (see PROJECT_OVERVIEW §4).

## Run it

```bash
bash analysis/osrm/osrm_up.sh          # download extract + build graph + serve :5000
python analysis/14_driving_access.py   # tract->school driving matrix + validation
docker rm -f chicago-osrm              # stop when done
```

`osrm_up.sh` is idempotent: it skips the download and graph build if already
present (delete `data/osrm/.built` to force a rebuild).

## What it produces

- `output/driving_times_selective.csv` — tract × selective-school driving long matrix (the reusable core).
- `output/driving_access.json` — per-tract driving analogues of the Finding-2 access fields
  (`nearest_selective_drive_min`, `drive_min_to_nearest_elite`, `n_selective_within_15min`, …).

The script validates against the existing straight-line metrics (correlation)
and re-runs the headline — drive time to the nearest elite selective by
neighborhood %Black quartile — in real minutes.

## Notes / limits

- **Driving assumes a car.** This is one access lens; the transit lens (the
  burden for car-free families) is the next stage.
- Default extract is BBBike's Chicago (`~100 MB`). If the validation step reports
  unrouted tracts, rerun with the statewide Geofabrik extract for fuller coverage:
  `PBF_URL=https://download.geofabrik.de/north-america/us/illinois-latest.osm.pbf bash analysis/osrm/osrm_up.sh`
- Origins are tract internal points (`intptlon/intptlat`) — the same points
  `07_finding2.sql` uses — so straight-line and driving metrics are directly comparable.
- This stage produces the comparable matrix; wiring real drive time into
  `07_finding2.sql` / the exported layers is the following step.
