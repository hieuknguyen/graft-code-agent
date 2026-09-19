import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graft.graph import CodebaseGraph
from graft.grafter import Grafter
from core.verifier import verify_code

def test_full_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir)
        py_file = tmp_p / "service.py"
        py_file.write_text('''import os

class DataService:
    def __init__(self):
        self.name = "default"

    def fetch_data(self):
        return ["item1", "item2"]

def helper():
    return 42
''', encoding="utf-8")

        # 1. Scan Graph
        graph = CodebaseGraph(tmpdir)
        graph.scan()
        assert "service.py" in graph.files
        summary = graph.get_compact_summary()
        assert "DataService" in summary
        assert "fetch_data" in summary
        print("[OK] CodebaseGraph scan & summary: PASSED")

        # 2. Surgical replace method inside class
        orig_code = py_file.read_text(encoding="utf-8")
        new_method = '''    def fetch_data(self):
        # Nâng cấp lấy thêm metadata
        return [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}]'''

        succ, modified_code, msg = Grafter.graft_replace_symbol(
            orig_code, "fetch_data", new_method, parent_class="DataService", file_path="service.py"
        )
        assert succ is True
        assert "metadata" in modified_code
        assert "def helper():" in modified_code
        print("[OK] Surgical method replacement: PASSED")

        # 3. Verify syntax
        valid, v_msg = verify_code("service.py", modified_code)
        assert valid is True
        print("[OK] Code syntax verification: PASSED")

if __name__ == "__main__":
    test_full_pipeline()
    print("\nALL PIPELINE TESTS PASSED!")
