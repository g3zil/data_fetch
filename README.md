# Installation 
This software has been tested on Linux Ubuntu 24.04.

### Download
You need to clone the package from github.com and run the software in the data_fetch sub-directory. 
```
cd ~
git clone https://github.com/g3zil/data_fetch.git
cd ~/data_fetch
```
Execute all further commands in the ~/data_fetch directory.
Updates can be downloaded with:
```
git pull
```

## Requirements
### Externally managed environment
The code has been tested with python 3.12.3 on Ubuntu Linux 24.04 LTS. A virtual environment is created and activated in the directory ~/data_fetch/.venv, the latest version of pip is installed, and the required modules installed. Check your python3 version and use instead of 3.12 in the first line below if appropriate.
```
sudo apt install python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```
### madrigal_8038_query.py
This is a rudimentary python script to query the Madrigal database at https://cedar.openmadrigal.org to obtain FT8, WSPR or CW data between user-selected hours on a user-selected day. The user enters those parameters by editing the 8038.ini file in the config subdirectory. Also in 8038.ini the user gives their credentials. (It is called 8308 as that is the MADRIGAL designator for Amateur Radio Data).

Execute using:
```
python3 madrigal_8308_query.py
```

Note that data in hdf5 format will be downloaded for the whole day to a) extract the wanted mode and b) extract the time period required into a csv file. The downloaded file may be about 8 GB. It will take time. There appears to be no way of sub-selecting prior to download where a file is over 200 MB.

The output is a csv file e.g. FT8-2026-5-10-1200-1500.csv in the directory ./output/csv/FT8, or subdirectory WSPR or CW, the first lines of which read:
datetime_utc,ut1_unix,smode,tfreq,sn,txlat,txlon,rxlat,rxlon,pthlen,call_sign_tx,call_sign_rx
2026-05-10 12:00:00+00:00,1778414400,FT8,14075507.0,-5.0,51.5,5.0,28.64583333333333,-13.875,2986.6180017555675,PA2WDR,EA8/DF4UE
2026-05-10 12:00:00+00:00,1778414400,FT8,14075515.0,-14.0,51.5,5.0,47.4375,19.375,1130.2662531780377,PA2WDR,HG0NPJ

The hdf5 file is cached for extraction of a different mode and is in directory ./output/hdf5

Subsequent processing is up to the user. Linux tools, e.g. grep, can be used to extract lines matching a required band or other sensible wildcards, e.g. grep ",1407" for 14 MHz band.

### sdo_eve_euv_extract.py
The user has to find and download the *.fit.gz file for the day of interest and copy into the ~/data_fetch/input/EVE_ESP directory. The filename must look like the following esp_L1_2026130_008.fit.gz, that is it must be a .fit file and it can be .gz, or not.

This is a rough and ready python script to then extract soft X-ray and eUV Level 1 data from five channels for the NASA Solar Dynamics Observatory EUV Variability Experiment (EVE) satellite's ESP instrument. Level 1 data is at 4 Hz cadence. Full details, and data access, are via links on the NASA/University of Colorado SDO-EVE [page](https://lasp.colorado.edu/eve/data_access/index.html)). The file name is the first command line parameter and the cadence to average to is the second (in seconds).

Execute using:
```
python3 sdo_eve_euv_extract.py esp_L1_2026130_008.fit.gz 10
```
The output is a csv file with the same root name as the raw data file and in the directory ./output/csv/ESP_EVE.

### sdo_aia_extract.py

This is a rough and ready python script to then extract eUV flux data from the 30.4 nm channel of NASA Solar Dynamics Observatory AIA instrument. AIA is the Atmospheric Imaging Assembly, that is an imager rather than a radiometer. Cadence is 12 seconds. This script fetches the data for the interval requested in the sdo_eve.ini file in the config subdirectory. SDO AIA data is at the [Joint Science Operations Centre](https://docs.sunpy.org/en/latest/tutorial/acquiring_data/jsoc.html)

Execute using:
```
python3 sdo_eve_euv_extract.py 
```
The output is a csv file sdo_aia_304_20260510.csv where 20260510 is Year, Month, Day in the directory ./output/csv/SDO_AIA.

### lyra_euv_extract.py

This is a rough and ready python script to extract eUV flux data for the Lyman alpha and 17-80 nM (aluminium filter) channels of the ESA PROBA2 satellite's LYRA sensor instrument. See [PROBA2 Science Centre](https://proba2.sidc.be/). This script fetches the data for the interval requested in the sat_data.ini file using sunpy. Cadence is set by the single command line parameter seconds. 3s is fine for flux level, but 10 s advised for rate of change.

Execute using:
```
python3 lyra_euv_extract.py 10
```
The output is a csv file lyra_euv_20260510_1300_1350.csv where 20260510 is Year, Month, Day followed by the time interval in the directory ./output/csv/LYRA.


