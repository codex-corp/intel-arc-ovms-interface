import os
import sys
import unittest
from pathlib import Path

# Ensure repository root is at the head of sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["PYTHONPATH"] = str(ROOT_DIR) + os.pathsep + os.environ.get("PYTHONPATH", "")

def main():
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(ROOT_DIR / "tests"),
        pattern="test_*.py",
        top_level_dir=str(ROOT_DIR),
    )
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    if not result.wasSuccessful():
        print("\nFAILED TESTS DETAIL:")
        for test, err in result.failures + result.errors:
            print(f"\n=== {test} ===")
            print(err)
        sys.exit(1)
    print("\nALL TESTS PASSED SUCCESSFULLY.")
    sys.exit(0)

if __name__ == "__main__":
    main()
