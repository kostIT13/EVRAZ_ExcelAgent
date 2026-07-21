from openai import OpenAI

client = OpenAI(
    api_key="sk-602c5e01001847ab973b77a658372860",
    base_url="http://deepcode.ci.nsu.ru/api/v1",
)

response = client.chat.completions.create(
    model="deepseek-ai/DeepSeek-V4-Flash",
    messages=[
        {
            "role": "user",
            "content": "Привет! Расскажи, ты крутой?"
        }
    ],
    temperature=0.7,
    top_p=0.8,
)

print(response.choices[0].message.content)