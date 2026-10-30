# Lab 4 — your answers. Numbers without quotes (ROWS_RAW = 12). Text in quotes ("…").
# PREDICT_… : your guess BEFORE you run the step. Never marked right or wrong: write it honestly.
# EXPLAIN_… : after the run, in your own words (one to three sentences). Your teacher reads them.

# ======== Session 1 — Clean & measure (Step 0 needs no answer) ========

# ---- Step 1: look before you compute ---------------------------------------------------------
ROWS_RAW = 0          # data rows of campaign.csv (the header line is not a row)
MOST_ROWS_FLIGHT = "" # the flight with the most rows (one shell pipeline)
EMPTY_LAT_ROWS = 0    # rows whose lat cell is empty (one shell pipeline)
DROPNA_ROWS_LOST = 0  # how many rows df.dropna() would throw away
PREDICT_CLEAN = ""    # how many rows will the three cleaning rules remove, and which rule removes most?

# ---- Step 2: cleaning ---------------------------------------------------------------------------
EXPLAIN_KEEP_NOFIX = ""   # why must the NO_FIX rows (empty lat/lon) stay in the clean log?

# ---- Step 3: motion -----------------------------------------------------------------------------
FASTEST_SOURCE = ""   # "gps", "day" or "none": the source of the fastest steps of the flights

# ---- Step 4: outage runs ------------------------------------------------------------------------
PREDICT_RUNS = ""     # what will outage_runs([0, 0, 1, 1, 0, 1, 0, 0, 0]) return? (write it before testing)

# ======== Session 2 — Detect & report ========

# ---- Step 6: the detective — the runner applies these two corrections from "schedule" on ---------
CLOCK_FIX_S = {}      # {flight_id: seconds to ADD to that flight's time_s}, e.g. {"some_flight": -120.0}
SPEED_FACTOR = {}     # {flight_id: factor that turns that flight's speed_mps into m/s}, e.g. {"some_flight": 0.5}
EXPLAIN_DETECTIVE = ""   # your evidence for each correction (what you compared, with numbers)
UNPLANNED_FLIGHT = ""    # after your corrections: the flight with an outage the jammer does not explain
UNPLANNED_START_UTC = "" # its start, "hh:mm:ss"

# ---- Step 7: how noisy is each source? ------------------------------------------------------------
PREDICT_NOISE = ""    # σ of the speed error you expect for gps and for day vision (m/s), from the lesson's §5
EXPLAIN_ROBUST = ""   # why is day vision's std_mps so much bigger than its mad_sigma_mps? which one is "the
                      # noise", and what must the report add? and what did the median NOT protect you from?
