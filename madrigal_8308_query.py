#!/usr/bin/env python3
"""
Script written mostly by Anthropic Claude AI Sonnet v4.6 following iterations with Gwyn Griffiths G3ZIL
Query the CEDAR Madrigal database (Instrument 8308 - Amateur Radio Signal Report)
for FT8, WSPR or CW spots.

The Madrigal server refuses isprint() filtering on files > 200 MB, so we
must download the full HDF5 file for the whole day. However, we avoid loading it all into
memory by using h5py to stream through it in chunks, applying the time
and mode filters as we go.

# KNOWN GOTCHAS (learned the hard way):
# - HDF5 column names are lowercase (ut1_unix, smode, tfreq, sn, etc.)
# - getExperimentFileParameters() returns uppercase — ignore for HDF5 access
# - isprint() silently rejects files > 200 MB — must use downloadFile()
# - Epoch values must be computed dynamically (hardcoded values caused year-off bug)
# - The 1200-1500 UTC window contains ~60-70M FT8 rows — must write CSV per chunk

Peak RAM usage is controlled by CHUNK_SIZE (rows per chunk), not file size.

Requirements:
    pip install madrigalWeb h5py numpy pandas
	
    and a 8308.ini configuration file in the ./config directory, see original example

Usage:
    python madrigal_8308_query.py

Output csv file with name constructed from:
    MODE-YEAR-MONTH-DAY-HOUR_START00-HOUR_END00.csv
"""

import sys
import os
import datetime
import numpy as np
import pandas as pd
import h5py
import configparser
import ast
import os

# ---------------------------------------------------------------------------
# Configuration from ./config/8308.ini
# ---------------------------------------------------------------------------
config_file = "./config/8308.ini"
config = configparser.ConfigParser()
config.read(config_file)           # 

USER_FULLNAME=config['credentials'].get('USER_FULLNAME')
USER_EMAIL=config['credentials'].get('USER_EMAIL')
USER_AFFILIATION=config['credentials'].get('USER_AFFILIATION')

# Time window
YEAR=config['datetime'].getint('YEAR')
MONTH=config['datetime'].getint('MONTH')
DAY=config['datetime'].getint('DAY')
HOUR_START=config['datetime'].getint('HOUR_START')
HOUR_END=config['datetime'].getint('HOUR_END')

# Mode parameters
MODE=config['mode'].get('MODE')

#------------------------------------------------------------------------------
# Remaining set-up
HDF5_LOCAL  = "rsd"+str(YEAR)+"-"+str(MONTH)+"-"+str(DAY)+".hdf5"     # This output file contains all reports for all Ham modes for a day, may be 8 GB
CSV_OUTPUT  = MODE+"-"+str(YEAR)+"-"+str(MONTH)+"-"+str(DAY)+"-"+str(HOUR_START)+"00-"+str(HOUR_END)+"00.csv"      # CSV file for 3 hr was ~ 1.7 GB

MADRIGAL_URL     = "https://cedar.openmadrigal.org"
INSTRUMENT_CODE  = 8308  # This is the code for amateur radio reports:
			             # WSPR from wsprnet.org, CW from Reverse Beacon Network, FT8 from pskreporter
CHUNK_SIZE  = 500_000   			    # rows processed at a time — keeps RAM low
UTC      = datetime.timezone.utc
DT_START = datetime.datetime(YEAR, MONTH, DAY, HOUR_START, 0, 0, tzinfo=UTC)
DT_END   = datetime.datetime(YEAR, MONTH, DAY, HOUR_END, 0, 0, tzinfo=UTC)

#-------------------------------------------------------------------------------

START_UT1_UNIX = int(DT_START.timestamp())
END_UT1_UNIX   = int(DT_END.timestamp())

print("Selecting data for mode: ", MODE)
print(f"Time window : {DT_START.isoformat()} → {DT_END.isoformat()}")
print(f"Unix epochs : {START_UT1_UNIX} → {END_UT1_UNIX}")
sys.exit()
# ---------------------------------------------------------------------------
# Step 1 — Download the full HDF5 file (only if not already present)
# ---------------------------------------------------------------------------

try:
    import madrigalWeb.madrigalWeb as mw
except ImportError:
    sys.exit("ERROR: madrigalWeb not found.\nInstall with: pip install madrigalWeb")

if os.path.exists(HDF5_LOCAL):
    print(f"\nUsing cached file: {HDF5_LOCAL} "
          f"({os.path.getsize(HDF5_LOCAL)/1e9:.2f} GB)")
else:
    print(f"\nConnecting to {MADRIGAL_URL} ...")
    madDB = mw.MadrigalData(MADRIGAL_URL)

    print("Connected: Searching for experiment ...")
    experiments = madDB.getExperiments(
        INSTRUMENT_CODE,
        YEAR, MONTH, DAY, 0, 0, 0,
        YEAR, MONTH, DAY, 23, 59, 59
    )
    if not experiments:
        sys.exit("No experiments found. Data may not yet be ingested (~1 month lag).")

    files = madDB.getExperimentFiles(experiments[0].id)
    if not files:
        sys.exit("No files found for this experiment.")

    file_rec = files[0]
    print(f"Experiment found: Downloading: {file_rec.name}")
    print("(This may take many minutes for a ~8 GB file ...)")

    madDB.downloadFile(
        file_rec.name, HDF5_LOCAL,
        USER_FULLNAME, USER_EMAIL, USER_AFFILIATION,
        format="hdf5"
    )
    print(f"Download complete ({os.path.getsize(HDF5_LOCAL)/1e9:.2f} GB).")

