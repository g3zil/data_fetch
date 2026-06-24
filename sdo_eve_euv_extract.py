# Written by Clause AI Sonnet 4.6 with checks by Gwyn Griffiths G3ZIL
# Data access for Level 1 data at 4 Hz via links for the Solar Dynamics Observatory EVE sensor
# at https://lasp.colorado.edu/eve/data_access/index.html
# The ESP functions as an advanced, high-speed transmission grating spectrograph.
# It operates at a rapid 4 Hz cadence to capture instantaneous flare fluctuations and provides vital
# in-flight cross-calibration for the main MEGS channels.
# It features broad band channels centered around five specific targets:
# 0.1–7 nm quadrant photodiode soft X-rays
# 18 nm
# 26 nm
# 30 nm Helium
# 36 nm
#
# Two command line arguments: .fit data file name, which can be .gz and cadence in seconds for the averaging

from astropy.io import fits
import numpy as np
import pandas as pd
import sys

datafile=str(sys.argv[1])            # First command line argument, .fit file name, can be .gz
cadence=int(sys.argv[2])             # Second command line argument, averaging interval in seconds

print("Extracting data from file: ", datafile, " averaging to: ", cadence, "s cadence")

hdul = fits.open(datafile)
data = hdul[1].data
hdul.close()

def to_native(arr):
    return arr.byteswap().view(arr.dtype.newbyteorder())

# Extract time components
year = to_native(data['YEAR'])
doy  = to_native(data['DOY'])
sod  = to_native(data['SOD'])   # seconds of day

# Build datetime index
base = pd.Timestamp('2026-05-10T00:00:00')
timestamps = pd.to_datetime(sod, unit='s', origin=base)

# Extract channels
df = pd.DataFrame({
    'qd_Wm2':    to_native(data['QD']),
    'ch18_Wm2':  to_native(data['CH_18']),
    'ch26_Wm2':  to_native(data['CH_26']),
    'ch30_Wm2':  to_native(data['CH_30']),
    'ch36_Wm2':  to_native(data['CH_36']),
}, index=timestamps)
df.index.name = 'time_utc'

# Trim to flare window
window = df['2026-05-10 13:20':'2026-05-10 13:40'].copy()

# Resample to cadence-second bins
avg = window.resample(f"{cadence}s").mean()

# Rate of change for CH_30 (He II 30.4 nm) and CH_26, scaled to per second
avg['ch30_dFdt_per_s'] = avg['ch30_Wm2'].diff() / cadence
avg['ch26_dFdt_per_s'] = avg['ch26_Wm2'].diff() / cadence

# Save to CSV
filename = ".".join(datafile.split(".")[:-2])+".csv"
avg.to_csv(filename, date_format='%Y-%m-%d %H:%M:%S')
print(avg)
print(f"\nSaved {len(avg)} rows into file:", filename)

