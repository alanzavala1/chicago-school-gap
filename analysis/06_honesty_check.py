"""
Finding-1 honesty check: is it neighborhood INCOME that predicts the quality of the
assigned default high school, or is income just standing in for racial / poverty
composition (which is deeply collinear with income in Chicago)?

Pulls the tract-level dataset from PostGIS (psql COPY -> CSV, no DB driver needed) and
runs bivariate correlations, a predictor collinearity matrix, standardized OLS, and a
partial correlation of income vs SAT controlling for race+poverty. numpy only.
"""
import subprocess, io, sys
import numpy as np
import pandas as pd

SQL = """COPY (
  SELECT ta.geoid, ta.assigned_sat,
         i.median_hh_income, d.poverty_rate, d.pct_black, d.pct_hispanic, d.pct_white_nh
  FROM tract_assignment ta
  JOIN acs_income i        ON i.geoid = ta.geoid
  JOIN acs_demographics d  ON d.geoid = ta.geoid
  WHERE ta.assigned_sat IS NOT NULL AND i.median_hh_income IS NOT NULL
        AND d.poverty_rate IS NOT NULL AND d.pct_black IS NOT NULL
) TO STDOUT WITH CSV HEADER"""


def fetch():
    out = subprocess.run(
        ["docker", "exec", "chicago-postgis", "psql", "-U", "postgres", "-d", "school_gap",
         "-c", SQL], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql error:\n" + out.stderr)
    return pd.read_csv(io.StringIO(out.stdout))


def zscore(s):
    return (s - s.mean()) / s.std(ddof=0)


def ols(X, y):
    """Return betas (incl intercept) and R^2."""
    Xi = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xi, y, rcond=None)
    yhat = Xi @ beta
    ss_res = ((y - yhat) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return beta, 1 - ss_res / ss_tot


def main():
    df = fetch()
    print(f"n tracts (complete income + demographics + SAT): {len(df)}\n")

    preds = ["median_hh_income", "poverty_rate", "pct_black", "pct_hispanic", "pct_white_nh"]

    print("=== (1) Bivariate Pearson r with assigned-school SAT ===")
    for p in preds:
        r = df["assigned_sat"].corr(df[p])
        print(f"   {p:<20} r = {r:+.3f}")

    print("\n=== (2) Collinearity among predictors (|r| with income) ===")
    for p in preds[1:]:
        print(f"   income vs {p:<16} r = {df['median_hh_income'].corr(df[p]):+.3f}")

    print("\n=== (3) Standardized OLS: SAT ~ z(income)+z(poverty)+z(%black)+z(%hispanic) ===")
    use = ["median_hh_income", "poverty_rate", "pct_black", "pct_hispanic"]
    Z = np.column_stack([zscore(df[c]) for c in use])
    y = df["assigned_sat"].values.astype(float)
    beta, r2 = ols(Z, y)
    print(f"   model R^2 = {r2:.3f}")
    print(f"   intercept (mean SAT) = {beta[0]:.0f}")
    for c, b in zip(use, beta[1:]):
        print(f"   std beta  {c:<18} = {b:+.1f} SAT pts per 1 SD")

    print("\n=== (4) R^2 of competing single-factor stories ===")
    for c in ["median_hh_income", "poverty_rate", "pct_black", "pct_hispanic"]:
        _, r2c = ols(zscore(df[c]).values.reshape(-1, 1), y)
        print(f"   SAT ~ {c:<20} R^2 = {r2c:.3f}")

    print("\n=== (5) Partial corr: income vs SAT, controlling for poverty + race ===")
    ctrl = ["poverty_rate", "pct_black", "pct_hispanic"]
    C = np.column_stack([np.ones(len(df))] + [df[c].values for c in ctrl])
    res_sat = y - C @ np.linalg.lstsq(C, y, rcond=None)[0]
    inc = df["median_hh_income"].values.astype(float)
    res_inc = inc - C @ np.linalg.lstsq(C, inc, rcond=None)[0]
    pr = np.corrcoef(res_sat, res_inc)[0, 1]
    print(f"   partial r (income | poverty,race) = {pr:+.3f}")
    print(f"   (bivariate income r was {df['assigned_sat'].corr(df['median_hh_income']):+.3f})")


if __name__ == "__main__":
    main()
