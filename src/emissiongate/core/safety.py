"""Static safety screen for HCL from a pull request before it is planned (GATE §6, THREAT_MODEL B1).

Untrusted HCL is planned only if it cannot reach the network or read secrets at plan time: no data
sources, no non-local modules, no custom provider endpoints, no remote backends, AWS provider only,
no file reads outside the configuration. Anything else makes the PR "not evaluated" (a neutral
check), never a plan.

Interim screen (E1): regex-based, so it refuses every format it cannot read (`*.tf.json`, `*.tofu`,
`*.tofu.json`) and screens files in every directory, which covers local modules. A parser-based
allowlist replaces it later in E1.
"""

from __future__ import annotations

import posixpath
import re

SCREENED = (".tf",)
UNSCREENABLE = (".tf.json", ".tofu", ".tofu.json")

DATA = re.compile(r'^\s*data\s+"', re.M)
MODULE = re.compile(r'^\s*module\s+"[^"]+"\s*\{(?P<body>.*?)^\}', re.M | re.S)
SOURCE = re.compile(r'^\s*source\s*=\s*"(?P<src>[^"]+)"', re.M)
ENDPOINTS = re.compile(r"^\s*endpoints\s*\{", re.M)
BACKEND = re.compile(r'^\s*(?:backend\s+"|cloud\s*\{)', re.M)
PROVIDER = re.compile(r'^\s*provider\s+"(?P<name>[^"]+)"', re.M)
FILE_CALL = re.compile(
    r"\b(?:file|fileexists|fileset|filebase64|filebase64sha256|filebase64sha512|filemd5|"
    r"filesha1|filesha256|filesha512|templatefile)\s*\(\s*",
    re.M,
)
# The path argument must be visible to the screen: a plain relative literal, optionally prefixed
# with `${path.module}/`, or bare `path.module` (fileset). Variables, locals, other interpolation
# and function results are refused, since their value can come from a default or an auto-loaded
# *.tfvars file the screen does not read.
LITERAL_PATH = re.compile(
    r'(?:"(?:\$\{path\.module\}/)?(?![^"]*\.\.)[A-Za-z0-9_][A-Za-z0-9_./-]*"|path\.module)\s*[,)]'
)
PATH_FUNCS = re.compile(r"\b(?:pathexpand|abspath)\s*\(")


def loaded_by_tofu(name: str) -> bool:
    """Files OpenTofu reads as configuration (variable files hold values only)."""
    return name.endswith(SCREENED + UNSCREENABLE)


def _escapes(file_name: str, source: str) -> bool:
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(file_name), source))
    return joined == ".." or joined.startswith("../") or posixpath.isabs(joined)


def problems(files: dict[str, str]) -> list[str]:
    """Problems found in `files` ({posix path relative to the root: text}); [] means plannable."""
    out: list[str] = []
    for name, text in sorted(files.items()):
        if name.endswith(UNSCREENABLE):
            out.append(f"{name}: format not screened yet (only .tf is planned)")
            continue
        if not name.endswith(SCREENED):
            continue
        if DATA.search(text):
            out.append(f"{name}: data sources are not planned (they can call out at plan time)")
        for m in MODULE.finditer(text):
            src = SOURCE.search(m.group("body"))
            if not src or not src.group("src").startswith(("./", "../")):
                out.append(f"{name}: non-local module source")
            elif _escapes(name, src.group("src")):
                out.append(f"{name}: module source outside the configuration")
        if ENDPOINTS.search(text):
            out.append(f"{name}: custom provider endpoints")
        if BACKEND.search(text):
            out.append(f"{name}: remote backend or cloud block")
        for m in PROVIDER.finditer(text):
            if m.group("name") != "aws":
                out.append(f"{name}: provider {m.group('name')!r} is not in the vetted mirror")
        if PATH_FUNCS.search(text) or any(
            not LITERAL_PATH.match(text, m.end()) for m in FILE_CALL.finditer(text)
        ):
            out.append(f"{name}: reads a file outside the configuration at plan time")
    return out
