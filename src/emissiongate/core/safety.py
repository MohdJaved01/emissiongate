"""Static safety screen for HCL from a pull request before it is planned (GATE §6).

Untrusted HCL is planned only if it cannot reach the network or read secrets at plan time: no data
sources, no non-local modules, no custom provider endpoints, no remote backends, AWS provider only.
Anything else makes the PR "not evaluated" (a neutral check), never a plan.
"""

from __future__ import annotations

import re

DATA = re.compile(r'^\s*data\s+"', re.M)
MODULE = re.compile(r'^\s*module\s+"[^"]+"\s*\{(?P<body>.*?)^\}', re.M | re.S)
SOURCE = re.compile(r'^\s*source\s*=\s*"(?P<src>[^"]+)"', re.M)
ENDPOINTS = re.compile(r"^\s*endpoints\s*\{", re.M)
BACKEND = re.compile(r'^\s*(?:backend\s+"|cloud\s*\{)', re.M)
PROVIDER = re.compile(r'^\s*provider\s+"(?P<name>[^"]+)"', re.M)
EXTERNAL_FUNCS = re.compile(r"\b(?:file|fileset|templatefile|filebase64)\s*\(\s*\"?/", re.M)


def problems(files: dict[str, str]) -> list[str]:
    out: list[str] = []
    for name, text in sorted(files.items()):
        if DATA.search(text):
            out.append(f"{name}: data sources are not planned (they can call out at plan time)")
        for m in MODULE.finditer(text):
            src = SOURCE.search(m.group("body"))
            if not src or not src.group("src").startswith(("./", "../")):
                out.append(f"{name}: non-local module source")
        if ENDPOINTS.search(text):
            out.append(f"{name}: custom provider endpoints")
        if BACKEND.search(text):
            out.append(f"{name}: remote backend or cloud block")
        for m in PROVIDER.finditer(text):
            if m.group("name") != "aws":
                out.append(f"{name}: provider {m.group('name')!r} is not in the vetted mirror")
        if EXTERNAL_FUNCS.search(text):
            out.append(f"{name}: reads an absolute path at plan time")
    return out
