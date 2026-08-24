import json, tempfile, unittest
from pathlib import Path
from tools.model_manager.model_registry import load_registry

class RegistryTests(unittest.TestCase):
    def test_legacy_registry_is_supported(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "registry.json"; p.write_text(json.dumps({"models":{"a":"C:/models/a"}}), encoding="utf-8")
            self.assertEqual(load_registry(p)["a"].path, "C:/models/a")

if __name__ == "__main__": unittest.main()
