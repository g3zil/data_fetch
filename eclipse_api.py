# Script specifically for the 12 August 2026 eclipse for use with Grafana dashboard 
# It calculates obscuration percent at a lat and lon set in the Grafana dashboard template variables
# Over the time interval hard-coded in function calculate_eclipse
# It also calculates the sun elevation and an irrandiance factor, sine of the sun elevation times (1-obscuration)
# The computed values are put into a postgresql database table on the localhost and hence available for a Grafana panel.
# The end-to-end method is usable for other similar home-brew plug-in like modules.
# Written with Claude AI Sonnet v4.6 July 2026 Gwyn Griffiths G3ZIL Version 1


import math
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Query
from skyfield.api import Topos, load
import psycopg2
from fastapi.middleware.cors import CORSMiddleware
import numpy as np

app = FastAPI()

# Database Connection Settings
DB_PARAMS = {
    "dbname": "local_meas",
    "user": "postgres",
    "password": "GW3ZIL",
    "host": "localhost",
    "port": 5432
}

# Load Ephemeris Data once on startup
ephemeris = load('de421.bsp')
sun, moon, earth = ephemeris['sun'], ephemeris['moon'], ephemeris['earth']
ts = load.timescale()

@app.get("/calculate-eclipse")
def calculate_eclipse(lat: float = Query(...), lon: float = Query(...)):
    # 1. Define the 2026 Eclipse window (UTC)
    start_time = datetime(2026, 8, 12, 16, 0, 0, tzinfo=timezone.utc)
    end_time   = datetime(2026, 8, 12, 21, 0, 0, tzinfo=timezone.utc)

    observer = earth + Topos(latitude_degrees=lat, longitude_degrees=lon)
    current_time = start_time
    rows_to_insert = []

    # 2. Loop through the afternoon in 1-minute increments
    while current_time <= end_time:
        t = ts.utc(current_time.year, current_time.month, current_time.day,
           current_time.hour, current_time.minute, current_time.second)
        obs = observer.at(t)

        sun_app  = obs.observe(sun).apparent()
        moon_app = obs.observe(moon).apparent()
        separation = sun_app.separation_from(moon_app).radians

        # ── Obscuration ──────────────────────────────────────────────────────
        r_sun  = 0.00465
        r_moon = 0.00475

        if separation >= (r_sun + r_moon):
            obscuration = 0.0
        elif separation <= abs(r_sun - r_moon):
            obscuration = 100.0
        else:
            d1   = (r_sun**2 - r_moon**2 + separation**2) / (2 * separation)
            d2   = separation - d1
            area = (r_sun**2  * math.acos(d1 / r_sun)  - d1 * math.sqrt(r_sun**2  - d1**2) +
                    r_moon**2 * math.acos(d2 / r_moon) - d2 * math.sqrt(r_moon**2 - d2**2))
            obscuration = (area / (math.pi * r_sun**2)) * 100.0
            obscuration = max(0.0, min(100.0, obscuration))

        # ── Sun elevation ────────────────────────────────────────────────────
        # apparent() already computed above; use altaz to get elevation
        alt, az, distance = sun_app.altaz()
        sun_elevation_deg = alt.degrees          # positive = above horizon

        # ── Irradiance proxy ─────────────────────────────────────────────────
        # (100 - obscuration) gives the unobscured fraction as a percentage.
        # Multiplying by cos(solar zenith angle) = sin(elevation) weights it
        # by the actual solar incidence angle, giving a proxy for available
        # solar irradiance relative to a clear overhead sun = 100.
        solar_zenith_deg  = 90.0 - sun_elevation_deg
        cos_sza           = max(0.0, math.cos(math.radians(solar_zenith_deg)))
        irradiance_proxy  = (100.0 - obscuration) * cos_sza

        rows_to_insert.append((
            current_time,
            lat,
            lon,
            obscuration,
            sun_elevation_deg,
            irradiance_proxy,
        ))
        current_time += timedelta(minutes=1)

    # ── Database ─────────────────────────────────────────────────────────────
    conn   = psycopg2.connect(**DB_PARAMS)
    cursor = conn.cursor()

    # Create/extend tracking table if missing
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eclipse_predictions (
            time              TIMESTAMPTZ,
            latitude          NUMERIC,
            longitude         NUMERIC,
            obscuration       NUMERIC,
            sun_elevation_deg NUMERIC,
            irradiance_proxy  NUMERIC,
            PRIMARY KEY (time, latitude, longitude)
        );
    """)

    # Add new columns to existing table if this is an upgrade from the old schema
    for col, typ in [("sun_elevation_deg", "NUMERIC"), ("irradiance_proxy", "NUMERIC")]:
        cursor.execute(f"""
            ALTER TABLE eclipse_predictions
            ADD COLUMN IF NOT EXISTS {col} {typ};
        """)

    # Clear previous run for these coordinates
    cursor.execute("DELETE FROM eclipse_predictions")

    # Batch insert
    cleaned_rows = [
        (
            row[0].strftime('%Y-%m-%d %H:%M:%S+00'),
            float(row[1]),
            float(row[2]),
            round(float(row[3]),2),
            round(float(row[4]), 2),
            round(float(row[5]), 2),        )
        for row in rows_to_insert
    ]

    cursor.executemany(
        """
        INSERT INTO eclipse_predictions
            (time, latitude, longitude, obscuration, sun_elevation_deg, irradiance_proxy)
        VALUES
            (%s::timestamptz, %s::numeric, %s::numeric,
             %s::numeric,     %s::numeric, %s::numeric)
        ON CONFLICT (time, latitude, longitude) DO UPDATE SET
            obscuration       = EXCLUDED.obscuration,
            sun_elevation_deg = EXCLUDED.sun_elevation_deg,
            irradiance_proxy  = EXCLUDED.irradiance_proxy
        """,
        cleaned_rows
    )

    conn.commit()
    cursor.close()
    conn.close()

    return {"status": "success", "points_generated": len(rows_to_insert)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

#------------------------------------------------------
# The following query is what is needed in a Grafana panel (again on localhost) to 'trigger' this python module
#
# WITH trigger_api AS (
#    SELECT content
#     FROM http_get(
#     -- Concatenate the base URL with your Grafana template variables
#     'http://10.0.1.245:8000/calculate-eclipse?lat=' || ${mid_lat:csv} || '&lon=' || ${mid_lon:csv}
#   )
# )
# SELECT content FROM trigger_api; 
#
# And to get the data from table eclipse_predictions is another query,
# 
# SELECT 
#   -- 1. Calculate the day offset between the selected day and the eclipse day, 
#   -- then shift the astronomical data time to look like it is happening today.
#   "time" + (DATE_TRUNC('day', $__timeFrom()::timestamptz) - '2026-08-12'::timestamp) AS "time",
#   obscuration AS "Eclipse Obscuration (%)", irradiance_proxy, 100*sin(sun_elevation_deg/(180/3.14159)) as "sin_sun_elevation"
# FROM 
#   eclipse_predictions
# ORDER BY 
#   1 ASC;
#
# To get this to run I had to install modules in a virt env and postgresql http support using:
# sudo apt install python3.12-venv
#python3 -m venv .venv
#source .venv/bin/activate
#sudo su postgres
#sudo apt update
#sudo apt install postgresql-14-http
#sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
#wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
#sudo apt update
#sudo apt install postgresql-14-http
#sudo systemctl restart postgresql
#pip install fastapi uvicorn skyfield psycopg2-binary
#
# And then to install the modules and as a service...
#sudo nano /etc/systemd/system/eclipse-api.service
#
# Which should contain the following:
#[Unit]
#Description=FastAPI Eclipse Calculation API
#After=network.target
#
#[Service]
# User and Group running the service (usually 'ubuntu' or your username)
#User=gwyn
#Group=gwyn

## The directory where your eclipse_api.py script is located
#WorkingDirectory=/home/gwyn/kiwi_on_mac

## The path to your Python executable and script
## If using a virtual environment, change this to /home/ubuntu/eclipse/venv/bin/python
#ExecStart=/home/gwyn/kiwi_on_mac/.venv/bin/python eclipse_api.py

## Restart policy: automatically restart if the script crashes
#Restart=always
#RestartSec=5

## Environment variables (optional, helpful if you use custom ports)
#Environment=PYTHONUNBUFFERED=1
#
#[Install]
#WantedBy=multi-user.target
#
# Th reload and restart
#sudo systemctl daemon-reload
#sudo systemctl restart eclipse-api.service
#sudo journalctl -u eclipse-api.service -f   # monitors in real time
#
# hopefully I have got most of the steps...
