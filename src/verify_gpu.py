"""GPU verification for Group 1.

Checks: (1) NVIDIA driver + container-toolkit passthrough (nvidia-smi works
            inside the container) — this is the actual Gate 1 requirement.
        (2) CUDA runtime via PyTorch — DEFERRED to Group 2, torch is not a
            Group 1 dependency (~2.5GB for zero Group 1 benefit).
"""
import shutil
import subprocess
import sys


def main() -> int:
    print("=" * 60)
    print("GPU Verification - Group 1 Foundation")
    print("=" * 60)

    if shutil.which("nvidia-smi") is None:
        print("FAIL: nvidia-smi not found.")
        print("  On host: install the NVIDIA driver.")
        print("  In container: check the GPU 'deploy:' block in docker-compose.yml.")
        return 1

    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
    if result.returncode != 0:
        print("FAIL: nvidia-smi exited with an error:")
        print(result.stderr)
        return 1

    print("PASS: nvidia-smi reachable — driver + GPU passthrough work in this container.\n")
    for line in result.stdout.splitlines()[:12]:
        if line.strip():
            print(f"      {line.strip()}")

    try:
        import torch
    except ImportError:
        print("\nDEFERRED: PyTorch not installed (intentional for Group 1).")
        print("          CUDA-runtime check happens at Group 2 / vLLM bring-up.")
        return 0

    print(f"\nPASS: torch {torch.__version__}, CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"      GPUs visible to torch: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"      [{i}] {torch.cuda.get_device_name(i)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())