from datetime import datetime, timezone
from pathlib import Path

import click

from .compendium import Compendium, OKFError, slugify, write_okf_bundle
from .create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
)
from .library import (
    LibraryError,
    import_compendium,
    publish_compendium,
    validate_library as validate_library_path,
)
from .research import (
    DeepResearchError,
    MissingConfigurationError,
    ResearchConfig,
    ResearchProgress,
    build_compendium,
    recover_compendium,
)
from .research.costs import CostPricing, CostTracker
from .research.agents_workflow.agents import selected_profile_agent_model
from .research.pricing import resolve_model_pricing


OUTPUT_FORMATS = ("okf", "xml", "html", "pdf")


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
    "--format",
    "formats",
    type=click.Choice(OUTPUT_FORMATS, case_sensitive=False),
    multiple=True,
    default=["okf"],
    show_default=True,
    help=("Output format(s). Can be specified multiple times."),
)
@click.option(
    "--library",
    "library_path",
    type=click.Path(path_type=Path, file_okay=False, writable=True),
    help="Also publish the finished compendium into a library directory.",
)
def create(
    topic: str,
    output_path: Path | None,
    formats: tuple[str, ...],
    library_path: Path | None,
):
    """Generate a research compendium for TOPIC."""

    click.echo(f"Preparing agentic research workflow for '{topic}'.")
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cost_tracker: CostTracker | None = None
    base_path = _base_path_for_run(
        topic=topic,
        output_path=output_path,
        run_timestamp=run_timestamp,
    )
    state_path = base_path.with_suffix(".research.json")

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

        # Display plan section titles when available.
        if "section_titles" in meta and meta["section_titles"]:
            for title in meta["section_titles"]:
                click.echo(f"           - {title}")
        if "plan_json" in meta and meta["plan_json"]:
            click.echo("           Research blueprint JSON:")
            click.echo(meta["plan_json"])

    try:
        config = ResearchConfig(progress_callback=handle_progress)
        client = create_openai_client(timeout=config.request_timeout_seconds)
        cost_tracker = _build_cost_tracker(
            base_path=base_path,
            config=config,
        )
        _echo_cost_pricing_context(cost_tracker)

        compendium = build_compendium(
            topic,
            client=client,
            config=config,
            cost_tracker=cost_tracker,
            state_path=state_path,
            output_formats=list(formats),
        )
    except KeyboardInterrupt:
        click.echo("\nHard shutdown requested.", err=True)
        raise SystemExit(1)
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

    _write_outputs(compendium, base_path, formats)
    if library_path is not None:
        try:
            entry = publish_compendium(compendium, library_path)
        except LibraryError as exc:
            click.echo(f"Library publish failed: {exc}", err=True)
            raise SystemExit(1) from exc
        click.echo(
            "Compendium published to library entry "
            f"'{entry.id}' at {library_path / entry.path}"
        )
    _echo_cost_summary(cost_tracker)


def _build_cost_tracker(
    *,
    base_path: Path,
    config: ResearchConfig,
) -> CostTracker:
    baseline_model = selected_profile_agent_model(
        config.contract4agents_profile,
        "ResearchManagerAgent",
    )
    default_pricing = _resolve_cost_pricing(baseline_model) or CostPricing(
        input_per_1m_usd=None,
        output_per_1m_usd=None,
        cached_input_per_1m_usd=None,
        requested_model=baseline_model,
    )
    tracker = CostTracker(
        path=base_path.with_suffix(".costs.json"),
        pricing=default_pricing,
        pricing_resolver=_resolve_cost_pricing,
    )
    tracker.initialize_report()
    return tracker


def _resolve_cost_pricing(model: str) -> CostPricing | None:
    model_pricing = resolve_model_pricing(model)
    if model_pricing is None:
        return None
    return model_pricing.to_cost_pricing()


def _base_path_for_run(
    *,
    topic: str,
    output_path: Path | None,
    run_timestamp: str,
) -> Path:
    if output_path is not None:
        return output_path.parent / output_path.stem
    return Path(f"{slugify(topic)}_{run_timestamp}")


