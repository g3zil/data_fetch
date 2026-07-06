# Written by Clause AI Sonnet 4.6 with checks by Gwyn Griffiths G3ZIL
# Data access for Level 1 data at 4 Hz via links for the PROBA2 LYRA eUV instrument
# Takes time interval from the sat_data.ini file in the config subdirectory
# 

from astropy.io import fits
import numpy as np
import pandas as pd
from sunpy.net import Fido, attrs as a
import configparser
import ast
import os

def to_native(arr):
    return arr.byteswap().view(arr.dtype.newbyteorder())

# set up base directory, and the directory path for inout and output files 
base_directory='./'

# ---------------------------------------------------------------------------
# Configuration from ./config/sat_data.ini
# ---------------------------------------------------------------------------
config_file = base_directory+"config/sat_data.ini"
config = configparser.ConfigParser()
config.read(config_file)           # 

# Time window
YEAR=config['datetime'].getint('YEAR')
MONTH=config['datetime'].getint('MONTH')
DAY=config['datetime'].getint('DAY')
HOUR_START=config['datetime'].getint('HOUR_START')
HOUR_END=config['datetime'].getint('HOUR_END')
MIN_START=config['datetime'].getint('MIN_START')
MIN_END=config['datetime'].getint('MIN_END')

csv_output_dir=os.path.join(base_directory,'output','csv','LYRA')
if not os.path.exists(csv_output_dir):       
  os.makedirs(csv_output_dir)

# --- Step 1: Automatically Download PROBA2 LYRA Data via SunPy ---
print("Searching for PROBA2 LYRA data...")

# Check If File Exists Locally Before Querying Online ---
# Standard PROBA2 LYRA filename convention: lyra_YYYYMMDD-000000_lev2_std.fits
expected_filename = f"lyra_{YEAR:04d}{MONTH:02d}{DAY:02d}-000000_lev2_std.fits"
local_dir = get_and_create_download_dir()
local_path = os.path.join(local_dir, expected_filename)

if os.path.exists(local_path):
    print(f"Found local file cache: {local_path}")
    fname = local_path
else:
    print(f"File not found locally. Searching online for PROBA2 LYRA data...")
    # Dynamically build the full-day search window for Fido
    time_range = a.Time(f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} 00:00:00", f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} 23:59:59")

# Query Fido for the LYRA instrument
results = Fido.search(time_range, a.Instrument.lyra)

print("Downloading FITS file...")
# Download the file (returns a Results object containing the local file path)
downloaded_files = Fido.fetch(results)

if not downloaded_files:
    raise FileNotFoundError("No LYRA data found for the specified date.")

# Extract the absolute path of the first downloaded file
fname = downloaded_files[0]
print(f"Successfully fetched: {fname}\nProcessing data...")

# --- Step 2: Your Existing Processing Code ---
hdul = fits.open(fname)
data = hdul[1].data
time = to_native(data['TIME'])
lya  = to_native(data['CHANNEL1'])
alum = to_native(data['CHANNEL3'])
hdul.close()

# Convert TIME (seconds of day) to datetime
base = pd.Timestamp('2026-05-10T00:00:00')
timestamps = pd.to_datetime(time, unit='s', origin=base)

# Build dataframe
df = pd.DataFrame({
    'lyman_alpha_Wm2': lya,
    'aluminium_Wm2':   alum,
}, index=timestamps)
df.index.name = 'time_utc'

# Trim to 13:00-14:00 UTC (Updated to match your actual slice string below)
window = df['2026-05-10 13:00':'2026-05-10 14:00'].copy()

# Resample to 3-second bins — mean of ~60 samples per bin
avg3s = window.resample('3s').mean()

# Rate of change between successive 3-second averages, scaled to per second
avg3s['lya_dFdt_per_s']  = avg3s['lyman_alpha_Wm2'].diff() / 3.0
avg3s['alum_dFdt_per_s'] = avg3s['aluminium_Wm2'].diff() / 3.0

# Write to CSV
avg3s.index.name = 'time_utc'
avg3s.to_csv('lyra_euv_3s_20260510_1300_1400.csv', date_format='%Y-%m-%dT%H:%M:%S')

print(avg3s)
print(f"\nSaved {len(avg3s)} rows (3-second bins)")
