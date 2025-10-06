from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import click

from .create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
)
from .research_domain import (
    DeepResearchError,
    ResearchConfig,
    ResearchProgress,
    build_compendium,
)


def _default_output_path(topic: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    if not slug:
        slug = "compendium"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{slug}_{timestamp}.xml")


@click.command()
@click.argument("topic", type=str)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False, writable=True),
    help="Save XML to this path (defaults to a timestamped filename).",
)
@click.option(
    "--no-background",
    is_flag=True,
    help="Run deep research synchronously instead of background mode.",
)
@click.option(
    "--no-stream-progress",
    is_flag=True,
    help="Disable streaming updates from the deep research run.",
)
@click.option(
    "--export-format",
    "export_formats",
    type=click.Choice(["md", "html", "pdf"], case_sensitive=False),
    multiple=True,
    help=(
        "Additional formats to export alongside XML (may be repeated)."
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
    no_stream_progress: bool,
    export_formats: tuple[str, ...],
    max_tool_calls: int | None,
):
    """Generate a research compendium for TOPIC and save it as XML."""

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
        stream_progress=not no_stream_progress,
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

    output_path = output_path or _default_output_path(topic)
    output_path.write_text(compendium.to_xml_string(), encoding="utf-8")

    click.echo(f"Compendium written to {output_path}")

    additional_outputs: list[tuple[str, Path]] = []
    normalized_formats = tuple(
        dict.fromkeys(fmt.lower() for fmt in export_formats)
    )

    for fmt in normalized_formats:
        target = output_path.with_suffix(f".{fmt}")
        if fmt == "md":
            target.write_text(compendium.to_markdown(), encoding="utf-8")
        elif fmt == "html":
            target.write_text(compendium.to_html(), encoding="utf-8")
        elif fmt == "pdf":
            target.write_bytes(compendium.to_pdf_bytes())
        else:  # pragma: no cover - guarded by Click choice
            continue
        additional_outputs.append((fmt.upper(), target))

    for label, path in additional_outputs:
        click.echo(f"{label} export written to {path}")


if __name__ == "__main__":  # pragma: no cover
    main()
