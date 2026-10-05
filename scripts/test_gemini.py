import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
print("Key length:", len(key) if key else 0)

try:
    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Say Hello!"
    )
    print("Gemini response:", resp.text.strip())
except Exception as e:
    print("Gemini error:", e)
