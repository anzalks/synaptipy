import ast
import os
import glob
from collections import defaultdict

def check_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = [arg.arg for arg in node.args.args if arg.arg not in ('self', 'cls')]
            args += [arg.arg for arg in node.args.kwonlyargs]
            
            docstring = ast.get_docstring(node)
            if docstring:
                for arg in args:
                    # basic check: is the arg mentioned in the docstring?
                    # A more rigorous check parses the Google/Numpy style.
                    # We will just look for `arg:` or `arg ` or `*arg*` etc.
                    # Actually, if we use a regex:
                    pass

