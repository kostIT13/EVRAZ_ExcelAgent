"""
Запуск golden-прогона с хоста разработчика без правки .env.

Проблема: в .env (для docker compose) хост БД указан как 'postgres'.
С хоста Windows это имя не резолвится — нужен 'localhost'.
Этот скрипт читает .env, заменяет docker-имя на localhost ТОЛЬКО
в переменных окружения запускаемого процесса и выполняет
run_golden_report.py. Файл .env и docker-стек не затрагиваются.

Использование:
    python scripts/run_golden_local.py                        # полный прогон
    python scripts/run_golden_local.py --limit 5              # первые 5 вопросов
    python scripts/run_golden_local.py --json out/report.json # сохранить отчёт
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def load_env() -> dict:
    values: dict = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    return values


def main() -> int:
    env = os.environ.copy()
    values = load_env()

    url = values.get("POSTGRES_URL") or ""
    m = re.match(r"^(postgresql(?:\+asyncpg)?://[^@]+)@([^:/]+)(.*)$", url)
    if m and m.group(2) != "localhost":
        env["POSTGRES_URL"] = f"{m.group(1)}@localhost{m.group(3)}"
        print(f"POSTGRES_URL: host '{m.group(2)}' -> localhost")

    host = values.get("POSTGRES_HOST") or ""
    if host and host != "localhost":
        env["POSTGRES_HOST"] = "localhost"
        print(f"POSTGRES_HOST: '{host}' -> localhost")

    target = ROOT / "scripts" / "run_golden_report.py"
    cmd = [sys.executable, str(target), *sys.argv[1:]]
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    sys.exit(main())