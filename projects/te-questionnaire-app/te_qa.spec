# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — ThousandEyes Questionnaire Automator
# Builds a self-contained macOS .app (or Windows .exe folder).
#
# Usage:
#   pyinstaller te_qa.spec --clean --noconfirm

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── Collect assets that live inside installed packages ──────────────────────
# customtkinter ships JSON theme files and font assets that must travel
# with the bundle or the UI will crash at runtime.
datas = []
datas += collect_data_files('customtkinter')
# Bundle the Vizzy mascot logo and any other local assets
datas += [('assets', 'assets')]
# Bundle the vertical industry knowledge base JSON files
datas += [('data/vertical_knowledge', 'data/vertical_knowledge')]

# ── Hidden imports PyInstaller can't trace automatically ────────────────────
hidden = []
hidden += collect_submodules('customtkinter')
hidden += [
    # tkinter
    'tkinter', 'tkinter.filedialog', 'tkinter.messagebox',
    '_tkinter',
    # file parsing
    'openpyxl', 'openpyxl.styles', 'openpyxl.styles.fills',
    'openpyxl.styles.fonts', 'openpyxl.styles.alignment',
    'pandas', 'pandas.io.formats.style',
    'docx', 'docx.shared', 'docx.enum.text',
    'docx.oxml', 'docx.oxml.ns',
    'pdfplumber', 'pdfminer', 'pdfminer.high_level',
    # web / search
    'bs4', 'lxml', 'lxml.etree', 'lxml._elementpath',
    'requests', 'urllib3', 'charset_normalizer',
    'ddgs', 'ddgs.ddgs',
    *collect_submodules('ddgs.engines'),
    'primp',
    # app source
    'src', 'src.file_parser', 'src.question_extractor',
    'src.te_search', 'src.llm_engine',
    'src.file_writer', 'src.processor', 'src.vizzy',
    'src.qa_reference', 'src.cache', 'src.feedback',
    'src.vertical_loader', 'src.vertical_detector',
    'src.setup_wizard',
    'openpyxl.styles.borders',
    # PIL / imaging
    'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFilter', 'PIL.ImageTk',
]

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['openai', 'torch', 'tensorflow', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TE_Questionnaire_Automator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # leave UPX off — faster build, avoids AV false positives
    console=False,      # no terminal window
    disable_windowed_traceback=False,
    target_arch=None,   # native arch (arm64 on M-series, x86_64 on Intel)
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='TE_Questionnaire_Automator',
)

# ── macOS: wrap into a double-clickable .app bundle ─────────────────────────
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='TE Questionnaire Automator.app',
        bundle_identifier='com.thousandeyes.qa-automator',
        info_plist={
            'CFBundleDisplayName':      'TE Questionnaire Automator',
            'CFBundleVersion':          '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable':  True,
            'LSMinimumSystemVersion':   '12.0',
            # Allow network access for fetching TE docs
            'NSAppTransportSecurity': {
                'NSAllowsArbitraryLoads': True,
            },
        },
    )
