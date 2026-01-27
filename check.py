import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("Gemini_PRO_API"))

# 利用可能なモデルをリストアップ
print("利用可能なモデル一覧:")
for m in client.models.list():
    if 'generateContent' in m.supported_actions:
        print(f"- {m.name}")