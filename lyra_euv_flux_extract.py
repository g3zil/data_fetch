from astropy.io import fits
import numpy as np

# Open the LYRA Level 2 FITS file
fname = './Lyra_EUV_10May2026.fits'  # adjust filename as downloaded
hdul = fits.open(fname)

# Show the overall structure — number of HDUs and their types
print("=== HDU List ===")
hdul.info()

# Primary header
print("\n=== Primary Header ===")
print(repr(hdul[0].header))

# First extension — usually the data table
print("\n=== Extension 1 Header ===")
print(repr(hdul[1].header))

# Column names in the data table
print("\n=== Column Names ===")
print(hdul[1].columns.names)

# Shape and cadence check
data = hdul[1].data
print(f"\n=== Data shape: {data.shape} ===")
print(f"Number of records: {len(data)}")

# Time column — check first few values and spacing
time = data['TIME']  # may be named differently — columns.names will tell you
print(f"\nFirst 5 time values: {time[:5]}")
print(f"Last 5 time values:  {time[-5:]}")
print(f"Time step (seconds): {np.median(np.diff(time)):.3f}")

hdul.close()
