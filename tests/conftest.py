"""Paths, and the one thing the suite must not do: assume it is in the repo.

BRIDGES's verification battery, the `suite` leg: *does the suite pass from a
directory that is
not the repository?* So nothing here uses a relative path or `os.getcwd()`.
Every example is located from this file, which pytest gives an absolute path.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
EXAMPLES = os.path.join(ROOT, "examples")
CORPUS = os.path.join(ROOT, "battery", "corpus")
REGISTER = os.path.join(EXAMPLES, "asset_register.json")
FIXTURE = os.path.join(EXAMPLES, "declarations", "line1.fixture.json")

if os.path.isdir(os.path.join(ROOT, "src")):
    sys.path.insert(0, os.path.join(ROOT, "src"))


@pytest.fixture
def register():
    from factory_line_audit.presence import load_register
    return load_register(REGISTER)


@pytest.fixture
def clean_walk():
    from factory_line_audit import formats
    return formats.load(os.path.join(CORPUS, "clean.json"), formats.WALK)


@pytest.fixture
def gated(register):
    from factory_line_audit.declarations import gate
    return gate([FIXTURE], register)


def write(tmp_path, name, body):
    path = os.path.join(str(tmp_path), name)
    with open(path, "w", encoding="utf-8") as handle:
        if isinstance(body, str):
            handle.write(body)
        else:
            json.dump(body, handle)
    return path
