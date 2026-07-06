# with help from laude CAI Sonnet 4.6
# Get the .nc file from 
# GOES satelittes go into eclipse, so may not return GOES 19 data, and may need GOES 18
# Gets time interval from sat_data.ini in config sub folder


import sys
import requests
import re
import os
import configparser
import ast
import xarray as xr
import pandas as pd



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
  
csv_output_dir=os.path.join(base_directory,'output','csv','GOES')
if not os.path.exists(csv_output_dir):       
  os.makedirs(csv_output_dir)
    
def fetch_goes19_exis_sfeu(date_str, outdir='.'):
    """
    date_str: 'YYYYMMDD'
    Downloads operational GOES-19 EXIS L1b SFEU (EUV) file from NCEI.
    """
    year  = date_str[:4]
    month = date_str[4:6]

    base = ('https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/'
            f'goes/goes19/l1b/exis-l1b-sfeu/{year}/{month}/')

    print(f"Checking: {base}")
    r = requests.get(base)
    print(f"Status: {r.status_code}")

    if r.status_code != 200:
        print("Directory not found")
        return None

    # Match ops_ prefix and version pattern from your example filename
    pattern = rf'(ops_exis-l1b-sfeu_g19_d{date_str}_v[\d-]+\.nc)'
    match = re.search(pattern, r.text)

    if match:
        fname   = match.group(1)
        url     = base + fname
        outpath = os.path.join(outdir, fname)
        print(f"Downloading {fname}...")
        with requests.get(url, stream=True) as resp:
            with open(outpath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"Saved to {outpath}")
        return outpath
    else:
        print("File not found in directory listing")
        print("Directory contents snippet:")
        print(r.text[:1000])
        return None

# Usage
fpath = fetch_goes19_exis_sfeu(f'{YEAR:04d}{MONTH:02d}{DAY:02d}', outdir=nc_output_dir)
ds = xr.open_dataset(fpath)
sys.exit()

# Convert to dataframe
df = ds[['xrsa_flux', 'xrsb_flux', 'xrsa_flags', 'xrsb_flags']].to_dataframe()

# Trim to the flare window
window = df[f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} {HOUR_START:02d}:{MIN_START:02d}":f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} {HOUR_END:02d}:{MIN_END:02d}"].copy()

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

# Write to CSV with an explicit ISO 8601 format with a dynamic filename based on your variables
csv_filename = f"goes19_xrs_{YEAR:04d}{MONTH:02d}{DAY:02d}_{HOUR_START:02d}{MIN_START:02d}_{HOUR_END:02d}{MIN_END:02d}.csv"
filename = os.path.join(csv_output_dir, csv_filename)
df_out.to_csv(filename, date_format='%Y-%m-%dT%H:%M:%S')
print(f"Saved {len(df_out)} rows to {filename}")
