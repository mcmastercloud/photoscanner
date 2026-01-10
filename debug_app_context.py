from photoscanner.utils import get_torch_devices
import torch
import sys

print(f"Executable: {sys.executable}")
print(f"Path: {sys.path}")
print(f"Torch: {torch.__file__}")
print(f"CUDA Available: {torch.cuda.is_available()}")
devices = get_torch_devices()
print(f"Devices: {devices}")
