"""Entry script for PyInstaller (it needs a file, not ``-m capri``)."""

import sys

from capri.app import main

sys.exit(main())
