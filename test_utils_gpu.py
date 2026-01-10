from photoscanner.utils import get_torch_devices
import torch

print(f"Torch file: {torch.__file__}")
print(f"Torch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"Detected devices: {get_torch_devices()}")
