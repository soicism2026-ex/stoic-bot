"""Every workflow file must be one GitHub accepts. On 2026-11-22 a duplicate
HIGGSFIELD_API_KEY in daily-short.yml's env made GitHub reject the whole file:
no Short was posted for about 40 hours, while yaml.safe_load (which keeps the
last of two equal keys) and every other test stayed green."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))


class _StrictLoader(yaml.SafeLoader):
    pass


def _no_duplicates(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r} (GitHub rejects the whole workflow)", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_has_a_duplicate_key(path):
    yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)


def test_the_check_catches_the_nov_22_mistake():
    bad = "jobs:\n  a:\n    steps:\n      - run: x\n        env:\n          K: 1\n          K: 2\n"
    with pytest.raises(yaml.constructor.ConstructorError, match="duplicate key 'K'"):
        yaml.load(bad, Loader=_StrictLoader)
