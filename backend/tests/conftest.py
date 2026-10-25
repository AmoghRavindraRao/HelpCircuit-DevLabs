import os
import sys
import tempfile
from pathlib import Path

# Ensure the backend package root is importable when running pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Point persistence at a throwaway database so tests never touch the real one.
# Must be set before `store`/`db` are first imported.
os.environ["HELPCIRCUIT_DB"] = str(Path(tempfile.gettempdir()) / "helpcircuit_test.db")
