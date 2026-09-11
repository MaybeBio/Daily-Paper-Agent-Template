import os
import sys

# Tests import the monitor modules directly (`import agent`, `import monitor`,
# `import build_site`, `import fulltext`); they live in scripts/, so expose that
# directory on sys.path during test collection.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
