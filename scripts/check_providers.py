from app.core.config import get_settings

s = get_settings()
print("LLM_PROVIDER:", s.LLM_PROVIDER)
print("GEMINI_MODEL:", s.GEMINI_MODEL)
print("EMBEDDING_PROVIDER:", s.EMBEDDING_PROVIDER)
print("GEMINI_EMBEDDING_MODEL:", s.GEMINI_EMBEDDING_MODEL)
print("Has GEMINI_API_KEY:", bool(s.GEMINI_API_KEY))
