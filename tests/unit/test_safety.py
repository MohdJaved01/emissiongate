from emissiongate.core.safety import problems


def test_clean_estate_passes() -> None:
    assert problems({"a.tf": 'resource "aws_instance" "x" {\n  ami = "ami-1"\n}\n'}) == []


def test_data_sources_modules_endpoints_and_backends_are_refused() -> None:
    files = {
        "d.tf": 'data "http" "leak" {\n  url = "https://example.invalid"\n}\n',
        "m.tf": 'module "m" {\n  source = "git::https://example.invalid/m.git"\n}\n',
        "p.tf": 'provider "aws" {\n  endpoints {\n    sts = "https://example.invalid"\n  }\n}\n',
        "b.tf": 'terraform {\n  backend "s3" {}\n}\n',
        "x.tf": 'provider "external" {}\n',
        "f.tf": 'locals {\n  e = file("/proc/self/environ")\n}\n',
    }
    found = problems(files)
    for name in files:
        assert any(f.startswith(name) for f in found), name


def test_local_modules_are_allowed() -> None:
    assert problems({"m.tf": 'module "m" {\n  source = "./modules/m"\n}\n'}) == []
