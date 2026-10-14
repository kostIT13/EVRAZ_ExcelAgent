"""Временный скрипт: прогон вопросов из request_examples_2.txt через API."""
import json
import time
import urllib.request

BASE = "http://localhost:8000"
OUT = "scripts/faked_questions_dump.txt"

QUESTIONS = [
    ("Каковы утверждённая и фактическая доли угля «Распадская ГЖ» на листе «2 блок»?", "10% и 11,1837%"),
    ("На сколько процентных пунктов фактическая доля «Распадская ГЖ» на 2 блоке отличается от утверждённого плана?", "1,18 п.п."),
    ("Каков суммарный расход из силосов по всем строкам поставщика «Краснокаменская КЖ» на листе «2 блок»?", "726,14 т"),
    ("Среди поставщиков листа «2 блок», у которых фактическая доля участия в столбце G больше нуля, какой поставщик имеет наибольшую стоимость?", "Кузнецкая (ш. Юбилейная) — 12 249,69"),
    ("На листе «Отклонения от БЮДЖЕТА и ПЛАНА» сравните фактическую стоимость шихты 2 и 3 блоков. У какого блока она выше и на сколько?", "2 блок выше на 1 272,99"),
    ("Рассчитайте фактическую среднюю стоимость шихты по производству, используя фактические стоимости двух блоков и коэффициенты распределения: 2 блок — 0,5035; 3 блок — 0,4965.", "9 797,03"),
    ("Рассчитай среднюю по производству фактическую долю «Краснокаменской КЖ», используя: факт 2 блока — E61; факт 3 блока — E84; веса блоков — 0,5035 и 0,4965.", "21,029%"),
    ("На листе «Отклонения от БЮДЖЕТА и ПЛАНА» найдите поставщика с наибольшим положительным отклонением фактической средней доли от утверждённого плана. Используй столбец W.", "Сибирь ОС — +2,7304 п.п."),
]


def _post(path, payload, timeout=300):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    lines = []
    for i, (q, expected) in enumerate(QUESTIONS, 1):
        started = time.monotonic()
        try:
            resp = _post("/ask", {"question": q, "top_k": 10, "mode": "agent"})
            if resp.get("status") == "waiting_for_input" and resp.get("waiting_question"):
                opts = resp["waiting_question"].get("options") or []
                resp = _post("/ask/resume", {"thread_id": resp["thread_id"], "user_answer": opts[0] if opts else "да"})
            answer = resp.get("answer", "")
            sql = resp.get("sql_query", "")
            lines.append(f"[{i:02d}] status={resp.get('status')} ({int(time.monotonic()-started)}s)")
            lines.append(f"  Q: {q}")
            lines.append(f"  expected: {expected}")
            lines.append(f"  A: {answer[:300]}")
            lines.append(f"  SQL: {sql[:300]}")
            lines.append("")
        except Exception as exc:
            lines.append(f"[{i:02d}] ERROR: {type(exc).__name__}: {exc}")
            lines.append("")
        # Инкрементальная запись
        with open(OUT, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"[{i:02d}] done", flush=True)

    print("written", OUT)


if __name__ == "__main__":
    main()