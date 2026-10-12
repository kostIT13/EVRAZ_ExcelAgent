"""Прогон примеров запросов из docs/request_examples.txt через API агента."""
import json
import re
import sys
import time
import urllib.request

BASE = "http://localhost:8000"

# (вопрос, ожидаемое значение или None если нечисловой ответ)
QUESTIONS = [
    ("Сколько составила среднерыночная цена на Лом твердых сплавов (без припоя) в декабре 2025 года?", 2697900.0),
    ("Какова была максимальная цена по результатам предложения победителя на аукционе за Лом латуни ЛАЖМц в январе 2025 - декабре 2025 года?", 602922.0),
    ("Какова была средняя цена на все виды медного лома по данным Ферроком в феврале 2025 года?", 696625.15),
    ("Какова была дельта между минимальной и максимальной ценой на все виды медного лома по данным Ферроком, Сплав-21, ЦветМет, шами-сервис, в феврале 2025 года?", 438350.1),
    ("Какова была минимальная цена на цинковый лом за все месяцы?", 164220.0),
    ("Какова была максимальная среднерыночная цена на Лом меди кусок за весь 2025 год (январь-декабрь)?", 906729.75),
    ("Какова была минимальная цена предложения победителя на Лом алюминия за весь 2025 год?", 143692.75),
    ("В каком месяце 2025 года цена на Лом латуни (секции холодильные) по данным компании \"Северо-запад ВторМет\" была максимальной и чему она равнялась?", None),
    ("Какова была максимальная цена на Лом баббита Б83 (Олово 2) по результатам предложения победителя за весь 2025 год?", 2869940.0),
    ("Какая минимальная среднерыночная цена была зафиксирована на Лом алюминия стружка в 2025 году?", 70380.0),
    ("Какова была средняя цена всех видов медного лома (кусочек, микс, в кабеле, стружка, трубка с оребрением, трубка с оребрением меди 87,2%) по данным компании 'Сплав-21' в декабре 2025 года?", 759991.39),
    ("Какова была средняя цена на все виды алюминиевого лома (алюминий, в кабеле, стружка, блоки УБРС, трубка медная с алюм оребрением меди) по данным Шами-сервис в сентябре 2025 года?", 122632.35),
    ("Рассчитайте среднюю цену по трем видам латуни (лом латуни, лом латуни стружка, лом латуни ЛАЖМц) по данным компании \"ЦветМет\" в апреле 2025 года.", 492660.0),
    ("Какова разница (дельта) между максимальной и минимальной ценой на Лом меди кусок среди всех поставщиков (ВРП У, Северо-запад, Ферроком, Сплав-21, ЦветМет, Шами-сервис, УралМетРесурс) в декабре 2025 года?", 141346.5),
    ("Насколько выросла среднерыночная цена на Лом алюминия с января 2025 года по декабрь 2025 года?", -879.75),
    ("Какова разница между ценой предложения победителя и стартовой ценой августа на Лом меди в кабеле в октябре 2025 года?", 23072.91),
    ("Какова была сумма цен на все виды лома баббита (Б83, Б83 стружка, Б16, Б16 стружка) по данным компании \"Ферроком\" в июле 2025 года?", 4516050.0),
    ("В каком месяце 2025 года цена на Лом нержавейки стружка по данным \"Северо-запад ВторМет\" была равна 73 899 руб./тн?", None),
    ("Какова была средняя цена на Лом провода (Ni 91,5%; Cr 4,5%) по всем поставщикам (исключая пустые ячейки) в июне 2025 года?", 576896.06),
    ("Какова была цена на Лом легированный Б26 (рукава СРГС) по данным компании \"Шами-сервис\" в мае 2025 года?", 65394.75),
]


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_number(text: str):
    if not text:
        return None
    # Ищем первое число (с пробелами-разделителями тысяч и запятой как десятичным разделителем)
    m = re.search(r"[\d][\d\s\u00a0]*[\d]?(?:[.,]\d+)?", text.replace("\u00a0", " "))
    if not m:
        return None
    s = m.group(0).strip()
    s = s.replace(" ", "").replace("\u00a0", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _check(actual, expected, tol_pct=1.0):
    if expected is None:
        return None  # нечисловой ответ — не оцениваем
    if actual is None:
        return False
    if expected == 0:
        return abs(actual) < 1.0
    return abs(actual - expected) / abs(expected) * 100 <= tol_pct


def main():
    results = []
    for i, (q, expected) in enumerate(QUESTIONS, 1):
        started = time.monotonic()
        try:
            resp = _post("/ask", {"question": q, "top_k": 10, "mode": "agent"})
            # Если агент просит уточнение — резюмируем с первым вариантом
            if resp.get("status") == "waiting_for_input" and resp.get("waiting_question"):
                opts = resp["waiting_question"].get("options") or []
                choice = opts[0] if opts else "да"
                resp = _post("/ask/resume", {"thread_id": resp["thread_id"], "user_answer": choice})
            status = resp.get("status", "?")
            answer = resp.get("answer", "")
            sql = resp.get("sql_query", "")
            actual = _extract_number(answer)
            ok = _check(actual, expected)
            results.append({
                "id": i,
                "question": q,
                "expected": expected,
                "status": status,
                "answer": answer,
                "actual_number": actual,
                "sql": sql,
                "passed": ok,
                "latency_ms": resp.get("latency_ms"),
            })
            print(f"[{i:02d}] status={status} passed={ok} expected={expected} actual={actual} ({int(time.monotonic()-started)}s)")
            print(f"     Q: {q[:90]}")
            print(f"     A: {answer[:120]}")
        except Exception as exc:
            results.append({"id": i, "question": q, "expected": expected, "status": "error", "error": str(exc), "passed": False})
            print(f"[{i:02d}] ERROR: {exc}")

    passed = sum(1 for r in results if r.get("passed") is True)
    failed = sum(1 for r in results if r.get("passed") is False)
    skipped = sum(1 for r in results if r.get("passed") is None)
    total = len(results)
    print("=" * 70)
    print(f"ИТОГО: {total} | passed={passed} | failed={failed} | skipped(нечисловые)={skipped}")
    if total - skipped > 0:
        print(f"PASS RATE (по числовым): {passed/(total-skipped)*100:.1f}%")
    with open("scripts/request_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print("Результаты сохранены в scripts/request_results.json")


if __name__ == "__main__":
    main()