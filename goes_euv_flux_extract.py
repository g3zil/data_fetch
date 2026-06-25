import xarray as xr
import pandas as pd
import numpy as np
import sys

ds = xr.open_dataset('ops_exis-l1b-sfeu_g19_d20260510_v0-0-0.nc')

# Extract the two channels
df = ds[['time', 'avgIrradiance1216', 'avgIrradiance256']].to_dataframe()
df = df.set_index('time')
df.index = pd.to_datetime(df.index)

# Trim to flare window
window = df['2026-05-10 13:00':'2026-05-10 15:00'].copy()

# Rename for clarity
window.rename(columns={
    'avgIrradiance1216': 'lyman_alpha_121_6nm_Wm2',
    'avgIrradiance256':  'euv_25_6nm_Wm2',
}, inplace=True)

# Rate of change over successive 30-second intervals (W/m²/30s)
window['lya_dFdt_per30s']  = window['lyman_alpha_121_6nm_Wm2'].diff()
window['euv_dFdt_per30s']  = window['euv_25_6nm_Wm2'].diff()

# If you prefer rate in W/m²/s divide by 30
window['lya_dFdt_per_s']   = window['lya_dFdt_per30s'] / 30.0
window['euv_dFdt_per_s']   = window['euv_dFdt_per30s'] / 30.0

# Write to CSV
window.index.name = 'time_utc'
window.to_csv('goes19_euv_lya_roc_20260510.csv', date_format='%Y-%m-%dT%H:%M:%S')
print(window)
