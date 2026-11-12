#!/usr/bin/env python3
"""
dTEC_polar_movie.py
Code written by Anthropic Claude AI Sonnet v5.5 under instructions and iterations with Gwyn Griffiths G3ZIL
November 2026
Make a movie of detrended TEC from the ISEE (Nagoya University) hourly netCDF
files, drawn in an azimuthal equidistant projection centred on the north
geomagnetic pole, with geographic coastlines (option A).

Reads ./config/dTEC_config.ini.  The existing [datetime], [movie] and [paths]
sections work as they are; everything below is optional:

    [datetime]            (UT; frames from start to end inclusive)
    YEAR=2024
    MONTH=5
    DAY=17
    HOUR_START=17
    HOUR_END=20
    MIN_START=0
    MIN_END=0

    [movie]
    FRAME_RATE=5
    STEP_MIN=5            ; 5 = every frame in the files, 10 = every second one

    [paths]
    NC_DIR=./dtec_nc                  ; downloaded hourly .nc files (~50 MB each)
    FRAME_DIR=./dtec_polar_frames     ; PNG frames
    OUTPUT_DIR=./output/plots/dTEC    ; mp4 goes here

    [map]
    POLE_LAT=80.7         ; north geomagnetic (centred dipole) pole, 2024
    POLE_LON=-72.7
    RADIUS_DEG=65         ; map radius, degrees of arc from the pole
    VMIN=-0.4
    VMAX=0.4
    CMAP=isee             ; "isee" (ISEE-like colours) or any matplotlib name
    MISSING_COLOR=white   ; colour for cells with no data
    HIDE_BELOW=-0.4       ; cells at or below this value are not plotted (the
                          ; black speckle); default = VMIN, "none" plots them
    HIDE_LAT_MIN=66       ; do not plot geographic latitudes above this ...
    HIDE_LON_MIN=-180     ; ... between these longitudes (west of Greenwich
    HIDE_LON_MAX=0        ; to the antimeridian); HIDE_LAT_MIN=90 switches off
    MAG_RINGS=1           ; dipole geomagnetic latitude rings (0 to switch off)
    COAST_RES=50m         ; Natural Earth resolution: 110m, 50m or 10m
    GRID_PX=800           ; resolution of the regridded map image

    [annotation]          (optional; any number of RX sites: RX_*_1, _2, _3 ...)
    TX_IDENT=WWV
    TX_LAT=40.678
    TX_LON=-105.047
    RX_IDENT_1=N4RVE
    RX_LAT_1=48.54
    RX_LON_1=-123.07
    RX_IDENT_2=N5BRG
    RX_LAT_2=33.467
    RX_LON_2=-97.081
    PATH_LINES=1          ; great-circle line from the TX to each RX (0 = off)

The transmitter is drawn as a gold star, each receiver with its own symbol
(white, black edge) and the great-circle midpoint of each TX-RX path with the
same symbol in solid black.  A legend sits under the colour bar, with the\nclock time repeated between the two (so a player's black banner cannot hide it).

Needs: numpy, matplotlib, ffmpeg, and one of netCDF4 / xarray / scipy (scipy
only reads NetCDF-3 files).  cartopy is used only to fetch the Natural Earth
coastline and border lines (downloaded on first use); without it the map is
drawn without coastlines.

All times are UT.
"""

import configparser
import copy
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle

BASE_URL = "https://stdb2.isee.nagoya-u.ac.jp/GPS/shinbori/GRID2/nc"
CONFIG_INI = Path("./config/dTEC_config.ini")
R_EARTH = 6370997.0        # sphere radius in metres (same as PROJ "sphere")
MISSING = 900.0            # the files flag missing data as 999

