import pyexiv2
import sys

path = "photoscanner/gui/IMG.jpg"

print(f"Reading XMP from {path}...")

try:
    with pyexiv2.Image(path) as img:
        raw = img.read_raw_xmp()
        print("--- RAW XMP START ---")
        print(raw)
        print("--- RAW XMP END ---")
        
        # Also print parsed keys to see how pyexiv2 sees it
        print("\n--- Parsed Structure ---")
        data = img.read_xmp()
        for k in sorted(data.keys()):
             # Only show region related stuff to keep it brief
             if "mwg-rs" in k:
                 print(f"{k}: {data[k]}")

except Exception as e:
    print(f"Error: {e}")
