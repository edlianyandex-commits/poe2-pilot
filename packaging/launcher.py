"""PyInstaller entry point for PoE2Pilot.exe."""
import sys

from pilot.app import main

if __name__ == "__main__":
    sys.exit(main())
