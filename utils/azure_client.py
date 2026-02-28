"""
Azure AI Foundry client helper.
Uses the OpenAI client with the /openai/v1/ base URL — the correct pattern
for Azure AI Foundry endpoints (*.services.ai.azure.com).
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def get_client() -> OpenAI:
    api_key = os.getenv("AZURE_OPENAI_KEY", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    base_url = endpoint.rstrip("/") + "/openai/v1/"
    return OpenAI(api_key=api_key, base_url=base_url)


def get_deployment() -> str:
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o").strip()
