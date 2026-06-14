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
### Synthetic spectrogram scripts

