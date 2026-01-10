from PIL import Image
from pathlib import Path
import os

def create_test_data():
    root = Path(r"d:\SynologyDrive\Development\Home\Photo Scanner\test_images")
    root.mkdir(exist_ok=True)
    
    # Create a simple image
    img = Image.new('RGB', (100, 100), color = 'red')
    
    # Save it as two different files
    img.save(root / "image1.jpg")
    img.save(root / "image2.jpg")
    
    print(f"Created test images in {root.absolute()}")

if __name__ == "__main__":
    create_test_data()