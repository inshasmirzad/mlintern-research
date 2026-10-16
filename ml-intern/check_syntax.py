import ast
import os
import sys

def check_syntax(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        source = f.read()
                    ast.parse(source, filename=path)
                except SyntaxError as e:
                    print(f"SyntaxError in {path}: {e}")
                except Exception as e:
                    print(f"Error reading {path}: {e}")

check_syntax(r"C:\Users\insha\Downloads\ml-intern-main_pro\ml-intern-main\backend")
check_syntax(r"C:\Users\insha\Downloads\ml-intern-main_pro\ml-intern-main\agent")
