"""Pytest-конфигурация для EVRAZ agent.

- регистрирует marker 'golden' (LLM-интеграция, включается флагом --golden).
- CI-режим по умолчанию: golden-тесты отключены (только юнит-проверки), чтобы
  не требовать LLM-модель при каждом прогоне.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "golden: интеграционные тесты golden-dataset, требующие LLM-модель и данные.",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--golden",
        action="store_true",
        default=False,
        help="Включить golden-интеграционные тесты (требуют LLM и загруженные данные).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--golden"):
        return
    skip_golden = pytest.mark.skip(reason="Включите --golden для LLM-интеграции")
    for item in items:
        if "golden" in item.keywords:
            item.add_marker(skip_golden)