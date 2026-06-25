from astropy.io import fits
import numpy as np
import pandas as pd

def to_native(arr):
    return arr.byteswap().view(arr.dtype.newbyteorder())

fname = 'Lyra_EUV_10May2026.fits'
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

# Trim to 13:00-15:00 UTC
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

