"""Generate the SIMULATED demonstration dataset in data/flight_fares.csv.

Every row is flagged is_simulated=True. The numbers come from a simple, seeded
booking-curve model, NOT from any airline, travel website or API.

Run:  python scripts/generate_sample_data.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
OUT = Path(__file__).resolve().parents[1] / "data" / "flight_fares.csv"
SOURCE = f"Simulated: scripts/generate_sample_data.py (seed {SEED})"

AIRPORTS = {"LHE": "Lahore", "KHI": "Karachi", "ISB": "Islamabad", "DXB": "Dubai"}
# route -> assumed base one-way economy fare in PKR (illustrative only)
ROUTES = {("LHE", "KHI"): 24000, ("KHI", "ISB"): 26000, ("LHE", "ISB"): 14000,
          ("LHE", "DXB"): 62000, ("ISB", "DXB"): 68000}
CARRIERS = {"Simulated Carrier A": 1.00, "Simulated Carrier B": 1.07, "Simulated Carrier C": 0.94}
DEPARTURES = {date(2026, 10, 15): 1.00, date(2026, 11, 15): 1.06}
FIRST_OBS, N_OBS, STEP_DAYS = date(2026, 7, 1), 30, 3   # 1 Jul .. 26 Sep 2026, every 3 days
N_MISSING = 8                                            # blank fares, to exercise gap handling


def main() -> None:
    rng = np.random.default_rng(SEED)
    obs_dates = [FIRST_OBS + timedelta(days=STEP_DAYS * i) for i in range(N_OBS)]
    rows = []
    for (o, d), base in ROUTES.items():
        phase = rng.uniform(0, 2 * np.pi)
        for carrier, c_factor in CARRIERS.items():
            for dep, d_factor in DEPARTURES.items():
                walk = 0.0
                for i, obs in enumerate(obs_dates):
                    days_out = (dep - obs).days
                    curve = 1 + 0.45 * np.exp(-days_out / 30)             # fares drift up near departure
                    wave = 1 + 0.04 * np.sin(2 * np.pi * i / 10 + phase)  # mild cyclical variation
                    walk = 0.8 * walk + rng.normal(0, 0.015)              # autocorrelated noise
                    promo = 0.90 if (o, d) == ("LHE", "ISB") and date(2026, 8, 10) <= obs <= date(2026, 8, 25) else 1.0
                    fare = base * c_factor * d_factor * curve * wave * (1 + walk) * promo
                    rows.append({
                        "recorded_at": obs.isoformat(), "origin": AIRPORTS[o], "origin_code": o,
                        "destination": AIRPORTS[d], "destination_code": d, "airline": carrier,
                        "departure_date": dep.isoformat(), "fare": int(round(fare / 50) * 50),
                        "currency": "PKR", "source": SOURCE, "is_simulated": True,
                    })
    df = pd.DataFrame(rows)
    df = df.sort_values(["recorded_at", "origin_code", "destination_code", "airline", "departure_date"])
    df["fare"] = df["fare"].astype("object")
    blank = rng.choice(df.index.to_numpy(), size=N_MISSING, replace=False)
    df.loc[blank, "fare"] = ""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} rows to {OUT}")


if __name__ == "__main__":
    main()
