"""detective.py — a reference for lab Step 6 (teacher only; students write their own)."""
import pandas as pd

from navera_lite.logbook import add_motion, clean, load_log

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

DATA = "/data/academy/04-python-data/"
df, _ = clean(load_log(DATA + "campaign.csv"))
df = add_motion(df)
sheet = pd.read_csv(DATA + "flight_sheet.csv").set_index("flight_id")
takeoff = pd.to_timedelta(sheet["takeoff_utc"]).dt.total_seconds()
landing = pd.to_timedelta(sheet["landing_utc"]).dt.total_seconds()
g = df.groupby("flight_id")
clock = pd.DataFrame({"log_first_s": g["time_s"].min(), "sheet_takeoff_s": takeoff,
                      "log_last_s": g["time_s"].max(), "sheet_landing_s": landing})
clock["first_minus_takeoff_s"] = (clock["log_first_s"] - clock["sheet_takeoff_s"]).round(1) + 0.0   # no "-0.0"
print(clock.round(1), "\n")
speed = pd.DataFrame({"logged_median": g["speed_mps"].median(), "from_positions_median": g["pos_speed_mps"].median()})
speed["ratio"] = speed["logged_median"] / speed["from_positions_median"]
print(speed.round(2))
