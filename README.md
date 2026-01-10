# Photo Scanner

A Windows desktop application to scan photo libraries, detect duplicates using perceptual hashing, and manage photo metadata with local AI assistance.

## Features

- **Duplicate Management**:
  - **Scanning**: Multi-threaded scanning of large photo libraries.
  - **Detection**: Finds exact duplicates (SHA-256) and similar images (Perceptual Hash).
  - **Resolution**: Interface to review duplicate groups and select the best version based on resolution/sharpness.

- **Metadata Editor & Labeling**:
  - **Label Editor**: Visual editor for image tags and regions (Face/Object bounding boxes).
  - **XMP Support**: fully compatible with **MWG-RS** (Metadata Working Group) regions and standard XMP metadata.
    - Reads/Writes labels that work with **DigiKam**, **Lightroom**, and standard Windows file properties.
    - Handles both legacy IPTC and modern MWG schemas.

- **Local AI Analysis**:
  - **Object Detection**: Uses **YOLOv8** to suggest labels and bounding boxes (e.g., "person", "cat", "car").
  - **Face Detection**: Uses **MediaPipe** for face region extraction.
  - **Semantic Search**: Generates **CLIP embeddings** to allow searching your library by text description (e.g., "dog on beach").
  - **Zero-Data Privacy**: All AI models run 100% locally on your machine (CPU or NVIDIA GPU).

## Architecture

- **Database**: SQLite (`photoscanner.sqlite`) for caching hashes, metadata, and embeddings.
- **GUI**: Built with PySide6 (Qt) for high-performance rendering.
- **Backend**: Python 3.10+

## Installation

1. **Create Environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install Dependencies**:
   ```powershell
   pip install -U pip
   
   # Core & GUI
   pip install -r requirements.txt
   ```

3. **(Optional) GPU Support**:
   For faster AI processing on NVIDIA GPUs, install PyTorch with CUDA support:
   ```powershell
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
   pip install ultralytics # For YOLOv8
   ```

## Usage

Run the main application:

```powershell
python -m photoscanner
```

### Key Tools
*   **Scanner**: Main window for finding duplicates. Add folders and click "Scan".
*   **Label Editor**: Open an image folder to view/edit labels.
    *   **Suggest Labels**: Runs YOLOv8 to auto-detect objects.
    *   **Deduplication**: Automatically merges AI suggestions with existing manual labels to avoid clutter.
    *   **Notification**: Subtle alerts when no new unique labels are found.

## Project Structure

*   `photoscanner/`: Source code.
    *   `gui/`: PySide6 Window classes (`ScannerWindow`, `LabelImagesWindow`).
    *   `ai.py`: Wrappers for YOLO, MediaPipe, and SentenceTransformers.
    *   `db.py`: Database schema and ORM.
    *   `scanner.py`: File system walking and hashing logic.
*   `yolov8n.pt`: Tiny YOLO model for efficient local detection.

## License

MIT
