import pyexiv2
import xml.etree.ElementTree as ET
import os

# Create a clean jpg
from PIL import Image
img_path = "test_fresh.jpg"
img = Image.new('RGB', (100, 100), color = 'red')
img.save(img_path)

# Verify no XMP
with pyexiv2.Image(img_path) as i:
    print("Initial XMP:", i.read_raw_xmp())

NS_MAP = {
    'x': "adobe:ns:meta/",
    'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    'dc': "http://purl.org/dc/elements/1.1/",
    'mwg-rs': "http://www.metadataworkinggroup.com/schemas/regions/",
    'stArea': "http://ns.adobe.com/xmp/sType/Area#",
    'stDim': "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
    'stReg': "http://ns.adobe.com/xmp/sType/Region#"
}

print("Registering namespaces...")
for prefix, uri in NS_MAP.items():
    ET.register_namespace(prefix, uri)
    try:
        pyexiv2.registerNs(uri, prefix)
    except Exception as e:
        print("Register NS error:", e)

# Construct Fresh XMP
root = ET.Element(f"{{{NS_MAP['x']}}}xmpmeta")
root.set(f"{{{NS_MAP['x']}}}xmptk", "XMP Core 5.6.0")

rdf = ET.SubElement(root, f"{{{NS_MAP['rdf']}}}RDF")
desc = ET.SubElement(rdf, f"{{{NS_MAP['rdf']}}}Description")
desc.set(f"{{{NS_MAP['rdf']}}}about", "")

# Add regions stuff
regions = ET.SubElement(desc, f"{{{NS_MAP['mwg-rs']}}}Regions")
regions.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
dims = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}AppliedToDimensions")
dims.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
w = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}w")
w.text = "100"
h = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}h")
h.text = "100"
u = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}unit")
u.text = "pixel"

# Valid Structure from previous fix
rlist = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}RegionList")
bag = ET.SubElement(rlist, f"{{{NS_MAP['rdf']}}}Bag")

li = ET.SubElement(bag, f"{{{NS_MAP['rdf']}}}li")
struct = ET.SubElement(li, f"{{{NS_MAP['rdf']}}}Description")
name = ET.SubElement(struct, f"{{{NS_MAP['stReg']}}}Name")
name.text = "Fresh Test"
type_el = ET.SubElement(struct, f"{{{NS_MAP['stReg']}}}Type")
type_el.text = "Face"
area = ET.SubElement(struct, f"{{{NS_MAP['stReg']}}}Area")
area.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
x = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}x")
x.text = "0.5"
y = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}y")
y.text = "0.5"
w = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}w")
w.text = "0.1"
h = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}h")
h.text = "0.1"
unit = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}unit")
unit.text = "normalized"

new_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
print("Generated XML:\n", new_xml)

print("Attempting Write...")
try:
    with pyexiv2.Image(img_path) as i:
        i.modify_raw_xmp(new_xml)
    print("SUCCESS: Write 1")
except Exception as e:
    print("FAILURE: Write 1 -", e)

print("Reading back...")
with pyexiv2.Image(img_path) as i:
    print("Data:", i.read_xmp())
