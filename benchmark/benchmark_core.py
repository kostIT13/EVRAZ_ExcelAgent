import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "request_examples.txt"

EXPECTED_OVERRIDES: Dict[str, float] = {
    "разница (дельта) между максимальной и минимальной ценой на Лом меди кусок": 141346.5,
    "Насколько выросла среднерыночная цена на Лом алюминия": -879.75,
    "разница между ценой предложения победителя и стартовой ценой августа": 23072.91,
    "сумма цен на все виды лома баббита": 4516050.0,
    "средняя цена на Лом провода": 576896.06,
}

_MONTHS = (
    "янв", "февр", "фев", "март", "апр", "май", "июнь", "июль",
    "авг", "сент", "окт", "нояб", "дек",
)
_NEG_WORDS = (
    "минус", "снизил", "упал", "упала", "ниже", "уменьшил", "уменьшилась",
    "отрицательн", "падени", "понизил", "понизилась", "сократил", "сократилась",
)



def _is_month_breakdown(line: str) -> bool:
    """Строка вида 'дек = 602922 руб/тн' — продолжение помесячного ответа."""
    m = re.match(r"^([а-яё]+)\s*=", line.lower())
    return bool(m and m.group(1) in _MONTHS)


def _parse_first_block(lines: List[str]) -> List[Dict[str, str]]:
    """Первый блок файла (до '|| Сгенерированные') — свободный формат."""
    entries: List[Dict[str, str]] = []
    current_q: List[str] = []
    state = "question"
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Ответ:"):
            if current_q:
                entries.append({
                    "question": " ".join(current_q),
                    "expected_text": line[len("Ответ:"):].strip(),
                })
                current_q = []
            state = "answer"
            continue
        if state == "answer":
            if _is_month_breakdown(line):
                continue  # продолжение ответа (помесячная разбивка)
            state = "question"
            current_q.append(line)
        else:
            current_q.append(line)
    return entries


def _parse_generated_block(lines: List[str]) -> List[Dict[str, str]]:
    """Блок '|| Сгенерированные' — формат 'N. Запрос: ...' / 'Ответ: ...'."""
    entries: List[Dict[str, str]] = []
    current_q: Optional[str] = None
    current_answer: Optional[str] = None
    for raw in lines:
        line = raw.strip()
        m = re.match(r"^(\d+)\.\s*Запрос:\s*(.+)$", line)
        if m:
            if current_q:
                entries.append({
                    "question": current_q,
                    "expected_text": current_answer or "",
                })
            current_q = m.group(2).strip()
            current_answer = None
            continue
        if current_q is not None and current_answer is None:
            am = re.match(r"^Ответ:\s*(.+)$", line)
            if am:
                current_answer = am.group(1).strip()
    if current_q:
        entries.append({
            "question": current_q,
            "expected_text": current_answer or "",
        })
    return entries


def parse_questions(path: Path) -> List[Dict[str, Any]]:
    """Разбирает docs/request_examples.txt в список вопросов с эталонами."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    split_at = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("||")),
        len(lines),
    )
    first_block = _parse_first_block(lines[:split_at])
    generated = _parse_generated_block(lines[split_at:])
    items: List[Dict[str, Any]] = []
    for i, entry in enumerate(first_block + generated, 1):
        items.append({
            "id": i,
            "question": entry["question"],
            "expected_text": entry["expected_text"],
            "expected": _expected_for(entry["question"], entry["expected_text"]),
        })
    return items


def _expected_for(question: str, expected_text: str) -> Optional[float]:
    for key, val in EXPECTED_OVERRIDES.items():
        if key in question:
            return val
    return extract_number(expected_text)



def extract_number(text: str) -> Optional[float]:
    if not text:
        return None
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    for m in re.finditer(r"[-+]?\d[\d\s]*\d?(?:[.,]\d+)?", text):
        s = m.group(0).strip()
        negative = s.startswith("-")
        digits = s.lstrip("+-").replace(" ", "").replace(",", ".")
        # Пропускаем «годы» вида 2025 (4 цифры без разделителей)
        if re.fullmatch(r"\d{4}", digits) and 1900 <= float(digits) <= 2100:
            continue
        try:
            val = float(digits)
        except ValueError:
            continue
        if negative:
            val = -abs(val)
        prefix = text[: m.start()].lower()
        if any(w in prefix for w in _NEG_WORDS):
            val = -abs(val)
        return val
    return None



def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask_question(
    question: str,
    base_url: str,
    api_key: str,
    top_k: int,
    timeout: int,
    mode: str = "agent",
) -> dict:
    """Отправляет вопрос агенту; при уточняющем вопросе отвечает первым вариантом."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    resp = _post(
        f"{base_url}/ask",
        {"question": question, "top_k": top_k, "mode": mode},
        headers,
        timeout,
    )
    if resp.get("status") == "waiting_for_input" and resp.get("waiting_question"):
        opts = resp["waiting_question"].get("options") or []
        choice = opts[0] if opts else "да"
        resp = _post(
            f"{base_url}/ask/resume",
            {"thread_id": resp["thread_id"], "user_answer": choice},
            headers,
            timeout,
        )
    return resp