def _echo_cost_pricing_context(cost_tracker: CostTracker) -> None:
    pricing = cost_tracker.pricing
    if pricing.configured:
        resolved_model = (
            pricing.resolved_model or pricing.requested_model or "configured-model"
        )
        tier = pricing.tier or "unknown"
        click.echo(
            "Cost estimator: using local pricing catalog for "
            f"{resolved_model} ({tier} tier)."
        )
        return
    requested_model = pricing.requested_model or "unknown-model"
    click.echo(
        "Cost estimator: no matching catalog entry for "
        f"'{requested_model}'. Usage will be tracked without USD estimates."
    )


def _echo_cost_summary(cost_tracker: CostTracker | None) -> None:
    if cost_tracker is None:
        return
    if cost_tracker.step_count == 0:
        click.echo("Cost report: no usage metrics were captured for this run.")
        return

    totals = cost_tracker.totals_snapshot()
    estimated_cost = totals.get("estimated_cost_usd")
    estimated_cost_display = "unavailable"
    if isinstance(estimated_cost, (int, float)):
        estimated_cost_display = f"${float(estimated_cost):.6f}"

    click.echo(f"Cost report written to {cost_tracker.path}")
    click.echo(
        "Usage totals: "
        f"input={totals.get('input_tokens', 0)}, "
        f"cached_input={totals.get('cached_input_tokens', 0)}, "
        f"output={totals.get('output_tokens', 0)}, "
        f"reasoning={totals.get('reasoning_tokens', 0)}, "
        f"est={estimated_cost_display}"
    )
    tool_calls = totals.get("tool_calls")
    if isinstance(tool_calls, dict) and tool_calls:
        click.echo(f"Tool calls: {tool_calls}")


@cli.command()
@click.argument(
    "input_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
)
@click.option(
    "--format",
    "formats",
    type=click.Choice(OUTPUT_FORMATS, case_sensitive=False),
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
    input_path: Path,
    formats: tuple[str, ...],
    output_path: Path | None,
):
    """Render an existing XML or OKF compendium to other formats.

    INPUT_PATH is an XML file or CompendiumScribe OKF directory.
    """
    try:
        click.echo(f"Reading compendium from {input_path}...")
        if input_path.is_dir():
            compendium = Compendium.from_okf_bundle(input_path)
        elif input_path.suffix.lower() == ".xml":
            compendium = Compendium.from_xml_file(str(input_path))
        else:
            raise ValueError(
                "Input must be an XML file or CompendiumScribe OKF directory."
            )
    except Exception as exc:
        click.echo(f"Error parsing compendium: {exc}", err=True)
        raise SystemExit(1) from exc

    if output_path:
        base_path = output_path.parent / output_path.stem
    else:
        base_path = input_path.parent / input_path.stem

    okf_destination = base_path.parent / f"{base_path.name}.okf"
    if (
        input_path.is_dir()
        and "okf" in {fmt.lower() for fmt in formats}
        and okf_destination.resolve() == input_path.resolve()
    ):
        raise click.ClickException(
            "Refusing to overwrite the input OKF bundle. "
            "Choose a different --output path."
        )

    _write_outputs(compendium, base_path, formats)


@cli.group(name="library")
def library_commands() -> None:
    """Manage filesystem-backed compendium libraries."""


@library_commands.command(name="import")
@click.argument(
    "library_path",
    type=click.Path(path_type=Path, file_okay=False, writable=True),
)
@click.argument(
    "source_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path),
)
def library_import(library_path: Path, source_path: Path) -> None:
    """Import an XML or OKF compendium into LIBRARY_PATH."""

    try:
        entry = import_compendium(
            library_path=library_path,
            source_path=source_path,
        )
    except LibraryError as exc:
        click.echo(f"Library import failed: {exc}", err=True)
        raise SystemExit(1) from exc
    click.echo(
        f"Imported '{entry.title}' as library entry '{entry.id}' "
        f"at {library_path / entry.path}"
    )


