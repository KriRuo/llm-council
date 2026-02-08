"""Configuration for the LLM Council."""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Validate API key is present
if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY environment variable is required.\n"
        "Please create a .env file in the project root with:\n"
        "OPENROUTER_API_KEY=sk-or-v1-your-key-here\n"
        "Get your API key from https://openrouter.ai/"
    )

# Warn if API key format looks incorrect
if not OPENROUTER_API_KEY.startswith("sk-or-"):
    print(
        f"WARNING: OPENROUTER_API_KEY doesn't match expected format (should start with 'sk-or-')",
        file=sys.stderr
    )

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"
