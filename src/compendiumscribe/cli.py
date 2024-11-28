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
def main(domain: str):
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
        domain_object = research_domain(domain, llm_client, online_llm_client)

        # Save the domain to a file by pickling it
        with open("compendium.pickle", "wb") as f:
            pickle.dump(domain_object, f)

        # Save the entire domain_object to an XML file as well
        xml_string = domain_object.to_xml_string()
        with open("compendium.xml", "w") as f:
            f.write(xml_string)

    except Exception as e:
        print(f"An error occurred while creating the compendium: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
