import sys
import click

from compendiumscribe.create_compendium import create_compendium


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

    try:
        create_compendium(domain)
    except Exception as e:
        print(f"An error occurred while creating the compendium: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
