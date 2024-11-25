import os
import sys
from colorama import Fore
from openai import OpenAI


def create_llm_clients() -> tuple[OpenAI, OpenAI]:
    """
    Create OpenAI and Perplexity clients for use in the research domain pipeline.

    Please note that load_env() must be called before this function is called, and
    colorama must be initialized before this function is called.

    Returns:
        tuple[OpenAI, OpenAI]: The OpenAI and Perplexity clients.
    """

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    perplexity_api_key = os.environ.get("PERPLEXITY_API_KEY")

    if not openai_api_key:
        print(f"{Fore.RED}OPENAI_API_KEY not found in environment variables.")
        sys.exit(1)

    llm_client = OpenAI(api_key=openai_api_key)

    if perplexity_api_key:
        online_llm_client = OpenAI(
            api_key=perplexity_api_key,
            base_url="https://api.perplexity.ai",
        )
    else:
        print(f"{Fore.RED}Unable to create online LLM client. Research impossible.")
        sys.exit(1)

    return llm_client, online_llm_client
