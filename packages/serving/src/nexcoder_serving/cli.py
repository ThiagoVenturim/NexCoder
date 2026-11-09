"""CLI entrypoint for faccoder-serving."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from faccoder_serving.compose import ServingConfig, ServingProfile, generate_compose_config

app = typer.Typer(help="faccoder-serving management and evaluation tool")


@app.command()
def compose(
    profile: str = typer.Option("vllm", help="Serving profile: 'vllm' or 'ollama'"),
    output: str = typer.Option("docker-compose.serving.yml", help="Output compose file path"),
    model: str = typer.Option("Qwen/Qwen2.5-Coder-7B-Instruct", help="Model name or HF repository"),
    port: int = typer.Option(8000, help="Container listening port"),
) -> None:
    """Generate a docker-compose.yml file for local model serving."""
    prof = ServingProfile.VLLM if profile.lower() == "vllm" else ServingProfile.OLLAMA
    config = ServingConfig(profile=prof, model_name=model, port=port)
    data = generate_compose_config(config)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    typer.echo(f"Generated compose configuration for profile '{prof.value}' at {out_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