def check(
    actual: Optional[float],
    expected: Optional[float],
    tol_pct: float,
) -> Optional[bool]:
    """True — совпало, False — не совпало, None — нечисловой эталон (пропуск)."""
    if expected is None:
        return None
    if actual is None:
        return False
    if expected == 0:
        return abs(actual) < 1.0
    return abs(actual - expected) / abs(expected) * 100 <= tol_pct


def run_benchmark(
    questions: List[Dict[str, Any]],
    base_url: str,
    api_key: str,
    top_k: int,
    tolerance: float,
    timeout: int,
    mode: str,
    json_out: Optional[Path],
) -> int:
    results: List[Dict[str, Any]] = []
    total = len(questions)
    for i, item in enumerate(questions, 1):
        started = time.monotonic()
        row: Dict[str, Any] = {
            "id": item["id"],
            "question": item["question"],
            "expected": item["expected"],
            "expected_text": item["expected_text"],
            "status": "error",
            "answer": "",
            "actual_number": None,
            "passed": False,
            "error": None,
            "latency_ms": None,
        }
        try:
            resp = ask_question(item["question"], base_url, api_key, top_k, timeout, mode)
            answer = resp.get("answer", "") or ""
            actual = extract_number(answer)
            ok = check(actual, item["expected"], tolerance)
            row.update({
                "status": resp.get("status", "?"),
                "answer": answer,
                "actual_number": actual,
                "passed": ok,
                "latency_ms": resp.get("latency_ms"),
            })
            marker = "OK  " if ok is True else ("SKIP" if ok is None else "FAIL")
            print(f"[{i:02d}/{total:02d}] {marker} status={row['status']} "
                  f"expected={item['expected']} actual={actual} "
                  f"({int(time.monotonic() - started)}s)")
            print(f"       Q: {item['question'][:110]}")
            print(f"       A: {answer[:130]}")
        except Exception as exc:  # noqa: BLE001 — бенчмарк переживает сбой одного вопроса
            row["error"] = str(exc)[:500]
            print(f"[{i:02d}/{total:02d}] ERROR: {exc}")
        results.append(row)

    passed = sum(1 for r in results if r["passed"] is True)
    failed = sum(1 for r in results if r["passed"] is False)
    skipped = sum(1 for r in results if r["passed"] is None)
    numeric = total - skipped
    rate = passed / numeric * 100 if numeric else 0.0

    print("=" * 72)
    print("BENCHMARK REPORT")
    print("=" * 72)
    print(f"Всего: {total} | Прошло: {passed} | Провалено: {failed} | "
          f"Пропущено (нечисловые): {skipped}")
    print(f"PASS RATE (по числовым ответам): {rate:.1f}% ({passed}/{numeric})")
    print("=" * 72)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "pass_rate": round(rate, 1),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rows": results,
        }
        json_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Результаты сохранены: {json_out}")

    return 0 if failed == 0 else 1


def build_parser(description: str, default_json: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--file",
        type=str,
        default=str(DEFAULT_SOURCE),
        help="Файл с вопросами (по умолчанию docs/request_examples.txt)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.environ.get("BENCHMARK_BASE_URL", "http://localhost:8000"),
        help="Базовый URL API агента (по умолчанию http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("API_KEY", ""),
        help="X-API-Key, если сервер запущен с API_KEY",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Количество релевантных листов (top_k)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1.0,
        help="Относительный допуск сравнения чисел, %%",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Таймаут HTTP-запроса, секунд",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="agent",
        choices=("auto", "rag", "agent"),
        help="Режим агента (по умолчанию agent)",
    )
    parser.add_argument(
        "--json",
        type=str,
        default=default_json,
        help="Путь для JSON-отчёта",
    )
    return parser


if __name__ == "__main__":
    items = parse_questions(DEFAULT_SOURCE)
    print(f"Распарсено вопросов: {len(items)}")
    for it in items:
        print(f"  [{it['id']:02d}] expected={it['expected']!r} | {it['question'][:80]}")
    sys.exit(0)