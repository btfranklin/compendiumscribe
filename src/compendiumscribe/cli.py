import pickle
import sys
import click
from dotenv import load_dotenv
import colorama.initialise as colorama

from compendiumscribe.create_llm_clients import create_llm_clients
from compendiumscribe.research_domain import research_domain


@click.command()
@click.option(
    "--domain",
    prompt="Domain of expertise",
    help="The domain of expertise to create the compendium for.",
)
def main(domain_name: str):
    """
    Command-line entry point for creating a compendium.
    """

    # Load environment variables from .env file
    load_dotenv()

    # Initialize colorama
    colorama.init(autoreset=True)

    # Create the LLM clients
    llm_client, online_llm_client = create_llm_clients()

    try:
        domain = research_domain(domain_name, llm_client, online_llm_client)

        # Save the domain to a file by pickling it
        with open(f"compendium_{domain_name}.pickle", "wb") as f:
            pickle.dump(domain, f)

        # Save the entire domain to an XML file as well
        domain.save(f"compendium_{domain_name}.xml")
        print(
            f"Compendium saved to compendium_{domain_name}.pickle and compendium_{domain_name}.xml"
        )

    except Exception as e:
        print(f"An error occurred while creating the compendium: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
