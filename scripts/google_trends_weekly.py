"""Fetch last week's Google Trends interest for a fixed keyword set across DE/IT/FR/ES/GB.

Run every Tuesday (see .github/workflows/google-trends-weekly.yml). "Last week" is
always the most recently completed Monday-Sunday range relative to the run date, so a
Tuesday run covers the week that ended two days earlier.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
from pytrends.request import TrendReq

KEYWORDS = ["Luna Ultra", "Insta360 Luna", "DJI Osmo Pocket 4", "Pocket 4"]
GEOS = {"DE": "Germany", "IT": "Italy", "FR": "France", "ES": "Spain", "GB": "United Kingdom"}
REQUEST_PAUSE_SECONDS = 20
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def last_full_week(today: date) -> tuple[date, date]:
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def fetch_geo(pytrends: TrendReq, geo: str, start: date, end: date) -> pd.DataFrame:
    pytrends.build_payload(KEYWORDS, timeframe=f"{start} {end}", geo=geo)
    df = pytrends.interest_over_time()
    if df.empty:
        return df
    return df.drop(columns=["isPartial"], errors="ignore")


def build_report(daily: pd.DataFrame, start: date, end: date) -> str:
    lines = [f"# Google Trends Weekly Report ({start} to {end})", ""]
    lines.append("Relative search interest (0-100), scaled per country/keyword group by Google Trends.")
    lines.append("")

    summary = daily.groupby(["geo", "keyword"])["value"].mean().unstack("keyword")
    summary = summary.reindex(columns=KEYWORDS)

    for geo, name in GEOS.items():
        lines.append(f"## {name} ({geo})")
        if geo not in summary.index or summary.loc[geo].isna().all():
            lines.append("")
            lines.append("_No data returned for this country/week._")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Keyword | Avg weekly interest |")
        lines.append("|---|---|")
        for kw in KEYWORDS:
            val = summary.loc[geo].get(kw)
            lines.append(f"| {kw} | {'' if pd.isna(val) else round(val, 1)} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    today = date.today()
    start, end = last_full_week(today)

    pytrends = TrendReq(
        hl="en-US",
        tz=0,
        timeout=(10, 25),
        retries=5,
        backoff_factor=5,
        requests_args={"headers": {"User-Agent": BROWSER_USER_AGENT}},
    )

    rows = []
    for geo in GEOS:
        try:
            df = fetch_geo(pytrends, geo, start, end)
        except Exception as exc:  # pytrends raises assorted request errors on rate limits/blocks
            print(f"WARN: failed to fetch {geo}: {exc}", file=sys.stderr)
            df = pd.DataFrame()

        if not df.empty:
            long_df = df.reset_index().melt(id_vars=["date"], var_name="keyword", value_name="value")
            long_df["geo"] = geo
            rows.append(long_df)

        time.sleep(REQUEST_PAUSE_SECONDS)

    daily = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "keyword", "value", "geo"])

    out_dir = os.path.join("reports", f"{start}_to_{end}")
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, "daily_interest.csv")
    daily.to_csv(csv_path, index=False)

    report_md = build_report(daily, start, end)
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Wrote {report_path} and {csv_path}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"report_dir={out_dir}\n")
            f.write(f"report_path={report_path}\n")
            f.write(f"range_start={start}\n")
            f.write(f"range_end={end}\n")


if __name__ == "__main__":
    main()
