import time
from PIL import Image
import random

def laplacian_sharpness_slow(img: Image.Image) -> float:
    gray = img.convert("L")
    px = gray.load()
    w, h = gray.size
    values = []
    # Only do a small center crop to not wait forever during test
    # But usually it runs on the whole image!
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            c = px[x, y]
            lap = -4 * c + px[x - 1, y] + px[x + 1, y] + px[x, y - 1] + px[x, y + 1]
            values.append(float(lap))
    return sum(values)/len(values) if values else 0

# Create dummy image 1000x1000
img = Image.new('RGB', (1000, 1000), color='red')
print("Starting slow sharpness check on 1000x1000 image...")
start = time.time()
laplacian_sharpness_slow(img)
print(f"Time taken: {time.time() - start:.4f} seconds")
