"""Command-line interface for nexcoder-mlops."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from nexcoder_mlops.dataset.builder import DatasetBuilder, DatasetFormat
from nexcoder_mlops.evaluation.evaluator import ModelEvaluator
from nexcoder_mlops.infra.cost_estimator import estimate_training_cost
from nexcoder_mlops.infra.generator import InfraGenerator
from nexcoder_mlops.infra.gpu_config import CloudProvider, GPUType
from nexcoder_mlops.pipeline.mlops_pipeline import MLOpsPipeline
from nexcoder_mlops.training.config import FineTuneConfig, FineTuneMethod
from nexcoder_mlops.training.engine import ToyOfflineTrainer

app = typer.Typer(help="NexCoder MLOps: Dataset preparation, fine-tuning, tracking, and GPU infrastructure.")
console = Console()


@app.command()
def prepare_dataset(
    output_dir: str = typer.Option("./data", help="Output directory for dataset splits"),
    synthetic_count: int = typer.Option(20, help="Number of synthetic samples if generating"),
    format_type: str = typer.Option("chatml", help="Format: chatml, alpaca, sharegpt, completion"),
) -> None:
    """Generate or prepare a supervised fine-tuning dataset with splits and checksums."""
    builder = DatasetBuilder()
    builder.create_synthetic_dataset(task_name="coding_instructions", count=synthetic_count)
    builder.filter_and_deduplicate()
    builder.anonymize_samples()

    train, val, test = builder.split(train_ratio=0.8, val_ratio=0.1)
    fmt = DatasetFormat(format_type.lower())
    manifest = builder.build_manifest(train, val, test, fmt=fmt)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    DatasetBuilder.export_jsonl(train, out / "train.jsonl", fmt=fmt)
    DatasetBuilder.export_jsonl(val, out / "val.jsonl", fmt=fmt)
    DatasetBuilder.export_jsonl(test, out / "test.jsonl", fmt=fmt)
    (out / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    console.print(f"[bold green]Dataset created successfully in {out}[/bold green]")
    console.print(f"Version: {manifest.version_hash[:12]} | Train: {len(train)} | Val: {len(val)} | Test: {len(test)}")


@app.command()
def train(
    dataset_path: str = typer.Option("./data/train.jsonl", help="Path to training dataset"),
    val_path: str = typer.Option("", help="Optional validation dataset path"),
    base_model: str = typer.Option("Qwen/Qwen2.5-Coder-7B-Instruct", help="Base model identifier"),
    method: str = typer.Option("lora", help="Method: lora, qlora, sft"),
    epochs: int = typer.Option(2, help="Number of training epochs"),
    output_dir: str = typer.Option("./outputs/checkpoints", help="Output checkpoints directory"),
) -> None:
    """Execute a toy offline training loop for local testing or validation."""
    cfg = FineTuneConfig(
        base_model=base_model,
        method=FineTuneMethod(method.lower()),
        dataset_path=dataset_path,
        val_dataset_path=val_path or None,
    )
    cfg.training_args.num_train_epochs = epochs
    cfg.training_args.output_dir = output_dir

    trainer = ToyOfflineTrainer(cfg)
    result = trainer.train()

    console.print(f"[bold green]Training finished with status: {result.status}[/bold green]")
    console.print(f"Run ID: {result.run_id} | Final Loss: {result.final_train_loss:.4f}")
    console.print(f"Artifacts saved to: {result.checkpoint_dir}")


@app.command()
def evaluate(
    test_path: str = typer.Option("./data/test.jsonl", help="Path to test set JSONL"),
    model_name: str = typer.Option("fine-tuned-model", help="Model name or tag"),
) -> None:
    """Evaluate predictions against ground-truth test samples."""
    samples = DatasetBuilder.load_jsonl(test_path)
    if not samples:
        console.print("[yellow]No samples found in test file.[/yellow]")
        return

    predictions = [s.output for s in samples]
    evaluator = ModelEvaluator()
    report = evaluator.evaluate_predictions(samples, predictions, model_name=model_name)

    table = Table(title=f"Evaluation Report: {model_name}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Total Samples", str(report.total_samples))
    table.add_row("Exact Match Rate", f"{report.exact_match_rate * 100:.1f}%")
    table.add_row("Avg Token F1", f"{report.avg_token_f1:.3f}")
    console.print(table)


@app.command()
def estimate_cost(
    tokens: int = typer.Option(500000, help="Estimated total token count"),
    params_b: float = typer.Option(7.0, help="Model parameters in billions"),
    gpu: str = typer.Option("a100_40gb", help="GPU type"),
    provider: str = typer.Option("runpod", help="Cloud provider"),
    epochs: int = typer.Option(3, help="Training epochs"),
    spot: bool = typer.Option(True, help="Whether to use spot instances"),
) -> None:
    """Estimate training duration and compute cost."""
    est = estimate_training_cost(
        total_tokens=tokens,
        param_count_billions=params_b,
        gpu_type=GPUType(gpu.lower()),
        provider=CloudProvider(provider.lower()),
        epochs=epochs,
        is_spot=spot,
    )

    table = Table(title="MLOps Training Cost Estimate")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("GPU Type", est.gpu_type.value)
    table.add_row("Cloud Provider", est.provider.value)
    table.add_row("VRAM Required", f"{est.required_vram_gb:.1f} GB")
    table.add_row("Estimated Duration", f"{est.estimated_duration_hours:.2f} hours")
    table.add_row("Hourly Rate", f"${est.hourly_rate_usd:.2f}/hr")
    table.add_row("Estimated Cost", f"${est.estimated_cost_usd:.4f}")
    console.print(table)


@app.command()
def export_infra(
    output_dir: str = typer.Option("./infra", help="Target directory for infra manifests"),
    base_model: str = typer.Option("Qwen/Qwen2.5-Coder-7B-Instruct", help="Base model"),
    method: str = typer.Option("lora", help="Fine-tuning method"),
    gpu: str = typer.Option("a100_40gb", help="GPU type"),
    provider: str = typer.Option("runpod", help="Cloud provider"),
) -> None:
    """Generate Docker Compose, Kubernetes Job, and script artifacts for GPU training."""
    cfg = FineTuneConfig(base_model=base_model, method=FineTuneMethod(method.lower()))
    artifacts = InfraGenerator.generate_all(
        cfg,
        gpu_type=GPUType(gpu.lower()),
        provider=CloudProvider(provider.lower()),
    )
    InfraGenerator.write_artifacts(artifacts, output_dir)
    console.print(f"[bold green]Infrastructure generated in {output_dir}:[/bold green]")
    for f in artifacts.files:
        console.print(f"- {f.filename} ({f.description})")


@app.command()
def run_pipeline(
    base_model: str = typer.Option("Qwen/Qwen2.5-Coder-7B-Instruct", help="Base model"),
    method: str = typer.Option("lora", help="Fine-tuning method"),
    synthetic_count: int = typer.Option(10, help="Number of synthetic samples"),
    output_dir: str = typer.Option("./outputs/checkpoints", help="Output checkpoints directory"),
) -> None:
    """Run full end-to-end MLOps pipeline offline (dataset, training, eval, tracking, serving)."""
    cfg = FineTuneConfig(base_model=base_model, method=FineTuneMethod(method.lower()))
    cfg.training_args.output_dir = output_dir
    pipeline = MLOpsPipeline()
    result = pipeline.run_pipeline(cfg, synthetic_count=synthetic_count)
    console.print(f"[bold green]{result.summary()}[/bold green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
