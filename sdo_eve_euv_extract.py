# Written by Clause AI Sonnet 4.6 with checks by Gwyn Griffiths G3ZIL
# Data access for Level 1 data at 4 Hz via links for the Solar Dynamics Observatory EVE sensor
# at https://lasp.colorado.edu/eve/data_access/index.html
# The ESP functions as an advanced, high-speed transmission grating spectrograph.
# It operates at a rapid 4 Hz cadence to capture instantaneous flare fluctuations and provides vital
# in-flight cross-calibration for the main MEGS channels.
# It features broad band channels centered around five specific targets:
# 0.1–7 nm quadrant photodiode soft X-rays and four eUV bands: 18 nm, 26 nm, 30 nm Helium II, 36 nm
#
# Two command line arguments: .fit data file name, which can be .gz and cadence in seconds for the averaging
# Date and time are input via a sdo_eve.ini file in the config subdirectory

from astropy.io import fits
import numpy as np
import pandas as pd
import sys
import configparser
import ast
import os

datafile=str(sys.argv[1])            # First command line argument, .fit file name, can be .gz
cadence=int(sys.argv[2])             # Second command line argument, averaging interval in seconds

print("Extracting data from file: ", datafile, " averaging to: ", cadence, "s cadence")

# set up base directory, and the directory path for inout and output files 
base_directory='./'

# ---------------------------------------------------------------------------
# Configuration from ./config/sdo_eve.ini
# ---------------------------------------------------------------------------
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

fit_input_dir=os.path.join(base_directory,'input','EVE_ESP')
if not os.path.exists(fit_input_dir):       
  os.makedirs(fit_input_dir)
    
csv_output_dir=os.path.join(base_directory,'output','csv','EVE_ESP')
if not os.path.exists(csv_output_dir):       
  os.makedirs(csv_output_dir)

hdul = fits.open(fit_input_dir + "/" + datafile)
data = hdul[1].data
hdul.close()

def to_native(arr):
    return arr.byteswap().view(arr.dtype.newbyteorder())

# Extract time components
year = to_native(data['YEAR'])
doy  = to_native(data['DOY'])
sod  = to_native(data['SOD'])   # seconds of day

# Build datetime index
base = pd.Timestamp(f"{YEAR}-{MONTH}-{DAY}T00:00:00")  # This is modern string concatenation with variables
timestamps = pd.to_datetime(sod, unit='s', origin=base)

# Extract channels
df = pd.DataFrame({
    'qd_Wm2':    to_native(data['QD']),           # 0.1 to 7.0 nm Quad Diode
    'ch18_Wm2':  to_native(data['CH_18']),        # 16.64–21.5 nm, targeting emissions from highly ionized iron
    'ch26_Wm2':  to_native(data['CH_26']),        # between 22.28–28.78 nm, monitoring hot coronal plasma and active regions
    'ch30_Wm2':  to_native(data['CH_30']),        # 27.16–33.8 nm,  dominated by He II 30.4 nm line originating in the upper chromosphere and transition
    'ch36_Wm2':  to_native(data['CH_36']),        # 33.3–40.04 nm, measuring coronal iron line irradiances (such as Fe XVI). COMPROMISED sensor.
}, index=timestamps)
df.index.name = 'time_utc'

# Trim to flare window
# This automatically forces integers like 5 into strings like '05'
window = df[f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} {START_HOUR:02d}:{START_MIN:02d}":f"{YEAR:04d}-{MONTH:02d}-{DAY:02d} {END_HOUR:02d}:{END_MIN:02d}"].copy()

# Resample to cadence-second bins
avg = window.resample(f"{cadence}s").mean()

# Rate of change for CH_30 (He II 30.4 nm) and CH_26, scaled to per second
avg['ch30_dFdt_per_s'] = avg['ch30_Wm2'].diff() / cadence
avg['ch26_dFdt_per_s'] = avg['ch26_Wm2'].diff() / cadence

# Save to CSV
filename = os.path.join(csv_output_dir, ".".join(datafile.split(".")[:-2]) + ".csv")
avg.to_csv(filename, date_format='%Y-%m-%d %H:%M:%S')
print(avg)
print(f"\nSaved {len(avg)} rows into file:", filename)