# Colours chosen to resemble the ISEE colour bar: black at -0.4, purple,
# blue, cyan, green near 0, yellow near +0.2, red at +0.4.
ISEE_CMAP = LinearSegmentedColormap.from_list(
    "isee",
    [(0.00, "#000000"), (0.125, "#4b0082"), (0.25, "#0000ff"),
     (0.40, "#00ffff"), (0.50, "#00ff00"), (0.75, "#ffff00"),
     (1.00, "#ff0000")],
)


# --------------------------------------------------------------------------
# configuration and file handling
# --------------------------------------------------------------------------

def read_ini(path):
    if not path.is_file():
        sys.exit(f"Config file not found: {path}")
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cp.read(path)
    return cp


def get_interval(cp):
    s = cp["datetime"]
    y, mo, d = int(s["YEAR"]), int(s["MONTH"]), int(s["DAY"])
    start = datetime(y, mo, d, int(s["HOUR_START"]), int(s.get("MIN_START", 0)))
    end = datetime(y, mo, d, int(s["HOUR_END"]), int(s.get("MIN_END", 0)))
    if end < start:
        sys.exit("End time is before start time - check dTEC_config.ini")
    return start, end


def hours_needed(start, end):
    t = start.replace(minute=0, second=0)
    while t <= end:
        yield t
        t += timedelta(hours=1)


def nc_name_url(hour):
    doy = hour.timetuple().tm_yday
    name = f"{hour:%Y%m%d%H}_dtec.nc"
    return name, f"{BASE_URL}/{hour.year}/{doy:03d}/{name}"


def download(url, dest, retries=3):
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dTEC_polar_movie.py"})
    err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        print(f"\r    {done / 1e6:6.1f} / {total / 1e6:.1f} MB",
                              end="", flush=True)
            print()
            part.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            print()
            if e.code == 404:
                return False
            err = e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print()
            err = e
        if attempt < retries:
            time.sleep(3 * attempt)
    print(f"    failed: {err}")
    part.unlink(missing_ok=True)
    return False


def _normalise(lat, lon, tsec, units, arr, dims):
    """Return lat, lon, list of datetimes, dtec[lat, lon, time] with NaN gaps."""
    names = [d.lower() for d in dims]
    try:
        order = [next(i for i, n in enumerate(names) if n.startswith("lat")),
                 next(i for i, n in enumerate(names) if n.startswith("lon")),
                 next(i for i, n in enumerate(names) if n.startswith("time"))]
    except StopIteration:
        order = [0, 1, 2]
    arr = np.transpose(np.asarray(arr, dtype=float), order)
    arr = np.where(np.isfinite(arr) & (np.abs(arr) < MISSING), arr, np.nan)

    m = re.search(r"since\s+(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2}))?",
                  units)
    if not m:
        raise ValueError(f"cannot parse time units: {units!r}")
    parts = [int(g) if g else 0 for g in m.groups()]
    base = datetime(*parts)
    times = [base + timedelta(seconds=float(s)) for s in np.asarray(tsec).ravel()]
    return (np.asarray(lat, dtype=float).ravel(),
            np.asarray(lon, dtype=float).ravel(), times, arr)


def read_nc(path):
    errors = []
    try:
        from netCDF4 import Dataset
        ds = Dataset(str(path))
        try:
            def get(n):
                return np.ma.filled(np.ma.asarray(ds.variables[n][:]).astype(float),
                                    np.nan)
            return _normalise(get("lat"), get("lon"), get("time"),
                              ds.variables["time"].units,
                              get("dtec"), ds.variables["dtec"].dimensions)
        finally:
            ds.close()
    except ImportError:
        errors.append("netCDF4 not installed")
    except Exception as e:
        errors.append(f"netCDF4: {e}")
    try:
        import xarray as xr
        ds = xr.open_dataset(path, decode_times=False)
        try:
            return _normalise(ds["lat"].values, ds["lon"].values, ds["time"].values,
                              ds["time"].attrs["units"], ds["dtec"].values,
                              ds["dtec"].dims)
        finally:
            ds.close()
    except ImportError:
        errors.append("xarray not installed")
    except Exception as e:
        errors.append(f"xarray: {e}")
    try:
        from scipy.io import netcdf_file
        f = netcdf_file(str(path), "r", mmap=False)
        try:
            v = f.variables
            units = v["time"].units
            units = units.decode() if isinstance(units, bytes) else units
            return _normalise(v["lat"].data.copy(), v["lon"].data.copy(),
                              v["time"].data.copy(), units,
                              v["dtec"].data.copy(), v["dtec"].dimensions)
        finally:
            f.close()
    except ImportError:
        errors.append("scipy not installed")
    except Exception as e:
        errors.append(f"scipy: {e}")
    sys.exit(f"Could not read {path}:\n  " + "\n  ".join(errors) +
             "\n  (try: pip install netCDF4)")


