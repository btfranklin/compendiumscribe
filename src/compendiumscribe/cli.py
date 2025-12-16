from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import click

from .create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
)
from .research import (
    DeepResearchError,
    ResearchConfig,
    ResearchProgress,
    build_compendium,
)


def _generate_slug(topic: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not slug:
        slug = "compendium"
    return slug


@click.command()
@click.argument("topic", type=str)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False, writable=True),
    help="Base path/filename for the output. Extension will be ignored.",
)
@click.option(
    "--no-background",
    is_flag=True,
    help="Run deep research synchronously instead of background mode.",
)
@click.option(
    "--format",
    "formats",
    type=click.Choice(["md", "xml", "html", "pdf"], case_sensitive=False),
    multiple=True,
    default=["md"],
    show_default=True,
    help=(
        "Output format(s). Can be specified multiple times."
    ),
)
@click.option(
    "--max-tool-calls",
    type=int,
    default=None,
    help="Limit total tool calls allowed for the deep research model.",
)
def main(
    topic: str,
    output_path: Path | None,
    no_background: bool,
    formats: tuple[str, ...],
    max_tool_calls: int | None,
):
    """Generate a research compendium for TOPIC."""

    click.echo(f"Preparing deep research assignment for '{topic}'.")

    def handle_progress(update: ResearchProgress) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        phase_label = update.phase.replace("_", " ").title()
        suffix = ""
        meta = update.metadata or {}
        if "poll_attempt" in meta:
            suffix = f" (poll #{meta['poll_attempt']})"
        stream_kwargs = {"err": update.status == "error"}
        click.echo(
            f"[{timestamp}] {phase_label}: {update.message}{suffix}",
            **stream_kwargs,
        )

    config = ResearchConfig(
        background=not no_background,
        max_tool_calls=max_tool_calls,
        progress_callback=handle_progress,
    )

    try:
        client = create_openai_client(timeout=config.request_timeout_seconds)
        compendium = build_compendium(topic, client=client, config=config)
    except MissingAPIKeyError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(1) from exc
    except DeepResearchError as exc:
        click.echo(f"Deep research failed: {exc}", err=True)
        raise SystemExit(1) from exc
    except Exception as exc:  # pragma: no cover - defensive logging for CLI
        click.echo(f"Unexpected error: {exc}", err=True)
        raise SystemExit(1) from exc

    # Determine base filename stem
    if output_path:
        base_path = output_path.parent / output_path.stem
    else:
        slug = _generate_slug(topic)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = Path(f"{slug}_{timestamp}")

    unique_formats = sorted(list(set(fmt.lower() for fmt in formats)))

    for fmt in unique_formats:
        if fmt == "html":
            # HTML creates a directory of files
            site_dir = base_path.parent / base_path.name
            site_files = compendium.to_html_site()
            for rel_path, content in site_files.items():
                target = site_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            click.echo(f"HTML site written to {site_dir}/")
        else:
            target_file = base_path.with_suffix(f".{fmt}")

            if fmt == "md":
                target_file.write_text(compendium.to_markdown(), encoding="utf-8")
            elif fmt == "xml":
                target_file.write_text(compendium.to_xml_string(), encoding="utf-8")
            elif fmt == "pdf":
                target_file.write_bytes(compendium.to_pdf_bytes())

            click.echo(f"Compendium written to {target_file}")


if __name__ == "__main__":  # pragma: no cover
    main()
