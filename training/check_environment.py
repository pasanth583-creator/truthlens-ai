import sys
import psutil
import torch
from pathlib import Path

def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def main():
    print("=" * 40)
    print("ENVIRONMENT CHECK")
    print("=" * 40)
    
    print(f"Python version: {sys.version.split()[0]}")
    print(f"PyTorch version: {torch.__version__}")
    
    cuda_available = torch.cuda.is_available()
    print(f"CUDA available: {cuda_available}")
    
    if cuda_available:
        print(f"GPU Count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
            print(f"Memory: {get_size(torch.cuda.get_device_properties(i).total_memory)}")
    else:
        print("GPU: None")

    print(f"CPU Physical cores: {psutil.cpu_count(logical=False)}")
    print(f"CPU Total cores: {psutil.cpu_count(logical=True)}")
    
    svmem = psutil.virtual_memory()
    print(f"Total RAM: {get_size(svmem.total)}")
    print(f"Available RAM: {get_size(svmem.available)}")

if __name__ == "__main__":
    main()
