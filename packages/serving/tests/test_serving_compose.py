"""Unit tests for serving compose generator and validator."""

from pathlib import Path

from nexcoder_serving.compose import (
    ServingConfig,
    ServingProfile,
    generate_compose_config,
    get_serving_endpoint,
    validate_compose_file,
)


def test_generate_compose_vllm_profile() -> None:
    config = ServingConfig(
        profile=ServingProfile.VLLM,
        model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
        port=8000,
        max_model_len=4096,
        gpu_count="all",
    )
    compose_dict = generate_compose_config(config)

    assert "services" in compose_dict
    assert "vllm" in compose_dict["services"]
    vllm = compose_dict["services"]["vllm"]
    assert vllm["image"] == "vllm/vllm-openai:latest"
    assert "8000:8000" in vllm["ports"]
    assert "--model" in vllm["command"]
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in vllm["command"]


def test_generate_compose_ollama_profile() -> None:
    config = ServingConfig(
        profile=ServingProfile.OLLAMA,
        port=11434,
    )
    compose_dict = generate_compose_config(config)

    assert "services" in compose_dict
    assert "ollama" in compose_dict["services"]
    ollama = compose_dict["services"]["ollama"]
    assert ollama["image"] == "ollama/ollama:latest"
    assert "11434:11434" in ollama["ports"]
    assert "ollama_models" in compose_dict.get("volumes", {})


def test_get_serving_endpoint() -> None:
    assert get_serving_endpoint(ServingProfile.VLLM) == "http://127.0.0.1:8000/v1"
    assert get_serving_endpoint(ServingProfile.OLLAMA) == "http://127.0.0.1:11434/v1"
    assert get_serving_endpoint(ServingProfile.VLLM, host="localhost", port=9000) == "http://localhost:9000/v1"


def test_validate_compose_file(tmp_path: Path) -> None:
    fake_file = tmp_path / "docker-compose.yml"
    fake_file.write_text("services:\n  vllm:\n    image: test\n", encoding="utf-8")
    assert validate_compose_file(fake_file) is True

    non_existent = tmp_path / "nope.yml"
    assert validate_compose_file(non_existent) is False
