import sys
import platform

print(f"Python: {sys.version}")
print(f"Platform: {platform.platform()}")

try:
    import torch
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"Device count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"Device {i}: {torch.cuda.get_device_name(i)}")
    else:
        print("CUDA is NOT available.")
        print("Possible reasons:")
        print("1. You installed the CPU-only version of PyTorch (common with default pip install).")
        print("2. You do not have an NVIDIA GPU.")
        print("3. NVIDIA drivers are missing or outdated.")
        print("\nTo fix this, you likely need to reinstall PyTorch with CUDA support.")
        print("Visit https://pytorch.org/get-started/locally/ for the correct command.")
        print("Example for CUDA 11.8: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
        print("Example for CUDA 12.1: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")

except ImportError:
    print("PyTorch is not installed.")
