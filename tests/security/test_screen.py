"""E1 screen (interim, before the parser-based allowlist): every file OpenTofu loads is screened."""

from __future__ import annotations

import pytest

from emissiongate.core.safety import loaded_by_tofu, problems

OK = 'resource "aws_instance" "x" {\n  ami = "ami-1"\n}\n'


@pytest.mark.parametrize("name", ["leak.tf.json", "leak.tofu", "leak.tofu.json"])
def test_formats_the_screen_cannot_read_are_refused(name: str) -> None:
    found = problems({"main.tf": OK, name: '{"data": {"http": {"x": {"url": "https://x"}}}}'})
    assert any(f.startswith(name) for f in found)


def test_local_module_contents_are_screened() -> None:
    files = {
        "main.tf": 'module "m" {\n  source = "./modules/m"\n}\n',
        "modules/m/main.tf": 'data "http" "leak" {\n  url = "https://example.invalid"\n}\n',
    }
    assert any(f.startswith("modules/m/main.tf") for f in problems(files))


@pytest.mark.parametrize("src", ["../outside", "./modules/../../outside", "../../../etc"])
def test_module_sources_cannot_leave_the_configuration(src: str) -> None:
    found = problems({"main.tf": f'module "m" {{\n  source = "{src}"\n}}\n'})
    assert found, src


@pytest.mark.parametrize(
    "expr",
    [
        'file("../../secrets")',
        'file("~/.aws/credentials")',
        'filebase64("/etc/passwd")',
        'templatefile("${path.module}/../../x.tpl", {})',
        'fileexists("C:/Users/x")',
        'file(pathexpand("~/.ssh/id_rsa"))',
        'filesha256(abspath("x"))',
        # paths that are not a literal: a variable can default to /proc/<ppid>/environ, or be set
        # in an auto-loaded *.tfvars the screen never reads (invariant-review finding, 25 Oct)
        "file(var.p)",
        "file(local.p)",
        'file("${var.p}")',
        'file(format("%s/environ", var.root))',
        'fileset(var.root, "*/environ")',
        'templatefile(join("/", ["", "proc", "self", "environ"]), {})',
        'file("${path.root}/x")',
    ],
)
def test_file_functions_cannot_read_outside_the_configuration(expr: str) -> None:
    assert problems({"main.tf": f"locals {{\n  x = {expr}\n}}\n"}), expr


@pytest.mark.parametrize(
    "expr",
    [
        'templatefile("${path.module}/user_data.tpl", { name = var.n })',
        'file("scripts/boot.sh")',
        'fileset(path.module, "*.json")',
        'filebase64("${path.module}/files/cert.pem")',
    ],
)
def test_literal_relative_reads_inside_the_configuration_are_allowed(expr: str) -> None:
    assert problems({"main.tf": f"locals {{\n  x = {expr}\n}}\n"}) == [], expr


def test_which_files_tofu_loads() -> None:
    assert loaded_by_tofu("a.tf") and loaded_by_tofu("m/a.tofu.json")
    assert not loaded_by_tofu("README.md") and not loaded_by_tofu("prod.tfvars")
