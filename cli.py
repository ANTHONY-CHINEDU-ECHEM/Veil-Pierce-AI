"""Command line interface.

Usage: veilpierce COMMAND [ARGUMENT] [section.key=value ...]

Commands
    benchmark     generate data, run everything, evaluate, draw figures
    generate      generate the synthetic registry only
    export        write the registry in the public source layouts
    build         run resolution, graph and detection and save artefacts
    figures       redraw all figures from saved artefacts
    docs          regenerate the mitigation matrix and typology documents
    samples       rewrite the sample dossiers from saved artefacts
    investigate   print and save the dossier for one company number
    ask           answer a free text question about a company
    search        find entities by name
    top           list the highest risk companies
    serve         start the HTTP service

Any setting can be overridden as section.key=value, for example
veilpierce benchmark synth.n_companies=50000 synth.seed=3
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import Settings, load_settings, project_root
from .logging_utils import StageTimer, get_logger

log = get_logger("veilpierce.cli")
SAMPLE_QUESTIONS = ("Who ultimately controls {name}?", "Is there any sanctions exposure for company {number}?", "What do we know about the registered address of {number}?")


def _split(argv: list[str]) -> tuple[list[str], list[str], dict[str, str]]:
    """Separate positional arguments, setting overrides and command options."""
    positional, overrides, options = [], [], {}
    for item in argv:
        head = item.split("=", 1)[0]
        if "=" in item and "." in head and " " not in head:
            overrides.append(item)
        elif "=" in item and " " not in head and head.isidentifier():
            if hasattr(Settings(), head):
                overrides.append(item)
            else:
                options[head] = item.split("=", 1)[1]
        else:
            positional.append(item)
    return positional, overrides, options


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def _peak_memory_gb() -> float:
    """Peak resident memory of this process, or zero where it cannot be read."""
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1_048_576, 2)
    except (ImportError, ValueError):
        return 0.0


def _write_samples(investigator, example_cases: dict, settings: Settings) -> dict:
    """Write one sample dossier per example case and a file of sample questions.

    The samples sit beside the figure folder, so a run that redirects its
    figures elsewhere does not overwrite the committed samples.
    """
    from .rag.report import write_dossier

    samples = settings.path("figure_dir").parent / "sample_dossiers"
    root = samples.parent.parent
    written, questions = {}, []
    for kind, case in example_cases.items():
        number = case.get("company_number")
        if not number:
            continue
        dossier = investigator.investigate(number)
        written[kind] = str(write_dossier(dossier, samples, stem=f"dossier_{kind}").relative_to(root))
        for template in SAMPLE_QUESTIONS[:2]:
            questions.append(investigator.ask(template.format(name=dossier.case.company_name, number=number)).to_dict())
    _write_json(samples / "sample_questions.json", {"questions": questions})
    return written


def cmd_samples(settings: Settings, args: list[str], options: dict) -> int:
    """Rewrite the sample dossiers from saved artefacts."""
    runtime = _runtime(settings)
    cases = runtime.metrics.get("example_cases")
    if not cases:
        print("no example cases found in the artefact folder; run the benchmark command first")
        return 2
    for kind, path in _write_samples(runtime.investigator, cases, settings).items():
        print(f"{kind}: {path}")
    return 0


def cmd_generate(settings: Settings, args: list[str], options: dict) -> int:
    from .pipeline import obtain_registry

    registry = obtain_registry(settings, StageTimer(), regenerate=True)
    print(json.dumps(registry.summary(), indent=2))
    return 0


def cmd_export(settings: Settings, args: list[str], options: dict) -> int:
    from .data.loaders import export_official_layout
    from .pipeline import obtain_registry

    target = Path(options.get("to", settings.path("data_dir") / "official_layout"))
    export_official_layout(obtain_registry(settings, StageTimer()), target)
    print(f"public source layouts written to {target}")
    return 0


def _registry_for(settings: Settings, options: dict, timer: StageTimer):
    from .pipeline import obtain_registry

    if "source" in options:
        from .data.loaders import load_official_directory

        with timer.stage("load public source files"):
            return load_official_directory(options["source"], snapshot=options.get("snapshot"))
    return obtain_registry(settings, timer)


def cmd_build(settings: Settings, args: list[str], options: dict) -> int:
    from .pipeline import build_entity_index, run_pipeline, save_artifacts

    timer = StageTimer()
    registry = _registry_for(settings, options, timer)
    state = run_pipeline(settings, registry, train_model=False, timer=timer)
    with timer.stage("name index"):
        index = build_entity_index(state.graph, settings)
    with timer.stage("save artefacts"):
        root = save_artifacts(state, index)
    print(f"artefacts written to {root} in {timer.total():.0f} seconds")
    return 0


def cmd_benchmark(settings: Settings, args: list[str], options: dict) -> int:
    from .evaluation.evaluate import evaluate_all
    from .evaluation.figures import case_figures, chart_figures
    from .pipeline import build_entity_index, build_investigator, obtain_registry, run_pipeline, save_artifacts
    timer = StageTimer()
    registry = obtain_registry(settings, timer)
    state = run_pipeline(settings, registry, train_model=True, timer=timer)
    with timer.stage("name index"):
        index = build_entity_index(state.graph, settings)
    investigator = build_investigator(state, index)
    metrics = evaluate_all(state, investigator, index)
    figure_dir = settings.path("figure_dir")
    with timer.stage("figures"):
        chart_figures(metrics, figure_dir)
        metrics["example_cases"] = case_figures(state, figure_dir)
    with timer.stage("sample dossiers"):
        metrics["sample_dossiers"] = _write_samples(investigator, metrics["example_cases"], settings)
    metrics["runtime_seconds"] = dict(timer.seconds) | {"total": timer.total()}
    metrics["peak_memory_gb"] = _peak_memory_gb()
    report_dir = settings.path("report_dir")
    _write_json(report_dir / "metrics.json", metrics)
    with timer.stage("save artefacts"):
        save_artifacts(state, index, metrics)
    fused = metrics["detection"]["fused_at_threshold"]
    print(
        f"benchmark complete in {timer.total():.0f} seconds: {metrics['dataset']['total_records']:,} records, "
        f"precision {fused['precision']:.3f} and recall {fused['recall']:.3f} at the alert threshold. Results in {report_dir / 'metrics.json'}"
    )
    return 0


def _runtime(settings: Settings):
    from .pipeline import load_runtime

    return load_runtime(settings)


def cmd_figures(settings: Settings, args: list[str], options: dict) -> int:
    """Redraw every figure from the saved artefacts without rerunning the pipeline."""
    from .evaluation.figures import case_figures, chart_figures

    runtime = _runtime(settings)
    if not runtime.metrics:
        print("no metrics found in the artefact folder; run the benchmark command first")
        return 2
    made = chart_figures(runtime.metrics, settings.path("figure_dir"))
    case_figures(runtime, settings.path("figure_dir"))
    print(f"{len(made)} charts and the case pictures written to {settings.path('figure_dir')}")
    return 0


def cmd_docs(settings: Settings, args: list[str], options: dict) -> int:
    """Regenerate the knowledge documents from the packaged JSON files."""
    from .docgen import write_docs

    metrics = None
    report = settings.path("report_dir") / "metrics.json"
    if report.exists():
        with open(report, "r", encoding="utf8") as handle:
            metrics = json.load(handle)
    for path in write_docs(project_root() / "docs", metrics):
        print(f"wrote {path}")
    return 0


def cmd_investigate(settings: Settings, args: list[str], options: dict) -> int:
    from .rag.report import dossier_markdown, write_dossier

    if not args:
        print("give a company number, for example: veilpierce investigate 09123456")
        return 2
    runtime = _runtime(settings)
    dossier = runtime.investigator.investigate(args[0])
    path = write_dossier(dossier, settings.path("report_dir") / "dossiers")
    print(dossier_markdown(dossier))
    print(f"\nsaved to {path}")
    return 0


def cmd_ask(settings: Settings, args: list[str], options: dict) -> int:
    if not args:
        print('give a question in quotes, for example: veilpierce ask "Who controls NORTHGATE FREIGHT SOLUTIONS LTD?"')
        return 2
    answer = _runtime(settings).investigator.ask(" ".join(args))
    print(json.dumps(answer.to_dict(), indent=2))
    return 0


def cmd_search(settings: Settings, args: list[str], options: dict) -> int:
    if not args:
        print("give a name to search for")
        return 2
    hits = _runtime(settings).entity_index.search(" ".join(args), k=int(options.get("k", 8)), kind=options.get("kind"))
    print(json.dumps(hits, indent=2))
    return 0


def cmd_top(settings: Settings, args: list[str], options: dict) -> int:
    cf = _runtime(settings).detection.companies
    best = cf.sort_values("risk_rules", ascending=False).head(int(options.get("limit", 20)))
    for row in best.itertuples(index=False):
        print(f"{row.company_number}  {row.risk_rules:.2f}  {row.risk_band:8s}  {row.company_name}")
    return 0


def cmd_serve(settings: Settings, args: list[str], options: dict) -> int:
    import uvicorn

    from .api.app import create_app

    uvicorn.run(create_app(_runtime(settings)), host=options.get("host", "127.0.0.1"), port=int(options.get("port", 8000)))
    return 0


COMMANDS = {
    "benchmark": cmd_benchmark,
    "generate": cmd_generate,
    "export": cmd_export,
    "build": cmd_build,
    "figures": cmd_figures,
    "docs": cmd_docs,
    "samples": cmd_samples,
    "investigate": cmd_investigate,
    "ask": cmd_ask,
    "search": cmd_search,
    "top": cmd_top,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("help", "h", "?") or argv[0] not in COMMANDS:
        print(__doc__)
        return 0 if argv and argv[0] in ("help", "h", "?") else 2
    positional, overrides, options = _split(argv[1:])
    config = options.pop("config", None)
    settings = load_settings(config, overrides)
    return COMMANDS[argv[0]](settings, positional, options)


if __name__ == "__main__":
    raise SystemExit(main())
