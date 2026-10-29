"""Run pytest without masking failures; log its return before native teardown."""
import sys
import pytest


def main():
    result=int(pytest.main(sys.argv[1:]))
    print(f'\nPytest returned exit code {result}; Python/native shutdown follows.',flush=True)
    return result


if __name__=='__main__':
    raise SystemExit(main())
