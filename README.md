# Installation 
This software has been tested on Linux Ubuntu 24.04.

### Download
You need to clone the package from github.com and run the software in the madrigal_fetch sub-directory. 
```
cd ~
git clone https://github.com/g3zil/madrigal_fetch.git
cd ~/madrigal_fetch
```
Execute all further commands in the ~/madrigal_fetch directory.
Updates can be downloaded with:
```
git pull
```

## Requirements
### Externally managed environment
The code has been tested with python 3.12.3 on Ubuntu Linux 24.04 LTS. A virtual environment is created and activated in the directory ~/madrigal_fetch/.venv, the latest version of pip is installed, and the required modules installed. Check your python3 version and use instead of 3.12 in the first line below if appropriate.
```
sudo apt install python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```
### madrigal_ft8_query.py
This is a rough and ready python script to query the Madrigal database at https://cedar.openmadrigal.org to obtain FT8 data between user-selected hours on a user-selected day. The user enters those parameters by editing the script (e.g. using nano). The lines to edit can be found in the Configuration block near the top of the script.

Note that data in hdf5 format will have to be downloaded for the whole day to a) extract FT8 and b) extract the time period required into a csv file. The downloaded file may be about 8 GB. It will take time. There appears to be no way of sub-selecting prior to download where a file is over 200 MB.

The output is a csv file e.g. ft8_10may2026_1200_1500utc.csv, the first lines of which read:
datetime_utc,ut1_unix,smode,tfreq,sn,txlat,txlon,rxlat,rxlon,pthlen,call_sign_tx,call_sign_rx
2026-05-10 12:00:00+00:00,1778414400,FT8,14074769.0,-9.0,,,51.35416666666667,-2.3750000000000004,,PA2BUL,G0KTN
2026-05-10 12:00:00+00:00,1778414400,FT8,14075508.0,-2.0,51.5,5.0,37.5,-1.0,1626.4515912077095,PA2WDR,AO5RKB
2026-05-10 12:00:00+00:00,1778414400,FT8,14075507.0,-5.0,51.5,5.0,28.64583333333333,-13.875,2986.6180017555675,PA2WDR,EA8/DF4UE
2026-05-10 12:00:00+00:00,1778414400,FT8,14075515.0,-14.0,51.5,5.0,47.4375,19.375,1130.2662531780377,PA2WDR,HG0NPJ

Linux tools, e.g. grep, can be used to extract lines matching a required band, e.g. grep ",1407" for 14 MHz, or a callsign.


