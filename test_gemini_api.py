import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("NO API KEY")
    exit()

print(f"API Key starting with: {api_key[:10]}...")

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro-latest') 

try:
    response = model.generate_content(
        "Respond with {" + '"test": "ok"' + "}",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.0
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("EXCEPTION CAUGHT:", type(e).__name__)
    print("DETAILS:", str(e))
