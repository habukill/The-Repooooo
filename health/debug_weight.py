"""
Dump the raw weight dataPoints so we can see why every date before 2026-07-20
came back as exactly 74.0 kg.

Run it the same way as fetch_health.py (needs token.json next to this file):

    cd health && python debug_weight.py

It prints, per date, every weight reading the API returned along with whatever
source/metadata fields came with it, and flags any date carrying more than one
distinct value - that is the case that would let a stale entry overwrite a real
scale reading.
"""
import json
import os
from collections import defaultdict

from fetch_health import get_credentials, fetch, fmt_date

DIR = os.path.dirname(__file__)


def main():
    creds = get_credentials()
    points = fetch(creds, "weight", paginate=True)
    print(f"total weight dataPoints returned: {len(points)}\n")

    if points:
        print("--- first raw dataPoint verbatim (to inspect available fields) ---")
        print(json.dumps(points[0], indent=2, ensure_ascii=False))
        print()

    by_date = defaultdict(list)
    for p in points:
        d = p.get("weight", {})
        date_obj = d.get("sampleTime", {}).get("civilTime", {}).get("date", {})
        if not date_obj:
            continue
        grams = d.get("weightGrams")
        # Anything that might identify where the reading came from.
        origin = {
            k: p.get(k)
            for k in ("dataSource", "source", "origin", "device", "metadata", "dataPointId")
            if p.get(k) is not None
        }
        by_date[fmt_date(date_obj)].append(
            (round(float(grams) / 1000, 2) if grams else None, origin)
        )

    multi = {d: v for d, v in by_date.items() if len({kg for kg, _ in v}) > 1}
    print(f"dates with more than one distinct weight: {len(multi)}")
    for d in sorted(multi)[:15]:
        print(f"  {d}: {multi[d]}")
    print()

    print("--- every reading, oldest first ---")
    for d in sorted(by_date):
        readings = by_date[d]
        vals = ", ".join(
            f"{kg} kg" + (f" {origin}" if origin else "") for kg, origin in readings
        )
        flag = "  <-- MULTIPLE" if len(readings) > 1 else ""
        print(f"  {d}: {vals}{flag}")


if __name__ == "__main__":
    main()
