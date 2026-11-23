"""Workflow files must have no duplicate mapping keys.

GitHub rejects a workflow whose YAML repeats a key in one mapping ("workflow
file issue": 0 jobs, failed run) and then stops firing its schedule. PyYAML
accepts duplicates silently, so a plain safe_load check misses it. On
2026-11-22 a repeated HIGGSFIELD_API_KEY in daily-short.yml's env block
stopped all posting for ~29 hours.
"""
import glob
import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(glob.glob(os.path.join(ROOT, ".github", "workflows", "*.y*ml")))


def _duplicates(path):
    found = []

    class Loader(yaml.SafeLoader):
        pass

    def construct(loader, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in seen:
                found.append((key, key_node.start_mark.line + 1))
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct)
    with open(path) as fh:
        yaml.load(fh, Loader=Loader)
    return found


def test_workflows_found():
    assert FILES


@pytest.mark.parametrize("path", FILES, ids=[os.path.basename(p) for p in FILES])
def test_no_duplicate_keys(path):
    assert _duplicates(path) == []