# ---------------------------------------------------------------------------
# Step 2 — Stream through the HDF5 file in chunks, filtering as we go
#
# h5py supports reading arbitrary row slices from an HDF5 dataset without
# loading the whole thing. We read CHUNK_SIZE rows at a time, apply the
# UT1_UNIX time filter and SMODE == "FT8" or "WSPR" or "CW" filter, and accumulate only
# the matching rows. Peak RAM ~ CHUNK_SIZE rows, not the full file.
# ---------------------------------------------------------------------------

total_8308 = 0
header_written = False
csv_fh = open(CSV_OUTPUT, "w", buffering=1)

with h5py.File(HDF5_LOCAL, "r") as f:

    layout = f["Data/Table Layout"]
    total_rows = layout.shape[0]
    print(f"Total rows in file: {total_rows:,}")

    # Confirm required columns exist (HDF5 stores names in lowercase)
    cols = layout.dtype.names
    for required in ("ut1_unix", "smode"):
        if required not in cols:
            csv_fh.close()
            sys.exit(f"Required column '{required}' not found. "
                     f"Available: {cols}")

    n_chunks = (total_rows + CHUNK_SIZE - 1) // CHUNK_SIZE

    for i in range(n_chunks):
        row_start = i * CHUNK_SIZE
        row_end   = min(row_start + CHUNK_SIZE, total_rows)

        chunk = layout[row_start:row_end]

        # --- Time filter ---
        ut1 = chunk["ut1_unix"].astype(np.float64)
        time_mask = (ut1 >= START_UT1_UNIX) & (ut1 < END_UT1_UNIX)

        if not np.any(time_mask):
            if i % 10 == 0:
                pct = 100 * row_end / total_rows
                print(f"  chunk {i+1}/{n_chunks} ({pct:.0f}%) — no time matches")
            continue

        chunk_time = chunk[time_mask]

        # --- Mode filter ---
        smode = np.char.decode(chunk_time["smode"], "utf-8")
        smode = np.char.strip(smode)
        mode_mask = np.char.upper(smode) == MODE

        chunk_8308 = chunk_time[mode_mask]
        n_8308 = len(chunk_8308)

        if n_8308 > 0:
            row_dict = {}
            for col in chunk_8308.dtype.names:
                col_data = chunk_8308[col]
                if col_data.dtype.kind == "S":
                    col_data = np.char.decode(col_data, "utf-8")
                    col_data = np.char.strip(col_data)
                row_dict[col] = col_data

            df_chunk = pd.DataFrame(row_dict)

            # Select wanted columns
            wanted = ["ut1_unix", "smode", "tfreq", "sn",
                      "txlat", "txlon", "rxlat", "rxlon",
                      "pthlen", "call_sign_tx", "call_sign_rx"]
            present = [c for c in wanted if c in df_chunk.columns]
            df_chunk = df_chunk[present]

            for col in ["ut1_unix", "tfreq", "sn", "txlat", "txlon",
                        "rxlat", "rxlon", "pthlen"]:
                if col in df_chunk.columns:
                    df_chunk[col] = pd.to_numeric(df_chunk[col], errors="coerce")

            df_chunk.insert(0, "datetime_utc",
                            pd.to_datetime(df_chunk["ut1_unix"], unit="s", utc=True))

            # Write to CSV immediately — no accumulation in RAM
            df_chunk.to_csv(csv_fh, index=False, header=not header_written)
            header_written = True
            csv_fh.flush()
            total_8308 += n_8308

        pct = 100 * row_end / total_rows
        print(f"  chunk {i+1}/{n_chunks} ({pct:.0f}%) — "
              f"{np.sum(time_mask):,} time match in window, "
              f"{n_8308:,} mode this chunk, "
              f"{total_8308:,} total written")

csv_fh.close()

# ---------------------------------------------------------------------------
# Step 3 — Report
# ---------------------------------------------------------------------------

if total_8308 == 0:
    sys.exit("No selected mode records found in the 1200-1500 UTC window.")

print(f"\nTotal selected mode records written: {total_8308:,}")

# ---------------------------------------------------------------------------
# Step 4 — Print summary statistics from the saved CSV
# (read back in chunks to avoid loading the whole thing)
# ---------------------------------------------------------------------------

print("\n--- Summary ---")
print(f"Date        : 10 May 2026")
print(f"Time window : 1200-1500 UTC")
print(f"Mode        :", MODE)
print(f"Total spots : {total_8308:,}")

# Read back CSV in chunks just to compute stats without loading all into RAM
tfreq_vals, sn_vals, pthlen_vals = [], [], []
for chunk in pd.read_csv(CSV_OUTPUT, chunksize=500_000,
                         usecols=lambda c: c in ("tfreq", "sn", "pthlen")):
    if "tfreq"  in chunk: tfreq_vals.append(chunk["tfreq"].dropna().values)
    if "sn"     in chunk: sn_vals.append(chunk["sn"].dropna().values)
    if "pthlen" in chunk: pthlen_vals.append(chunk["pthlen"].dropna().values)

if tfreq_vals:
    print(f"\nFrequency (Hz):\n{pd.Series(np.concatenate(tfreq_vals)).describe()}")
if sn_vals:
    print(f"\nSNR (dB):\n{pd.Series(np.concatenate(sn_vals)).describe()}")
if pthlen_vals:
    print(f"\nPath length (km):\n{pd.Series(np.concatenate(pthlen_vals)).describe()}")

print(f"\nFirst 5 rows:\n{pd.read_csv(CSV_OUTPUT, nrows=5).to_string()}")
