"""
一键测试：pytest 运行全部用例

用法：
    python tests/run_tests.py          # 所有测试
    python tests/run_tests.py -v       # 详细输出
    python tests/run_tests.py -k auth  # 只跑 auth 相关
    python tests/run_tests.py -s       # 显示 print 输出
"""
import sys
import pytest

if __name__ == "__main__":
    args = [
        "tests/",
        "-p", "no:warnings",
    ] + sys.argv[1:]
    sys.exit(pytest.main(args))
