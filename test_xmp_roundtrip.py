import pyexiv2
from xml.etree import ElementTree as ET
import os
from pathlib import Path

# Create a dummy image
TEST_IMG = "test_xmp_write.jpg"
if not os.path.exists(TEST_IMG):
    from PIL import Image
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save(TEST_IMG)

print(f"Testing on {TEST_IMG}")

# Define Labels Data (simulating app state)
objects = [
    {
        "label": "Test Person",
        "bbox": {"xmin": 0.1, "ymin": 0.1, "width": 0.5, "height": 0.5}
    },
    {
        "label": "Test Dog", 
        "bbox": None
    }
]

def write_xmp_test(path, objects):
    # Namespaces
    NS_MAP = {
        'x': "adobe:ns:meta/",
        'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        'dc': "http://purl.org/dc/elements/1.1/",
        'mwg-rs': "http://www.metadataworkinggroup.com/schemas/regions/",
        'stArea': "http://ns.adobe.com/xmp/sType/Area#",
        'stDim': "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
        'stReg': "http://ns.adobe.com/xmp/sType/Region#"
    }

    # Register for ET
    for prefix, uri in NS_MAP.items():
        ET.register_namespace(prefix, uri)
    
    # Register for pyexiv2
    try:
        for prefix, uri in NS_MAP.items():
            pyexiv2.registerNs(uri, prefix)
    except Exception as e:
        print(f"Warning registering NS: {e}")

    labels = sorted(list(set(o["label"] for o in objects)))
    region_objects = [o for o in objects if o.get("bbox")]

    with pyexiv2.Image(str(path)) as img:
        img_w, img_h = 100, 100 # Mocked for test
        
        raw_xmp = img.read_raw_xmp()
        print(f"Original XMP Length: {len(raw_xmp) if raw_xmp else 0}")
        
        root = None
        if raw_xmp:
            # Strip xpacket wrapper
            start = raw_xmp.find('<x:xmpmeta')
            end = raw_xmp.rfind('</x:xmpmeta>')
            if start != -1 and end != -1:
                raw_xml_body = raw_xmp[start:end+12]
                try:
                    root = ET.fromstring(raw_xml_body)
                except ET.ParseError:
                    pass
        
        if root is None:
            root = ET.Element(f"{{{NS_MAP['x']}}}xmpmeta")
            root.set(f"{{{NS_MAP['x']}}}xmptk", "XMP Core 5.6.0")

        # Ensure RDF
        rdf = root.find('rdf:RDF', NS_MAP)
        if rdf is None:
            # Try finding without prefix if namespace map failed to match
            for child in root:
                if child.tag.endswith("RDF"):
                    rdf = child
                    break
        
        if rdf is None:
            rdf = ET.SubElement(root, f"{{{NS_MAP['rdf']}}}RDF")

        # Find Description
        desc = None
        for d in rdf.findall('rdf:Description', NS_MAP):
            if d.get(f"{{{NS_MAP['rdf']}}}about") == "":
                desc = d
                break
        
        if desc is None:
            if len(rdf) > 0:
                    desc = rdf[0]
            else:
                desc = ET.SubElement(rdf, f"{{{NS_MAP['rdf']}}}Description")
                desc.set(f"{{{NS_MAP['rdf']}}}about", "")

        # 1. dc:subject (Keywords)
        subject = desc.find('dc:subject', NS_MAP)
        if subject is not None:
            desc.remove(subject)
        
        if labels:
            subject = ET.SubElement(desc, f"{{{NS_MAP['dc']}}}subject")
            bag = ET.SubElement(subject, f"{{{NS_MAP['rdf']}}}Bag")
            for label in labels:
                li = ET.SubElement(bag, f"{{{NS_MAP['rdf']}}}li")
                li.text = label

        # 2. mwg-rs:Regions
        # Clean old
        mwg_regions = desc.find('mwg-rs:Regions', NS_MAP)
        if mwg_regions is not None:
            desc.remove(mwg_regions)

        if region_objects:
            regions = ET.SubElement(desc, f"{{{NS_MAP['mwg-rs']}}}Regions")
            regions.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
            
            # AppliedToDimensions
            dims = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}AppliedToDimensions")
            dims.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
            
            w_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}w")
            w_el.text = str(img_w)
            h_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}h")
            h_el.text = str(img_h)
            unit_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}unit")
            unit_el.text = "pixel"

            # RegionList
            rlist = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}RegionList")
            bag = ET.SubElement(rlist, f"{{{NS_MAP['rdf']}}}Bag")
            
            for obj in region_objects:
                li = ET.SubElement(bag, f"{{{NS_MAP['rdf']}}}li")
                # Structure: rdf:Description with attributes
                struct = ET.SubElement(li, f"{{{NS_MAP['rdf']}}}Description")
                struct.set(f"{{{NS_MAP['stReg']}}}Name", obj["label"])
                struct.set(f"{{{NS_MAP['stReg']}}}Type", "Face")
                
                bbox = obj["bbox"]
                area = ET.SubElement(struct, f"{{{NS_MAP['stReg']}}}Area")
                # Area properties as attributes
                area.set(f"{{{NS_MAP['stArea']}}}x", "0.350000")
                area.set(f"{{{NS_MAP['stArea']}}}y", "0.350000")
                area.set(f"{{{NS_MAP['stArea']}}}w", "0.500000")
                area.set(f"{{{NS_MAP['stArea']}}}h", "0.500000")
                area.set(f"{{{NS_MAP['stArea']}}}unit", "normalized")

        new_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
        
        print("\n--- Generated XML ---")
        print(new_xml)
        print("---------------------\n")
        
        try:
            img.modify_raw_xmp(new_xml)
            print("SUCCESS: modify_raw_xmp completed")
        except Exception as e:
            print(f"FAILURE: {e}")
            raise

if __name__ == "__main__":
    try:
        write_xmp_test(TEST_IMG, objects)
        
        # Verify Read
        print("\n--- Verifying Read ---")
        with pyexiv2.Image(TEST_IMG) as img:
            print(img.read_xmp())
            
    except Exception as e:
        print(f"\nCRITICAL FAIL: {e}")
