# Originally written by Claude AI Sonnet 4.6 with checks by Gwyn Griffiths G3ZIL
# Data access for Level 1 data at 4 Hz via links for the Solar Dynamics Observatory EVE sensor
# at https://lasp.colorado.edu/eve/data_access/index.html
#
# The ESP functions as an advanced, high-speed transmission grating spectrograph.
# It operates at a rapid 4 Hz cadence to capture instantaneous flare fluctuations and provides vital
# in-flight cross-calibration for the main MEGS channels.
# It features broad band channels centered around five specific targets:
# 0.1-7 nm quadrant photodiode soft X-rays and four eUV bands: 18 nm, 26 nm, 30 nm Helium II, 36 nm
#
# No command line arguments are needed. The required UTC date (one day) and the averaging
# cadence are read from ./config/SDO_ESP_config.ini
# The script works out the file name from the date, e.g. 2026-10-08 is day 281, giving
#   https://lasp.colorado.edu/eve/data_access/eve_data/products/level1/esp/2026/esp_L1_2026281_008.fit.gz
# downloads it (if not already present in ./input/EVE_ESP), then averages and writes a CSV.
#
# For the 30.4 nm channel (CH_30) three rates of change are output, all in W/m^2 per second:
#   ch30_dFdt_per_s         simple difference of the cadence-averaged flux (noisy at short cadence)
#   ch30_dFdt_savgol_per_s  Savitzky-Golay first derivative of the 4 Hz data, then averaged to the cadence
#   ch30_dFdt_gauss_per_s   Gaussian first-derivative filter of the 4 Hz data, then averaged to the cadence
# The two filters work on the full day, so the START_TIME/END_TIME trim causes no edge effects.
# All times in the CSV are bin centres: a row stamped T holds data from T - cadence/2 to T + cadence/2,
# and the simple rate of change is a central difference, so every column refers to the same instant.

from astropy.io import fits
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.signal import savgol_filter
import configparser
import datetime as dt
import os
import re
import shutil
import sys
import urllib.error
import urllib.request

BASE_URL = "https://lasp.colorado.edu/eve/data_access/eve_data/products/level1/esp"

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------
base_directory = './'
fit_input_dir = os.path.join(base_directory, 'input', 'EVE_ESP')
csv_output_dir = os.path.join(base_directory, 'output', 'csv', 'EVE_ESP')
os.makedirs(fit_input_dir, exist_ok=True)
os.makedirs(csv_output_dir, exist_ok=True)

# ---------------------------------------------------------------------------
# Configuration from ./config/SDO_ESP_config.ini
# ---------------------------------------------------------------------------
config_file = os.path.join(base_directory, "config", "SDO_ESP_config.ini")
config = configparser.ConfigParser(inline_comment_prefixes=('#',))
if not config.read(config_file):
    sys.exit(f"Cannot read config file {config_file}")

esp = config['ESP']
try:
    the_date = dt.datetime.strptime(esp['DATE'].strip(), "%Y-%m-%d").date()
except (KeyError, ValueError):
    sys.exit("DATE in config must be present and in the form YYYY-MM-DD")

cadence = esp.getint('CADENCE')
if cadence is None or cadence < 1:
    sys.exit("CADENCE in config must be a whole number of seconds, 1 or more")

start_time = esp.get('START_TIME', '00:00').strip()
end_time = esp.get('END_TIME', '23:59').strip()
version = esp.get('VERSION', '008').strip()

# Derivative filter settings
savgol_window_s = esp.getfloat('SAVGOL_WINDOW', 8.0)     # seconds
savgol_polyorder = esp.getint('SAVGOL_POLYORDER', 3)
gauss_sigma_s = esp.getfloat('GAUSS_SIGMA', 3.0)         # seconds
GRID_S = 0.25                                            # ESP nominal 4 Hz sample spacing
savgol_window = int(round(savgol_window_s / GRID_S))
if savgol_window % 2 == 0:
    savgol_window += 1                                   # Savitzky-Golay needs an odd window
if savgol_window <= savgol_polyorder:
    sys.exit("SAVGOL_WINDOW is too short for SAVGOL_POLYORDER: need more samples than the polynomial order")
if gauss_sigma_s <= 0:
    sys.exit("GAUSS_SIGMA must be greater than zero")

YEAR = the_date.year
DOY = the_date.timetuple().tm_yday   # day of year, 1 to 366

# ---------------------------------------------------------------------------
# Download the file if we do not already have it
# ---------------------------------------------------------------------------
def fetch(url, dest):
    """Download url to dest via a temporary .part file."""
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, 'wb') as out:
        shutil.copyfileobj(resp, out)
    os.replace(tmp, dest)


def find_version_on_server(year, doy):
    """Fallback: read the year's directory listing and pick the highest version for this day."""
    with urllib.request.urlopen(f"{BASE_URL}/{year}/", timeout=60) as resp:
        listing = resp.read().decode('utf-8', errors='replace')
    versions = re.findall(rf"esp_L1_{year}{doy:03d}_(\d+)\.fit\.gz", listing)
    return max(versions) if versions else None


