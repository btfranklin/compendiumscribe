from datetime import datetime, timezone
from pathlib import Path

import click

from .compendium import Compendium, slugify
from .create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
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
from .research.pricing import resolve_model_pricing
from .skill_output import (
    SkillConfig,
    SkillGenerationError,
    SkillProgress,
    render_skill_folder,
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
    "--format",
    "formats",
    type=click.Choice(
        ["md", "xml", "html", "pdf", "skill"], case_sensitive=False
    ),
    multiple=True,
    default=["md"],
    show_default=True,
    help=(
        "Output format(s). Can be specified multiple times."
    ),
)
def create(
    topic: str,
    output_path: Path | None,
    formats: tuple[str, ...],
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

    skill_config = None
    skill_client = None
    if "skill" in {fmt.lower() for fmt in formats}:
        skill_config = SkillConfig()
        skill_client = client

    _write_outputs(
        compendium,
        base_path,
        formats,
        skill_client=skill_client,
        skill_config=skill_config,
    )
    _echo_cost_summary(cost_tracker)


def _build_cost_tracker(
    *,
    base_path: Path,
    config: ResearchConfig,
) -> CostTracker:
    default_pricing = _resolve_cost_pricing(
        config.research_agent_model
    ) or CostPricing(
        input_per_1m_usd=None,
        output_per_1m_usd=None,
        cached_input_per_1m_usd=None,
        requested_model=config.research_agent_model,
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
            pricing.resolved_model
            or pricing.requested_model
            or "configured-model"
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
        click.echo(
            "Cost report: no usage metrics were captured for this run."
        )
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
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--format",
    "formats",
    type=click.Choice(
        ["md", "xml", "html", "pdf", "skill"], case_sensitive=False
    ),
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

    skill_config = None
    skill_client = None
    if "skill" in {fmt.lower() for fmt in formats}:
        try:
            skill_config = SkillConfig(
                progress_callback=_handle_skill_progress
            )
            skill_client = create_openai_client()
        except MissingAPIKeyError as exc:
            click.echo(f"Configuration error: {exc}", err=True)
            raise SystemExit(1) from exc

    _write_outputs(
        compendium,
        base_path,
        formats,
        skill_client=skill_client,
        skill_config=skill_config,
    )


@cli.command()
@click.option(
    "--input",
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the .research.json sidecar state file.",
)
def recover(input_file: Path):
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
    formats = tuple(state.output_formats or ["md"])
    click.echo(f"Recovering research state for '{title}'...")

    config = ResearchConfig()
    client = None
    cost_tracker: CostTracker | None = None

    try:
        client = create_openai_client(timeout=config.request_timeout_seconds)
        cost_path = (
            Path(state.cost_report_path)
            if state.cost_report_path
            else _base_path_from_state_path(input_file).with_suffix(
                ".costs.json"
            )
        )
        cost_tracker = CostTracker(
            path=cost_path,
            pricing=_resolve_cost_pricing(config.research_agent_model)
            or CostPricing(
                input_per_1m_usd=None,
                output_per_1m_usd=None,
                cached_input_per_1m_usd=None,
                requested_model=config.research_agent_model,
            ),
            pricing_resolver=_resolve_cost_pricing,
        )
        cost_tracker.initialize_report()

        compendium = recover_compendium(
            input_file,
            config=config,
            cost_tracker=cost_tracker,
        )

        click.echo("Research completed! Writing outputs.")

        base_path = _base_path_from_state_path(input_file)

        skill_config = None
        skill_client = None
        if "skill" in {fmt.lower() for fmt in formats}:
            skill_config = SkillConfig(
                progress_callback=_handle_skill_progress
            )
            skill_client = client

        _write_outputs(
            compendium,
            base_path,
            formats,
            skill_client=skill_client,
            skill_config=skill_config,
        )
        _echo_cost_summary(cost_tracker)

    except MissingAPIKeyError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        raise SystemExit(1) from exc
    except DeepResearchError as exc:
        click.echo(str(exc), err=True)
        return
    except Exception as exc:
        click.echo(f"Error during recovery: {exc}", err=True)
        raise SystemExit(1)


def _write_outputs(
    compendium: "Compendium",
    base_path: Path,
    formats: tuple[str, ...],
    *,
    skill_client: object | None = None,
    skill_config: SkillConfig | None = None,
) -> None:
    """Helper to write compendium outputs to disk."""
    unique_formats = sorted(list(set(fmt.lower() for fmt in formats)))
    if "skill" in unique_formats:
        unique_formats.remove("skill")
        unique_formats.append("skill")

    for fmt in unique_formats:
        if fmt == "skill":
            if skill_client is None or skill_config is None:
                raise click.ClickException(
                    "Skill output requires an OpenAI client and config."
                )
            try:
                skill_dir = render_skill_folder(
                    compendium,
                    base_path,
                    skill_client,
                    skill_config,
                )
                click.echo(f"Skill written to {skill_dir}/")
            except SkillGenerationError as exc:
                fallback_file = base_path.with_suffix(".md")
                fallback_file.write_text(
                    compendium.to_markdown(),
                    encoding="utf-8",
                )
                click.echo(
                    (
                        "[!] Skill generation failed after "
                        f"{skill_config.max_retries} attempts: {exc}"
                    ),
                    err=True,
                )
                click.echo(
                    f"Wrote markdown fallback to {fallback_file}",
                    err=True,
                )
                raise SystemExit(1) from exc
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


def _base_path_from_state_path(state_path: Path) -> Path:
    name = state_path.name
    if name.endswith(".research.json"):
        return state_path.parent / name.removesuffix(".research.json")
    return state_path.with_suffix("")


def _handle_skill_progress(update: SkillProgress) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    phase_label = update.phase.replace("_", " ").title()
    status_label = update.status.replace("_", " ").title()
    suffix = ""
    meta = update.metadata or {}
    if (
        meta.get("attempt")
        and meta.get("max_attempts")
        and meta["attempt"] > 1
    ):
        suffix = f" (attempt {meta['attempt']}/{meta['max_attempts']})"
    click.echo(
        f"[{timestamp}] {phase_label}: "
        f"{status_label}. {update.message}{suffix}"
    )


if __name__ == "__main__":  # pragma: no cover
    cli()
