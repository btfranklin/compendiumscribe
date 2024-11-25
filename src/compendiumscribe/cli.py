import sys
import click

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

    try:
        domain = research_domain(domain_name)
    except Exception as e:
        print(f"An error occurred while creating the compendium: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
