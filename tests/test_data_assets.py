from __future__ import annotations

import json
import re
from pathlib import Path


def get_data_dir() -> Path:
    current_dir = Path(__file__).parent
    return current_dir.parent / "app" / "data"


def test_category_taxonomy_valid() -> None:
    data_path = get_data_dir() / "category_taxonomy.json"
    assert data_path.exists()

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    # At least 15 top-level categories
    assert len(data) >= 15
    for cat, subcats in data.items():
        assert isinstance(cat, str)
        assert isinstance(subcats, list)
        # At least 3 subcategories each
        assert len(subcats) >= 3
        for sub in subcats:
            assert isinstance(sub, str)


def test_mcc_codes_valid() -> None:
    data_path = get_data_dir() / "mcc_codes.json"
    assert data_path.exists()

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    # At least 50 mappings
    assert len(data) >= 50
    for code, mapping in data.items():
        assert isinstance(code, str)
        assert len(code) == 4
        assert isinstance(mapping, list)
        assert len(mapping) == 2
        assert isinstance(mapping[0], str)  # Category
        assert isinstance(mapping[1], str)  # Subcategory


def test_merchant_rules_valid() -> None:
    data_path = get_data_dir() / "merchant_rules.json"
    assert data_path.exists()

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert "rules" in data
    rules = data["rules"]
    assert isinstance(rules, list)
    # At least 30 rules
    assert len(rules) >= 30
    for rule in rules:
        assert isinstance(rule, list)
        assert len(rule) == 3
        pattern, cat, sub = rule
        assert isinstance(pattern, str)
        assert isinstance(cat, str)
        assert isinstance(sub, str)

        # Test compiling regex pattern
        re.compile(pattern)


def test_shariah_blocklist_valid() -> None:
    data_path = get_data_dir() / "shariah_blocklist.json"
    assert data_path.exists()

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, dict)
    assert "blocklisted_mcc" in data
    assert "keyword_patterns" in data

    mccs = data["blocklisted_mcc"]
    assert isinstance(mccs, list)
    for code in mccs:
        assert isinstance(code, str)
        assert len(code) == 4

    keywords = data["keyword_patterns"]
    assert isinstance(keywords, list)
    for kw in keywords:
        assert isinstance(kw, str)
        re.compile(kw)


def test_prompt_files_exist_and_non_empty() -> None:
    prompt_dir = get_data_dir() / "prompts"
    assert prompt_dir.exists()

    expected_prompts = [
        "categorization.txt",
        "shariah_screening.txt",
        "insight_generation.txt",
    ]

    for filename in expected_prompts:
        filepath = prompt_dir / filename
        assert filepath.exists(), f"Prompt file {filename} does not exist"
        content = filepath.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"Prompt file {filename} is empty"