def get_esp_file(year, doy, version):
    fname = f"esp_L1_{year}{doy:03d}_{version}.fit.gz"
    dest = os.path.join(fit_input_dir, fname)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("Using existing file:", dest)
        return fname

    url = f"{BASE_URL}/{year}/{fname}"
    print("Downloading", url)
    try:
        fetch(url, dest)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            sys.exit(f"Download failed: HTTP {e.code} for {url}")
        # Not found with the configured version, see what the server has for that day
        print(f"{fname} not found, checking the server directory for other versions")
        try:
            alt = find_version_on_server(year, doy)
        except Exception as e2:
            sys.exit(f"Not found, and could not read directory listing: {e2}")
        if alt is None:
            sys.exit(f"No ESP Level 1 file for {year} day {doy:03d} on the server. "
                     "Very recent days may not be posted yet.")
        fname = f"esp_L1_{year}{doy:03d}_{alt}.fit.gz"
        dest = os.path.join(fit_input_dir, fname)
        print("Found version", alt, "- downloading", f"{BASE_URL}/{year}/{fname}")
        fetch(f"{BASE_URL}/{year}/{fname}", dest)
    except urllib.error.URLError as e:
        sys.exit(f"Network error: {e.reason}")
    print("Saved", dest)
    return fname


datafile = get_esp_file(YEAR, DOY, version)
print("Extracting data from file:", datafile, "averaging to:", cadence, "s cadence")

# ---------------------------------------------------------------------------
# Read the file
# ---------------------------------------------------------------------------
hdul = fits.open(os.path.join(fit_input_dir, datafile))   # astropy reads .gz directly
data = hdul[1].data
hdul.close()


def to_native(arr):
    return arr.byteswap().view(arr.dtype.newbyteorder())


# Time components
year = to_native(data['YEAR'])
doy = to_native(data['DOY'])
sod = to_native(data['SOD'])   # seconds of day

# Sanity check: the file should contain the day we asked for
if int(year[0]) != YEAR or int(doy[0]) != DOY:
    print(f"WARNING: file header says year {int(year[0])} day {int(doy[0])}, "
          f"config asked for year {YEAR} day {DOY}")

# Build datetime index
base = pd.Timestamp(the_date)
timestamps = pd.to_datetime(sod, unit='s', origin=base)

# Extract channels
df = pd.DataFrame({
    'qd_Wm2': to_native(data['QD']),      # 0.1 to 7.0 nm Quad Diode
    'ch18_Wm2': to_native(data['CH_18']), # 16.64-21.5 nm, highly ionized iron
    'ch26_Wm2': to_native(data['CH_26']), # 22.28-28.78 nm, hot coronal plasma and active regions
    'ch30_Wm2': to_native(data['CH_30']), # 27.16-33.8 nm, dominated by He II 30.4 nm
    'ch36_Wm2': to_native(data['CH_36']), # 33.3-40.04 nm, coronal iron lines. COMPROMISED sensor.
}, index=timestamps)
df.index.name = 'time_utc'

def filtered_derivatives(flux, grid_s, window, polyorder, sigma_s):
    """Savitzky-Golay and Gaussian first derivatives (per second) of a flux series.
    The flux is put on a regular grid; gaps up to 1 s are bridged by interpolation, longer gaps
    are left as NaN and each continuous run of data is filtered separately."""
    f = flux.resample(f"{int(grid_s * 1000)}ms").mean().interpolate(limit=int(1 / grid_s))
    sg = pd.Series(np.nan, index=f.index)
    ga = pd.Series(np.nan, index=f.index)
    valid = f.notna().to_numpy().astype(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], valid, [0]))))
    for s0, e0 in zip(edges[::2], edges[1::2]):
        seg = f.to_numpy()[s0:e0]
        if len(seg) >= window:
            sg.iloc[s0:e0] = savgol_filter(seg, window, polyorder, deriv=1, delta=grid_s)
        if len(seg) >= 3:
            ga.iloc[s0:e0] = gaussian_filter1d(seg, sigma_s / grid_s, order=1, mode='nearest') / grid_s
    return sg, ga


def centred_mean(x, cadence):
    """Average into cadence-second bins centred on their timestamp.
    Each output time T is the mean of the data from T - cadence/2 to T + cadence/2."""
    shifted = x.copy()
    shifted.index = shifted.index + pd.Timedelta(seconds=cadence / 2)
    return shifted.resample(f"{cadence}s").mean()


# Work on the full day first, so the trim to START_TIME/END_TIME causes no edge effects
avg = centred_mean(df, cadence)

# Derivatives of the 30.4 nm channel from the 4 Hz data, then averaged to the same centred bins
sg_full, ga_full = filtered_derivatives(df['ch30_Wm2'], GRID_S, savgol_window,
                                        savgol_polyorder, gauss_sigma_s)
avg['ch30_dFdt_savgol_per_s'] = centred_mean(sg_full, cadence).reindex(avg.index)
avg['ch30_dFdt_gauss_per_s'] = centred_mean(ga_full, cadence).reindex(avg.index)

# Simple rate of change as a central difference, centred on the same timestamp, per second
avg['ch30_dFdt_per_s'] = (avg['ch30_Wm2'].shift(-1) - avg['ch30_Wm2'].shift(1)) / (2 * cadence)
avg['ch26_dFdt_per_s'] = (avg['ch26_Wm2'].shift(-1) - avg['ch26_Wm2'].shift(1)) / (2 * cadence)

# Trim to the requested window (whole day by default)
day = the_date.strftime("%Y-%m-%d")
avg = avg[f"{day} {start_time}":f"{day} {end_time}"].copy()
if avg.dropna(how='all').empty:
    sys.exit(f"No data between {start_time} and {end_time} on {day}")

# Save to CSV
filename = os.path.join(csv_output_dir, ".".join(datafile.split(".")[:-2]) + ".csv")
avg.to_csv(filename, date_format='%Y-%m-%d %H:%M:%S')

print(avg)
print(f"\nSaved {len(avg)} rows into file:", filename)
