import requests

url = "http://localhost:8000/ask"
payload = {
    "question": "Сколько составила среднерыночная цена на Лом свинца (пластины от АКБ) в марте 2025 года?",
    "mode": "auto",
}
r = requests.post(url, json=payload, timeout=120)
print(r.status_code)
print(r.json())