"""PyInstaller entry point; multiprocessing-safe for future parsing workers."""

from multiprocessing import freeze_support

from researchgraph.__main__ import main

if __name__ == "__main__":
    freeze_support()
    main()
