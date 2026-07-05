# Google. (2026). Gemini large language model. 
# AI consultation for SDO/AIA data extraction and SI conversion scripts. Generated on 6 June 2026.
# Checked and tested by Gwyn Griffiths G3ZIL

# Data extracted for 30.4 HeII emission from Solar Dynamics Observatory
# Atmospheric Imaging Assembly
# https://svs.gsfc.nasa.gov/3828/
# Geosync orbit at 35,789 km 102˚W inclination 28.5 degrees

import numpy as np
import datetime
import drms
import pandas as pd
import configparser
import ast
import os

# ---------------------------------------------------------------------------
# Configuration from ./config/sdo_eve.ini
# ---------------------------------------------------------------------------
# set up base directory, and the directory path for output file 
base_directory='./'
config_file = base_directory+"config/sdo_eve.ini"
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

csv_output_dir=os.path.join(base_directory,'output','csv','SDO_AIA')
if not os.path.exists(csv_output_dir):       
  os.makedirs(csv_output_dir)

# SDO AIA data is at the Joint Science Operations Centre: https://docs.sunpy.org/en/latest/tutorial/acquiring_data/jsoc.html
# 1. Initialize the JSOC/DRMS client
client = drms.Client()

# 2. Construct the query string for SDO/AIA 30.4 nm (12-second cadence)
series = 'aia.lev1_euv_12s'
t_start = f"{YEAR:04d}.{MONTH:02d}.{DAY:02d}_{HOUR_START:02d}:{MIN_START:02d}:00_TAI"
t_end = f"{YEAR:04d}.{MONTH:02d}.{DAY:02d}_{HOUR_START:02d}:{MIN_START:02d}:00_TAI"

#t_start = '2026.05.10_13:25:00_TAI'
#t_end = '2026.05.10_13:40:00_TAI'
qstr = f"{series}[{t_start}-{t_end}][? WAVELNTH = 304 ?]"

print("Querying JSOC database for high-precision AIA 304 light curve...")
result = client.query(qstr, key=['T_REC', 'DATAMEAN'])

# 3. Process the timestamps and apply the SI conversion factor
time_pandas = drms.to_datetime(result['T_REC'])
time_utc = np.array([t.to_pydatetime() for t in time_pandas])

# AIA 304nm Calibration Factor: converts DN/s/pixel to Watts/m^2
CALIBRATION_FACTOR = 4.96e-20
flux_304_si = result['DATAMEAN'].values * CALIBRATION_FACTOR

# 4. Compute the calibrated Rate of Change (dI/dt)
dt = np.diff([t.timestamp() for t in time_utc])
dI = np.diff(flux_304_si)

euv_rate_of_change = dI / dt
rate_times = time_utc[1:]

# 5. Save data directly to a clean CSV file
# Format times to standard ISO strings for cross-analysis with CHU/WWV
df_export = pd.DataFrame({
    'UTC_Timestamp': [t.strftime('%Y-%m-%d %H:%M:%S') for t in rate_times],
    'EUV_Flux_W_per_m2': flux_304_si[1:],
    'EUV_Rate_Of_Change_W_per_m2_per_sec': euv_rate_of_change
})
csv_filename = os.path.join(csv_output_dir, "sdo_aia_304_rate_of_change.csv")
df_export.to_csv(csv_filename, index=False)
print(f"Data values successfully written to '{csv_filename}'")


