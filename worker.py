"""Frozen AI worker entry. PyInstaller builds this into KoeiroWorker.exe.

The GUI launches that executable directly (no interpreter, no `-m src.vc.service`);
see src/runtime_paths.py WORKER_EXE and src/vc/client.py worker_python.
"""
from src.vc.service import main

if __name__ == '__main__':
    main()
