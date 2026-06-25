import xarray as xr
import pandas as pd
import sys
# with help from laude AI Sonnet 4.6
# Get the .nc file from
# https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/goes19/l2/data/xrsf-l2-flx1s/2026/05/
# GOES satelittes go into eclipse, so data for this time from GOES 19 rather than 18

ds = xr.open_dataset('./dn_xrsf-l2-flx1s_g19_d20250615_v2-2-1.nc')

# Convert to dataframe
df = ds[['xrsa_flux', 'xrsb_flux', 'xrsa_flags', 'xrsb_flags']].to_dataframe()

# Trim to the flare window
window = df['2025-06-15 17:00':'2025-06-15 20:00']
print(window)

# The main columns are typically 'xrsa_flux' (0.05–0.4 nm) and 'xrsb_flux' (0.1–0.8 nm)
# Keep only the flux channels (drop any quality flag columns if not needed)
flux_cols = [c for c in window.columns if 'xrsa_flux' in c or 'xrsb_flux' in c]
df_out = window[flux_cols].copy()

# Rename for clarity
df_out.index.name = 'time_utc'
df_out.rename(columns={
    'xrsa_flux': 'xrsa_flux_Wm2',   # 0.05–0.4 nm
    'xrsb_flux': 'xrsb_flux_Wm2',   # 0.1–0.8 nm
}, inplace=True)

# Ensure the index is a proper DatetimeIndex with full timestamps
df_out.index = pd.to_datetime(df_out.index)

# Write to CSV with an explicit ISO 8601 format
output_path = 'goes19_xrs_20250615.csv'
df_out.to_csv(output_path, date_format='%Y-%m-%dT%H:%M:%S')
print(f"Saved {len(df_out)} rows to {output_path}")