@library_commands.command(name="validate")
@click.argument(
    "library_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def library_validate(library_path: Path) -> None:
    """Validate a strict CompendiumScribe OKF Library."""

    issues = validate_library_path(library_path)
    if issues:
        click.echo(f"Library validation failed for {library_path}:", err=True)
        for issue in issues:
            click.echo(f"- {issue}", err=True)
        raise SystemExit(1)
    click.echo(f"Library is valid: {library_path}")


@cli.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the .research.json sidecar state file.",
)
@click.option(
    "--allow-paid-follow-up",
    is_flag=True,
    help="Allow one saved targeted-research call for this recovery.",
)
def recover(input_file: Path, allow_paid_follow_up: bool):
    """Recover an Agents SDK research run from sidecar state."""
    if not input_file.exists():
        click.echo(f"Error: Recovery file {input_file} not found.", err=True)
        raise SystemExit(1)

    try:
        from .research.agents_workflow import load_state

        state = load_state(input_file)
    except Exception as exc:
        click.echo(f"Error: Failed to parse recovery state: {exc}", err=True)
        raise SystemExit(1)

    title = state.title or state.topic
    formats = tuple(state.output_formats or ["okf"])
    unsupported_formats = sorted(
        {fmt.lower() for fmt in formats} - set(OUTPUT_FORMATS)
    )
    if unsupported_formats:
        unsupported = ", ".join(unsupported_formats)
        click.echo(
            "Recovery state requests unsupported output format(s): "
            f"{unsupported}. Restart the research run with a supported format.",
            err=True,
        )
        raise SystemExit(1)
    click.echo(f"Recovering research state for '{title}'...")

    cost_tracker: CostTracker | None = None

    try:
        config = ResearchConfig()
        client = create_openai_client(timeout=config.request_timeout_seconds)
        cost_path = (
            Path(state.cost_report_path)
            if state.cost_report_path
            else _base_path_from_state_path(input_file).with_suffix(".costs.json")
        )
        baseline_model = selected_profile_agent_model(
            config.contract4agents_profile,
            "ResearchManagerAgent",
        )
        cost_tracker = CostTracker(
            path=cost_path,
            pricing=_resolve_cost_pricing(baseline_model)
            or CostPricing(
                input_per_1m_usd=None,
                output_per_1m_usd=None,
                cached_input_per_1m_usd=None,
                requested_model=baseline_model,
            ),
            pricing_resolver=_resolve_cost_pricing,
        )
        cost_tracker.initialize_report()

        compendium = recover_compendium(
            input_file,
            client=client,
            config=config,
            cost_tracker=cost_tracker,
            allow_paid_follow_up=allow_paid_follow_up,
        )

        click.echo("Research completed! Writing outputs.")

        base_path = _base_path_from_state_path(input_file)

        _write_outputs(compendium, base_path, formats)
        _echo_cost_summary(cost_tracker)

    except MissingAPIKeyError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(1) from exc
    except MissingConfigurationError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(1) from exc
    except DeepResearchError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        click.echo(f"Error during recovery: {exc}", err=True)
        raise SystemExit(1)


def _write_outputs(
    compendium: "Compendium",
    base_path: Path,
    formats: tuple[str, ...],
) -> None:
    """Helper to write compendium outputs to disk."""
    unique_formats = sorted(list(set(fmt.lower() for fmt in formats)))

    for fmt in unique_formats:
        if fmt == "okf":
            bundle_dir = base_path.parent / f"{base_path.name}.okf"
            try:
                write_okf_bundle(bundle_dir, compendium.to_okf_bundle())
            except OKFError as exc:
                raise click.ClickException(
                    f"Failed to write OKF bundle: {exc}"
                ) from exc
            click.echo(f"OKF bundle written to {bundle_dir}/")
        elif fmt == "html":
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

            if fmt == "xml":
                target_file.write_text(
                    compendium.to_xml_string(),
                    encoding="utf-8",
                )
            elif fmt == "pdf":
                target_file.write_bytes(compendium.to_pdf_bytes())
            else:
                raise click.ClickException(f"Unsupported output format: {fmt}")

            click.echo(f"Compendium written to {target_file}")


def _base_path_from_state_path(state_path: Path) -> Path:
    name = state_path.name
    if name.endswith(".research.json"):
        return state_path.parent / name.removesuffix(".research.json")
    return state_path.with_suffix("")


if __name__ == "__main__":  # pragma: no cover
    cli()
