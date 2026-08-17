#!/usr/bin/env python
import ast
import sys

try:
    with open(r'backend\api\views.py', 'r', encoding='utf-8') as f:
        code = f.read()
    ast.parse(code)
    print("SYNTAX OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR at line {e.lineno}: {e.msg}")
    print(f"Text: {e.text}")
    print(f"Offset: {e.offset}")
    sys.exit(1)
