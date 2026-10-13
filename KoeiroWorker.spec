# -*- mode: python ; coding: utf-8 -*-
# Frozen AI worker: dist/KoeiroWorker/KoeiroWorker(.exe) + _internal_worker/.
#
# Built with the *AI* environment's interpreter, not the GUI's, because torch is what
# has to be bundled:
#   Windows: vc_models\meanvc2\.venv\Scripts\python.exe -m PyInstaller KoeiroWorker.spec --noconfirm
#   Linux:   vc_models/meanvc2/.venv/bin/python -m PyInstaller KoeiroWorker.spec --noconfirm
#
# Two choices here are load-bearing and easy to break from the GUI spec:
#   console=True    the worker speaks a binary protocol over stdin/stdout; a windowed
#                   bootloader has no usable stdout. The GUI starts it with CREATE_NO_WINDOW.
#   upx=False       torch ships hundreds of DLLs; packing them is slow and breaks them.
import os
import sysconfig

SITE = sysconfig.get_paths()['purelib']
SOURCE_PACKAGES = ('x_transformers', 'einops', 'einx', 'ema_pytorch')

a = Analysis(
    ['worker.py'],
    pathex=[],
    binaries=[],
    datas=[
        # lavasr.py and friends read these next to their own __file__, which inside a
        # bundle is _internal_worker/src/vc. Ship them to that exact folder.
        ('src/vc/lavasr_runtime.json', 'src/vc'),
        ('src/vc/flashsr_runtime.json', 'src/vc'),
        ('src/vc/mossformer_runtime.json', 'src/vc'),
        ('src/vc/voicefixer_runtime.json', 'src/vc'),
        # TorchScript compiles these decorators at load time and reads the source with
        # inspect.getsource, which a PYZ archive cannot answer. The .py files sit in the
        # bundle next to the compiled modules (~3 MB) so the worker can build its model.
    ] + [(os.path.join(SITE, package, '*.py'), package) for package in SOURCE_PACKAGES],
    hiddenimports=[
        # Loaded by files the worker opens *by path* (the MeanVC2 repo tree and the
        # vendored vocos/LavaSR), so modulegraph never sees them. Derived from a real
        # worker run's -X importtime trace, minus what the app's own imports already
        # reach. encodec is deliberately absent: the AI pack ships a raising stub for it.
        'einops', 'einx', 'x_transformers', 'x_transformers.x_transformers',
        'matplotlib', 'matplotlib.pylab', 'huggingface_hub', 'yaml', 'safetensors',
        'soundfile', 'librosa', 'scipy.signal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KoeiroWorker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='_internal_worker',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='KoeiroWorker',
)