# --------------------------------------------------------------------------
# azimuthal equidistant projection on a sphere
# --------------------------------------------------------------------------

def forward(lat, lon, lat0, lon0):
    """lat, lon (deg) -> x, y (m) and angular distance from the centre (deg)."""
    p, l = np.radians(lat), np.radians(lon)
    p0, l0 = np.radians(lat0), np.radians(lon0)
    dl = l - l0
    cosc = np.sin(p0) * np.sin(p) + np.cos(p0) * np.cos(p) * np.cos(dl)
    c = np.arccos(np.clip(cosc, -1, 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(c > 1e-9, c / np.sin(c), 1.0)
    x = R_EARTH * k * np.cos(p) * np.sin(dl)
    y = R_EARTH * k * (np.cos(p0) * np.sin(p) - np.sin(p0) * np.cos(p) * np.cos(dl))
    return x, y, np.degrees(c)


def inverse(x, y, lat0, lon0):
    """x, y (m) -> lat, lon (deg)."""
    p0, l0 = np.radians(lat0), np.radians(lon0)
    rho = np.hypot(x, y)
    c = rho / R_EARTH
    sinc, cosc = np.sin(c), np.cos(c)
    with np.errstate(invalid="ignore", divide="ignore"):
        arg = cosc * np.sin(p0) + np.where(rho > 0, y * sinc * np.cos(p0) / rho, 0.0)
    lat = np.arcsin(np.clip(arg, -1, 1))
    lon = l0 + np.arctan2(x * sinc, rho * np.cos(p0) * cosc - y * np.sin(p0) * sinc)
    return np.degrees(lat), (np.degrees(lon) + 180.0) % 360.0 - 180.0


def build_lookup(lat, lon, lat0, lon0, radius_deg, npx, hide=None):
    """Index arrays that turn a dtec[lat, lon] grid into a map image."""
    rm = np.radians(radius_deg) * R_EARTH
    xs = (np.arange(npx) + 0.5) / npx * 2 * rm - rm
    X, Y = np.meshgrid(xs, xs)               # row 0 = lowest y
    la, lo = inverse(X, Y, lat0, lon0)
    dlat = (lat[-1] - lat[0]) / (len(lat) - 1)
    dlon = (lon[-1] - lon[0]) / (len(lon) - 1)
    ilat = np.clip(np.rint((la - lat[0]) / dlat).astype(int), 0, len(lat) - 1)
    ilon = np.clip(np.rint((lo - lon[0]) / dlon).astype(int), 0, len(lon) - 1)
    outside = np.hypot(X, Y) > rm
    if hide is not None:                     # (lat_min, lon_min, lon_max) deg
        hlat, hlo0, hlo1 = hide
        outside = outside | ((la > hlat) & (lo >= hlo0) & (lo < hlo1))
    return rm, ilat, ilon, outside


# --------------------------------------------------------------------------
# map furniture
# --------------------------------------------------------------------------

def _runs(ok):
    """Start/stop indices of contiguous True runs."""
    idx = np.flatnonzero(np.diff(np.concatenate(([0], ok.view(np.int8), [0]))))
    return list(zip(idx[::2], idx[1::2]))


def project_line(lons, lats, lat0, lon0, max_deg):
    x, y, c = forward(np.asarray(lats), np.asarray(lons), lat0, lon0)
    segs = []
    for a, b in _runs(c <= max_deg):
        if b - a >= 2:
            segs.append(np.column_stack([x[a:b], y[a:b]]))
    return segs


def load_coast_lines(res):
    try:
        import cartopy.feature as cfeature
        feats = [cfeature.NaturalEarthFeature("physical", "coastline", res),
                 cfeature.NaturalEarthFeature("cultural",
                                              "admin_0_boundary_lines_land", res)]
        lines = []
        for f in feats:
            for g in f.geometries():
                for p in (list(g.geoms) if hasattr(g, "geoms") else [g]):
                    xy = np.asarray(p.coords)
                    if len(xy) >= 2:
                        lines.append(xy[:, :2])
        return lines
    except Exception as e:                      # no cartopy, or no network
        print(f"Warning: no coastlines ({type(e).__name__}: {e})")
        return []


def draw_furniture(ax, clip, lat0, lon0, radius_deg, rm, rings, coast_res):
    lim = radius_deg + 8.0
    grat = []
    lats = np.linspace(-10, 90, 401)
    lons = np.linspace(-180, 180, 721)
    for lo in range(-180, 180, 30):
        grat += project_line(np.full_like(lats, lo), lats, lat0, lon0, lim)
    for la in range(0, 90, 10):
        grat += project_line(lons, np.full_like(lons, la), lat0, lon0, lim)
    lc = LineCollection(grat, colors="0.45", linewidths=0.5, linestyles=":", zorder=3)
    ax.add_collection(lc)
    lc.set_clip_path(clip)

    # geographic longitude labels just outside the rim
    la_s = np.linspace(75, -10, 1000)
    for lo in range(-180, 180, 30):
        x, y, c = forward(la_s, np.full_like(la_s, lo), lat0, lon0)
        i = int(np.nanargmin(np.abs(c - radius_deg)))
        r = np.hypot(x[i], y[i])
        if r > 0:
            lab = "0°" if lo == 0 else "180°" if abs(lo) == 180 else \
                f"{abs(lo)}°{'E' if lo > 0 else 'W'}"
            ax.text(x[i] * 1.045, y[i] * 1.045, lab, ha="center", va="center",
                    fontsize=8, color="0.3")
    # geographic latitude labels down the central meridian
    for la in range(30, 80, 10):
        x, y, c = forward(la, lon0, lat0, lon0)
        if c < radius_deg - 2:
            ax.text(x + 0.012 * rm, y, f"{la}°N", fontsize=7, color="0.35",
                    va="center", zorder=6)

    if rings:                                   # dipole geomagnetic latitude
        for ml in range(30, 90, 10):
            r = np.radians(90 - ml) * R_EARTH
            if r < rm:
                ax.add_patch(Circle((0, 0), r, fill=False, ec="#a000a0", lw=0.9,
                                    ls="--", zorder=4))
                ax.text(r * np.cos(np.radians(160)), r * np.sin(np.radians(160)),
                        f"{ml}° mag", fontsize=7, color="#a000a0", ha="center",
                        va="bottom", zorder=6)

    # geomagnetic pole (centre) and geographic pole
    ax.plot([0], [0], "+", color="#a000a0", ms=10, mew=1.5, zorder=6)
    gx, gy, _ = forward(90.0, 0.0, lat0, lon0)
    ax.plot([gx], [gy], "o", color="k", ms=3, zorder=6)
    ax.text(gx + 0.012 * rm, gy, "geog. pole", fontsize=7, va="center", zorder=6)

    segs = []
    for xy in load_coast_lines(coast_res):
        segs += project_line(xy[:, 0], xy[:, 1], lat0, lon0, lim)
    if segs:
        cl = LineCollection(segs, colors="k", linewidths=0.7, zorder=5)
        ax.add_collection(cl)
        cl.set_clip_path(clip)


# --------------------------------------------------------------------------
# station annotation
# --------------------------------------------------------------------------

RX_MARKERS = ["o", "s", "^", "v", "D", "P", "X", "p", "h", "<", ">", "d"]


def read_annotations(cp):
    """Return (tx, rx_list); tx = (ident, lat, lon) or None, rx the same."""
    if not cp.has_section("annotation"):
        return None, []
    sec = cp["annotation"]

    def one(ident_key, lat_key, lon_key):
        ident = sec.get(ident_key)
        try:
            return ident.strip(), float(sec[lat_key]), float(sec[lon_key])
        except (AttributeError, KeyError, ValueError):
            print(f"Warning: [annotation] {ident_key} needs {lat_key} and "
                  f"{lon_key} as numbers - skipped")
            return None

    tx = one("TX_IDENT", "TX_LAT", "TX_LON") if "tx_ident" in sec else None
    nums = sorted(int(m.group(1)) for k in sec
                  if (m := re.fullmatch(r"rx_ident_(\d+)", k.lower())))
    rx = [r for n in nums
          if (r := one(f"RX_IDENT_{n}", f"RX_LAT_{n}", f"RX_LON_{n}"))]
    return tx, rx


def gc_midpoint(lat1, lon1, lat2, lon2):
    """Great-circle midpoint of two points (degrees)."""
    def vec(la, lo):
        la, lo = np.radians(la), np.radians(lo)
        return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    v = vec(lat1, lon1) + vec(lat2, lon2)
    v /= np.linalg.norm(v)
    return float(np.degrees(np.arcsin(v[2]))), float(np.degrees(np.arctan2(v[1], v[0])))


def gc_points(lat1, lon1, lat2, lon2, n=200):
    """Points along the great circle between two places (degrees)."""
    def vec(la, lo):
        la, lo = np.radians(la), np.radians(lo)
        return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    a, b = vec(lat1, lon1), vec(lat2, lon2)
    om = np.arccos(np.clip(a @ b, -1, 1))
    t = np.linspace(0, 1, n)[:, None]
    v = (np.sin((1 - t) * om) * a + np.sin(t * om) * b) / np.sin(om) if om > 1e-9 \
        else np.repeat(a[None, :], n, axis=0)
    return (np.degrees(np.arcsin(np.clip(v[:, 2], -1, 1))),
            np.degrees(np.arctan2(v[:, 1], v[:, 0])))


def draw_annotations(ax, tx, rx, lat0, lon0, radius_deg, path_lines=True):
    """Plot TX, RX and path midpoints; return legend (col0, col1) entries."""
    from matplotlib.lines import Line2D

    def place(lat, lon, **kw):
        x, y, c = forward(lat, lon, lat0, lon0)
        if c > radius_deg:
            return None
        return ax.plot([float(x)], [float(y)], ls="", zorder=8, clip_on=False, **kw)

    def handle(**kw):
        return Line2D([], [], ls="", **kw)

    if path_lines and tx:
        import matplotlib.patheffects as pe
        for ident, la, lo in rx:
            gl, go = gc_points(tx[1], tx[2], la, lo)
            for seg in project_line(go, gl, lat0, lon0, radius_deg):
                ax.plot(seg[:, 0], seg[:, 1], color="k", lw=1.2, zorder=7,
                        path_effects=[pe.Stroke(linewidth=2.8, foreground="white"),
                                      pe.Normal()])

    col0, col1 = [], []
    if tx:
        ident, la, lo = tx
        kw = dict(marker="*", ms=17, mfc="gold", mec="k", mew=1.2)
        if place(la, lo, **kw) is None:
            print(f"Warning: TX {ident} is outside the map")
        col0.append((handle(**kw), f"TX  {ident}"))
        col1.append((handle(), ""))
    for i, (ident, la, lo) in enumerate(rx):
        m = RX_MARKERS[i % len(RX_MARKERS)]
        kw = dict(marker=m, ms=9, mfc="white", mec="k", mew=1.4)
        if place(la, lo, **kw) is None:
            print(f"Warning: RX {ident} is outside the map")
        col0.append((handle(**kw), f"RX  {ident}"))
        if tx:
            mla, mlo = gc_midpoint(tx[1], tx[2], la, lo)
            kw2 = dict(marker=m, ms=7, mfc="k", mec="white", mew=1.0)
            if place(mla, mlo, **kw2) is None:
                print(f"Warning: midpoint {tx[0]}-{ident} is outside the map")
            col1.append((handle(**kw2), f"midpoint {tx[0]}-{ident}"))
    return col0, col1


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    cp = read_ini(CONFIG_INI)
    start, end = get_interval(cp)

    fps = cp.getfloat("movie", "FRAME_RATE", fallback=5.0)
    step = cp.getint("movie", "STEP_MIN", fallback=5)
    nc_dir = Path(cp.get("paths", "NC_DIR", fallback="./dtec_nc"))
    frame_dir = Path(cp.get("paths", "FRAME_DIR", fallback="./dtec_polar_frames"))
    out_dir = Path(cp.get("paths", "OUTPUT_DIR", fallback="./"))
    lat0 = cp.getfloat("map", "POLE_LAT", fallback=80.7)
    lon0 = cp.getfloat("map", "POLE_LON", fallback=-72.7)
    radius = cp.getfloat("map", "RADIUS_DEG", fallback=65.0)
    vmin = cp.getfloat("map", "VMIN", fallback=-0.4)
    vmax = cp.getfloat("map", "VMAX", fallback=0.4)
    cmap_name = cp.get("map", "CMAP", fallback="isee")
    bad = cp.get("map", "MISSING_COLOR", fallback="white")
    rings = cp.getint("map", "MAG_RINGS", fallback=1) != 0
    hb = cp.get("map", "HIDE_BELOW", fallback=None)
    if hb is None:
        hide_below = vmin
    elif hb.strip().lower() in ("", "none", "off"):
        hide_below = None
    else:
        hide_below = float(hb)
    hide = (cp.getfloat("map", "HIDE_LAT_MIN", fallback=66.0),
            cp.getfloat("map", "HIDE_LON_MIN", fallback=-180.0),
            cp.getfloat("map", "HIDE_LON_MAX", fallback=0.0))
    coast_res = cp.get("map", "COAST_RES", fallback="50m")
    npx = cp.getint("map", "GRID_PX", fallback=800)
    dpi = cp.getint("map", "DPI", fallback=120)
    tx, rx = read_annotations(cp)
    path_lines = cp.getint("annotation", "PATH_LINES", fallback=1) != 0
    for d in (nc_dir, frame_dir, out_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. get the hourly files -------------------------------------------------
    files = []
    for hour in hours_needed(start, end):
        name, url = nc_name_url(hour)
        dest = nc_dir / name
        if dest.is_file() and dest.stat().st_size > 1_000_000:
            print(f"have  {name}")
        else:
            print(f"get   {name}")
            if not download(url, dest):
                print(f"  MISSING {name} - its frames are skipped")
                continue
        files.append((hour, dest))
    if not files:
        sys.exit("No data files available.")

    # 2. set up the figure ------------------------------------------------------
    cmap = copy.copy(ISEE_CMAP if cmap_name.lower() == "isee"
                     else plt.get_cmap(cmap_name))
    cmap.set_bad(bad)
    lookup = None
    fig = ax = im = ttl = None

    frame_no = 0
    for old in frame_dir.glob("f[0-9][0-9][0-9][0-9][0-9].png"):
        old.unlink()

    # 3. render ---------------------------------------------------------------
    for hour, path in files:
        lat, lon, times, dtec = read_nc(path)
        if lookup is None:
            rm, ilat, ilon, outside = build_lookup(lat, lon, lat0, lon0, radius, npx, hide)
            lookup = True
            # layout in inches: legend, colour bar, map, title (bottom to top)
            W, mapw = 8.0, 7.5
            rows = (1 if tx else 0) + len(rx)
            leg_h = 0.24 * rows + 0.2 if rows else 0.0
            clock_h = 0.45                            # room for the clock time
            cbar_y = 0.10 + leg_h + clock_h + 0.65
            map_y = cbar_y + 0.2 + 0.15
            H = map_y + mapw + 0.55
            H = 2 * round(H * dpi / 2) / dpi          # even pixel height
            fig = plt.figure(figsize=(W, H))
            ax = fig.add_axes([(W - mapw) / 2 / W, map_y / H, mapw / W, mapw / H])
            cax = fig.add_axes([0.14, cbar_y / H, 0.72, 0.2 / H])
            ax.set_aspect("equal")
            ax.set_xlim(-1.12 * rm, 1.12 * rm)
            ax.set_ylim(-1.12 * rm, 1.12 * rm)
            ax.axis("off")
            clip = Circle((0, 0), rm, transform=ax.transData)
            blank = np.ma.masked_all((npx, npx))
            im = ax.imshow(blank, origin="lower", extent=[-rm, rm, -rm, rm],
                           cmap=cmap, vmin=vmin, vmax=vmax,
                           interpolation="nearest", zorder=2)
            im.set_clip_path(clip)
            ax.add_patch(Circle((0, 0), rm, fill=False, ec="k", lw=1.2, zorder=7))
            draw_furniture(ax, clip, lat0, lon0, radius, rm, rings, coast_res)
            fig.colorbar(im, cax=cax, orientation="horizontal", extend="both",
                         label=r"Detrended TEC  [$10^{16}$ el m$^{-2}$]")
            col0, col1 = draw_annotations(ax, tx, rx, lat0, lon0, radius, path_lines)
            clock = fig.text(0.5, (0.10 + leg_h + clock_h / 2) / H, "",
                             ha="center", va="center", fontsize=20,
                             fontweight="bold")
            if rows:
                ents = col0 + (col1 if rx and tx else [])
                fig.legend([h for h, _ in ents], [t for _, t in ents],
                           loc="lower center", bbox_to_anchor=(0.5, 0.10 / H),
                           ncol=2 if (rx and tx) else 1, fontsize=9,
                           columnspacing=2.5, handletextpad=0.8, borderpad=0.6)
            ttl = ax.set_title("", fontsize=14)

        for k, t in enumerate(times):
            if not (start <= t <= end) or t.minute % step:
                continue
            img = dtec[:, :, k][ilat, ilon]
            skip = outside | ~np.isfinite(img)
            if hide_below is not None:
                skip |= img <= hide_below
            img = np.ma.masked_where(skip, img)
            im.set_data(img)
            ttl.set_text(f"dTEC  {t:%Y-%m-%d %H:%M} UT   "
                         f"(centre: geomagnetic pole {lat0:.1f}°N {abs(lon0):.1f}°"
                         f"{'W' if lon0 < 0 else 'E'})")
            clock.set_text(f"{t:%H:%M} UT")
            frame_no += 1
            fig.savefig(frame_dir / f"f{frame_no:05d}.png", dpi=dpi)
            print(f"  frame {frame_no:3d}  {t:%H:%M} UT")

    if frame_no == 0:
        sys.exit("No frames fell inside the requested interval.")

    # 4. movie ------------------------------------------------------------------
    if shutil.which("ffmpeg") is None:
        sys.exit(f"{frame_no} frames written to {frame_dir}, but ffmpeg was not "
                 "found (sudo apt install ffmpeg)")
    out = out_dir / f"dTEC_polar_{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
         "-i", str(frame_dir / "f%05d.png"),
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)],
        check=True)
    print(f"Movie written: {out}  ({frame_no} frames)")


if __name__ == "__main__":
    main()
