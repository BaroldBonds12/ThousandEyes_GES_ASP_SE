"""
Launcher — single entry point for both installer and main app.

First run:  shows the installation wizard
Subsequent runs: shows the main application directly

PyInstaller bundles THIS file as the executable entry point.
Pass  --install  to force the wizard, --app to force the main app.
"""

from __future__ import annotations

import sys
from pathlib import Path

SETUP_FLAG = Path.home() / ".te_qa_installed"


def _setup_done() -> bool:
    return SETUP_FLAG.exists()


def main() -> None:
    args = sys.argv[1:]

    if "--install" in args or not _setup_done():
        from installer import run_installer
        run_installer()
        # After installer finishes, launch the app automatically
        if _setup_done():
            from main import App
            App().mainloop()
    else:
        from main import App
        App().mainloop()


if __name__ == "__main__":
    main()
