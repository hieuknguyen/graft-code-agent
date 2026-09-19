import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graft.parser import parse_python_ast
from graft.grafter import Grafter
from graft.diff_utils import generate_unified_diff

SAMPLE_CODE = '''def add(a, b):
    # Hàm cộng 2 số
    return a + b

def subtract(a, b):
    # Hàm trừ 2 số
    return a - b
'''

def test_ast_parser():
    fast = parse_python_ast(SAMPLE_CODE, "sample.py")
    assert len(fast.symbols) == 2
    assert fast.symbols[0].name == "add"
    assert fast.symbols[1].name == "subtract"
    print("[OK] test_ast_parser: PASSED")

def test_surgical_replace():
    new_add = '''def add(a, b):
    # Hàm cộng 2 số nâng cao có kiểm tra kiểu
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("a và b phải là số")
    return a + b'''

    succ, result, msg = Grafter.graft_replace_symbol(SAMPLE_CODE, "add", new_add)
    assert succ is True
    assert "TypeError" in result
    assert "def subtract(a, b):" in result  # Hàm subtract không hề bị ảnh hưởng!
    print("[OK] test_surgical_replace: PASSED")

def test_insert_symbol():
    new_func = '''def multiply(a, b):
    return a * b'''
    succ, result, msg = Grafter.graft_insert_symbol(SAMPLE_CODE, new_func)
    assert succ is True
    assert "multiply" in result
    print("[OK] test_insert_symbol: PASSED")

if __name__ == "__main__":
    test_ast_parser()
    test_surgical_replace()
    test_insert_symbol()
    print("\nALL GRAFT UNIT TESTS PASSED SUCCESSFULLY!")
