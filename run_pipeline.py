#!/usr/bin/env python3
"""
Wrapper: roda pipeline_complete.py a partir da raiz do projeto
"""

import subprocess
import sys

result = subprocess.run(
    [sys.executable, "api/pipeline_complete.py"] + sys.argv[1:],
    cwd="."
)

sys.exit(result.returncode)
