import json
from pathlib import Path

import typer

from app.benchmarks.library import BENCHMARKS
from app.core.evaluation import Evaluator
from app.core.models import EvaluationRequest
from app.reports.export import export

app = typer.Typer(help="Real-calculation, counterexample-driven Excel formula validation")


@app.command()
def benchmarks():
    for benchmark in BENCHMARKS:
        typer.echo(f"{benchmark.id:18} {benchmark.difficulty:10} {benchmark.title}")


@app.command()
def evaluate(
    candidate: str = "=SUM(B2:B5)",
    benchmark: str = "sales_total",
    cases: int = 10,
    seed: int = 42,
    output: Path | None = None,
):
    result = Evaluator().evaluate(
        EvaluationRequest(benchmark=benchmark, candidate=candidate, cases=cases, seed=seed)
    )
    if output:
        data, _ = export(result, output.suffix.lstrip("."))
        output.write_bytes(data)
    typer.echo(
        json.dumps(
            {k: result[k] for k in ("id", "status", "passed", "failed", "counterexample")},
            indent=2,
            default=str,
        )
    )
    if result["status"] not in {"Passed Tested Cases", "Counterexample Found"}:
        raise typer.Exit(2)


@app.command()
def replay(run_id: str):
    result = Evaluator().replay(run_id)
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["reproduced"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
