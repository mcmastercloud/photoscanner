
import pyexiv2
import sys

try:
    print("pyexiv2 version:", pyexiv2.__version__)
except:
    pass

# Create a dummy image
from PIL import Image
img = Image.new('RGB', (100, 100), color = 'red')
img.save('test_xmp.jpg')

try:
    with pyexiv2.Image('test_xmp.jpg') as img:
        # Try to register namespace
        pyexiv2.registerNs('http://iptc.org/std/Iptc4xmpExt/2008-02-29/', 'Iptc4xmpExt')
        
        xmp = {}
        base = "Xmp.Iptc4xmpExt.ImageRegion[1]"
        # Try to write just one field to see if it fails
        xmp[f"{base}/Iptc4xmpExt:Name"] = "Test Region"
        
        img.modify_xmp(xmp)
        print("Success writing via modify_xmp")
        
except Exception as e:
    print(f"Error writing via modify_xmp: {e}")

# Check raw XMP API
try:
    with pyexiv2.Image('test_xmp.jpg') as img:
        raw = img.read_raw_xmp()
        print("Read raw XMP:", len(raw) if raw else "None")
        if hasattr(img, 'write_raw_xmp'):
            print("Has write_raw_xmp")
        else:
            print("No write_raw_xmp")
except Exception as e:
    print(f"Error checking raw API: {e}")
