import os

from dotenv import load_dotenv

# Load the .env file
load_dotenv()


class DefaultConfig:

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
    OCR_MODEL = os.environ.get("OCR_MODEL", "gpt-4.1-mini")
    EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", "gpt-4.1-mini")
