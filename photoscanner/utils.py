from __future__ import annotations

from typing import List, Dict, Optional
from pathlib import Path

def get_torch_devices() -> List[str]:
    """Return a list of available torch devices (e.g. ['cpu', 'cuda'])."""
    devices = ["cpu"]
    try:
        import torch
        if torch.cuda.is_available():
            devices.append("cuda")
            # If multiple GPUs, could list them, but 'cuda' usually defaults to cuda:0 which is fine.
            for i in range(torch.cuda.device_count()):
                devices.append(f"cuda:{i}")
    except ImportError:
        pass
    return devices


def get_image_metadata(path: str) -> Dict[str, str]:
    """Extract display-friendly metadata (Device, Date, GPS)."""
    meta = {}
    try:
        import pyexiv2
        with pyexiv2.Image(str(path)) as img:
            exif = img.read_exif()
            
            # Device
            make = exif.get('Exif.Image.Make', '').strip()
            model = exif.get('Exif.Image.Model', '').strip()
            if model:
                meta['Device'] = model if make in model else f"{make} {model}"
            elif make:
                meta['Device'] = make
                
            # Date
            date = exif.get('Exif.Photo.DateTimeOriginal') or exif.get('Exif.Image.DateTime')
            if date:
                meta['Date'] = str(date)
                
            # GPS (very rough check, parsing rationals properly is complex)
            # pyexiv2 usually returns string "deg/1 min/1 sec/1" or similar
            lat_ref = exif.get('Exif.GPSInfo.GPSLatitudeRef')
            lat = exif.get('Exif.GPSInfo.GPSLatitude')
            lon_ref = exif.get('Exif.GPSInfo.GPSLongitudeRef')
            lon = exif.get('Exif.GPSInfo.GPSLongitude')
            
            if lat and lon:
                meta['GPS'] = "Yes" # Just indicating presence is often enough for "Device info" request context
                # If we want detailed coordinates, it takes more code to parse D/M/S
            else:
                meta['GPS'] = "<MISSING>"

            if 'Device' not in meta:
               meta['Device'] = "<MISSING>"
            if 'Date' not in meta:
               meta['Date'] = "<MISSING>"
                
    except Exception:
        # If read failed completely
        meta['Device'] = "<MISSING>"
        meta['Date'] = "<MISSING>"
        meta['GPS'] = "<MISSING>"
        pass
        
    return meta


def merge_image_metadata(source_paths: List[str], target_path: str) -> None:
    """Copy metadata fields from source images to target if target is missing them."""
    try:
        import pyexiv2
        
        # Read target first
        with pyexiv2.Image(str(target_path)) as target_img:
            target_exif = target_img.read_exif()
            target_iptc = target_img.read_iptc()
            target_xmp = target_img.read_xmp()
            
            new_exif = {}
            new_iptc = {}
            new_xmp = {}
            
            modified = False
            
            for src_path in source_paths:
                try:
                    with pyexiv2.Image(str(src_path)) as src_img:
                        src_exif = src_img.read_exif()
                        src_iptc = src_img.read_iptc()
                        src_xmp = src_img.read_xmp()
                        
                        # Merge Exif
                        for k, v in src_exif.items():
                            if k not in target_exif and k not in new_exif:
                                new_exif[k] = v
                                modified = True
                                
                        # Merge IPTC
                        for k, v in src_iptc.items():
                            if k not in target_iptc and k not in new_iptc:
                                new_iptc[k] = v
                                modified = True

                        # Merge XMP
                        for k, v in src_xmp.items():
                            if k not in target_xmp and k not in new_xmp:
                                new_xmp[k] = v
                                modified = True
                except Exception:
                    continue
            
            if modified:
                target_img.modify_exif(new_exif)
                target_img.modify_iptc(new_iptc)
                target_img.modify_xmp(new_xmp)
                
    except Exception as e:
        print(f"Failed to merge metadata: {e}")

