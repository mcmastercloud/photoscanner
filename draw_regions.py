import lxml.etree as ET
from PIL import Image, ImageDraw

# Define the namespaces provided
NS = {
    'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    'mwg-rs': "http://www.metadataworkinggroup.com/schemas/regions/",
    'stArea': "http://ns.adobe.com/xmp/sType/Area#",
}

def draw_regions(image_path, xml_data):
    # Load image to get dimensions
    img = Image.open(image_path)
    w, h = img.size
    draw = ImageDraw.Draw(img)

    root = ET.fromstring(xml_data)
    
    # Find all region descriptions
    regions = root.xpath('//mwg-rs:RegionList/rdf:Bag/rdf:li/rdf:Description/mwg-rs:Area', namespaces=NS)

    for area in regions:
        # XMP coordinates are often normalized (0.0 to 1.0)
        # centered at the point (x, y)
        x = float(area.get(f'{{{NS["stArea"]}}}x'))
        y = float(area.get(f'{{{NS["stArea"]}}}y'))
        rw = float(area.get(f'{{{NS["stArea"]}}}w'))
        rh = float(area.get(f'{{{NS["stArea"]}}}h'))

        # Convert normalized center-based coordinates to pixel corners
        left = (x - rw/2) * w
        top = (y - rh/2) * h
        right = (x + rw/2) * w
        bottom = (y + rh/2) * h

        # Draw the rectangle
        draw.rectangle([left, top, right, bottom], outline="red", width=3)
        print(f"Region found at: {left}, {top}, {right}, {bottom}")

    img.show()

# Example XML snippet
xml_input = """<rdf:RDF xmlns:rdf="...">...</rdf:RDF>""" 
# draw_regions('your_image.jpg', xml_input)