import json
from datetime import datetime, timezone
from pathlib import Path

import click

from .compendium import Compendium, slugify
from .create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
)
from .research import (
    CancellationContext,
    DeepResearchError,
    MissingConfigurationError,
    ResearchCancelledError,
    ResearchConfig,
    ResearchProgress,
    ResearchTimeoutError,
    build_compendium,
    recover_compendium,
)


@click.group()
def cli() -> None:
    """Compendium Scribe: AI Research & Rendering Tool."""


@cli.command()
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
def create(
    topic: str,
    output_path: Path | None,
    no_background: bool,
    formats: tuple[str, ...],
    max_tool_calls: int | None,
):
    """Generate a research compendium for TOPIC."""

    click.echo(f"Preparing deep research assignment for '{topic}'.")

    def handle_progress(update: ResearchProgress) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        phase_label = update.phase.replace("_", " ").title()
        suffix = ""
        meta = update.metadata or {}
        if "poll_attempt" in meta:
            suffix = f" (poll #{meta['poll_attempt']})"

        if "elapsed_seconds" in meta:
            seconds = meta["elapsed_seconds"]
            mins, secs = divmod(seconds, 60)
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            suffix += f" [Time elapsed: {time_str}]"

        stream_kwargs = {"err": update.status == "error"}
        click.echo(
            f"[{timestamp}] {phase_label}: {update.message}{suffix}",
            **stream_kwargs,
        )

        # Display blueprint section titles when available
        if "section_titles" in meta and meta["section_titles"]:
            for title in meta["section_titles"]:
                click.echo(f"           - {title}")
        if "plan_json" in meta and meta["plan_json"]:
            click.echo("           Research blueprint JSON:")
            click.echo(meta["plan_json"])

    try:
        config = ResearchConfig(
            background=not no_background,
            max_tool_calls=max_tool_calls,
            progress_callback=handle_progress,
        )
        client = create_openai_client(timeout=config.request_timeout_seconds)

        # Set up cancellation context for graceful Ctrl+C handling
        cancel_ctx = CancellationContext(client, config)
        cancel_ctx.install_signal_handler()

        try:
            compendium = build_compendium(
                topic, client=client, config=config, cancel_ctx=cancel_ctx
            )
        finally:
            cancel_ctx.restore_signal_handler()
    except ResearchCancelledError as exc:
        click.echo(f"\nResearch cancelled (ID: {exc.research_id}).", err=True)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        click.echo("\nHard shutdown requested.", err=True)
        raise SystemExit(1)
    except ResearchTimeoutError as exc:
        compendium_title = getattr(exc, "compendium_title", None)
        timeout_data = {
            "research_id": exc.research_id,
            "topic": topic,
            "title": compendium_title or topic,
            "no_background": no_background,
            "formats": list(formats),
            "max_tool_calls": max_tool_calls,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        timeout_payload = json.dumps(timeout_data, indent=2)
        Path("timed_out_research.json").write_text(timeout_payload)
        click.echo(
            f"\n[!] Deep research timed out (ID: {exc.research_id}).",
            err=True,
        )
        click.echo(
            "Stored recovery information in timed_out_research.json",
            err=True,
        )
        raise SystemExit(1) from exc
    except MissingAPIKeyError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(1) from exc
    except MissingConfigurationError as exc:
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
        # If output_path has a suffix, we use it as the stem to avoid out.md.md
        base_path = output_path.parent / output_path.stem
    else:
        name_for_slug = compendium.topic or topic
        slug = slugify(name_for_slug)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_path = Path(f"{slug}_{timestamp}")

    _write_outputs(compendium, base_path, formats)


@cli.command()
@click.argument(
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--format",
    "formats",
    type=click.Choice(["md", "xml", "html", "pdf"], case_sensitive=False),
    multiple=True,
    default=["html"],
    show_default=True,
    help="Output format(s). Can be specified multiple times.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False, writable=True),
    help="Base path/filename for the output.",
)
def render(
    input_file: Path,
    formats: tuple[str, ...],
    output_path: Path | None,
):
    """Render an existing compendium XML file to other formats.

    INPUT_FILE is the path to the existing compendium XML file.
    """
    try:
        click.echo(f"Reading compendium from {input_file}...")
        compendium = Compendium.from_xml_file(str(input_file))
    except Exception as exc:
        click.echo(f"Error parsing XML file: {exc}", err=True)
        raise SystemExit(1) from exc

    # Determine base filename stem
    if output_path:
        base_path = output_path.parent / output_path.stem
    else:
        # Defaults to the input filename (without extension) in the same
        # directory.
        base_path = input_file.parent / input_file.stem

    _write_outputs(compendium, base_path, formats)


@cli.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=Path("timed_out_research.json"),
    show_default=True,
    help="Path to the recovery JSON file.",
)
def recover(input_file: Path):
    """Recover a timed-out deep research run."""
    if not input_file.exists():
        click.echo(f"Error: Recovery file {input_file} not found.", err=True)
        raise SystemExit(1)

    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
        research_id = data["research_id"]
        topic = data["topic"]
        title = data.get("title") or topic
        formats = tuple(data["formats"])
        max_tool_calls = data.get("max_tool_calls")
        no_background = data.get("no_background", False)
    except (json.JSONDecodeError, KeyError) as exc:
        click.echo(f"Error: Failed to parse recovery file: {exc}", err=True)
        raise SystemExit(1)

    click.echo(
        f"Checking status for research ID: {research_id} ('{title}')..."
    )

    config = ResearchConfig(
        background=not no_background,
        max_tool_calls=max_tool_calls,
    )

    try:
        compendium = recover_compendium(
            research_id=research_id,
            topic=title,
            config=config,
        )

        click.echo("Research completed! Writing outputs.")

        slug = slugify(title)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base_path = Path(f"{slug}_{timestamp}")

        _write_outputs(compendium, base_path, formats)

    except DeepResearchError as exc:
        click.echo(str(exc), err=True)
        return
    except Exception as exc:
        click.echo(f"Error during recovery: {exc}", err=True)
        raise SystemExit(1)


def _write_outputs(
    compendium: "Compendium", base_path: Path, formats: tuple[str, ...]
) -> None:
    """Helper to write compendium outputs to disk."""
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
                target_file.write_text(
                    compendium.to_markdown(),
                    encoding="utf-8",
                )
            elif fmt == "xml":
                target_file.write_text(
                    compendium.to_xml_string(),
                    encoding="utf-8",
                )
            elif fmt == "pdf":
                target_file.write_bytes(compendium.to_pdf_bytes())

            click.echo(f"Compendium written to {target_file}")


if __name__ == "__main__":  # pragma: no cover
    cli()
