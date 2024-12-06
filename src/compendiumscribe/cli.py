import pickle
import re
import sys
import click
from dotenv import load_dotenv
from datetime import datetime
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

        # Create a file-friendly name string based on the domain name, in the form:
        # domain_name_with_underscores_2024-12-31
        # by:
        # 1. removing any non-alphanumeric characters
        # 2. converting spaces to underscores
        # 3. converting to lowercase
        # 4. Removing any underscores from the beginning or end of the string
        # 5. Removing any consecutive underscores
        # 6. Removing any trailing underscores
        # 7. Adding the date of creation (YYYY-MM-DD) to the end of the string, separated by a single underscore
        file_friendly_domain_name = re.sub(r"[^a-zA-Z0-9]+", "_", domain).lower()
        file_friendly_domain_name = re.sub(r"^_+|_+$", "", file_friendly_domain_name)
        file_friendly_domain_name = re.sub(r"_{2,}", "_", file_friendly_domain_name)
        file_friendly_domain_name = (
            file_friendly_domain_name + "_" + datetime.now().strftime("%Y-%m-%d")
        )

        # Save the domain to a file by pickling it
        pickle_filename = f"{file_friendly_domain_name}.compendium.pickle"
        with open(pickle_filename, "wb") as f:
            pickle.dump(domain_object, f)

        # Save the entire domain_object to an XML file as well
        xml_filename = f"{file_friendly_domain_name}.compendium.xml"
        xml_string = domain_object.to_xml_string()
        with open(xml_filename, "w") as f:
            f.write(xml_string)

    except Exception as e:
        print(f"An error occurred while creating the compendium: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
