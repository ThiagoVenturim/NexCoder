"""Tests for Compose, Terraform, Ansible, and HighLevelSpecParser generators."""

import pytest
from nexcoder_iac.catalog import ArchitectureCatalog
from nexcoder_iac.generators.ansible import AnsibleGenerator
from nexcoder_iac.generators.compose import ComposeGenerator
from nexcoder_iac.generators.parser import HighLevelSpecParser
from nexcoder_iac.generators.terraform import TerraformGenerator
from nexcoder_iac.models import ArchitectureTier, DatabaseEngine, IaCTarget, IaCTool


def test_compose_generator_basic():
    spec = ArchitectureCatalog.get("app_database", target=IaCTarget.LOCAL_COMPOSE)
    generator = ComposeGenerator()
    artifacts = generator.generate(spec)

    assert artifacts.target == IaCTarget.LOCAL_COMPOSE
    assert artifacts.tool == IaCTool.COMPOSE
    assert len(artifacts.files) == 3

    compose_file = artifacts.get_file("docker-compose.yml")
    assert compose_file is not None
    assert "version: '3.8'" in compose_file.content or 'version: "3.8"' in compose_file.content
    assert "db:" in compose_file.content
    assert "postgres" in compose_file.content


def test_compose_generator_ai_serving():
    spec = ArchitectureCatalog.get("ai_serving", target=IaCTarget.LOCAL_COMPOSE, profile="vllm")
    generator = ComposeGenerator()
    artifacts = generator.generate(spec)

    compose_file = artifacts.get_file("docker-compose.yml")
    assert compose_file is not None
    assert "vllm" in compose_file.content
    assert "Qwen/Qwen2.5-Coder-7B-Instruct" in compose_file.content


def test_terraform_generator_aws():
    spec = ArchitectureCatalog.get("app_database", target=IaCTarget.AWS, tier=ArchitectureTier.STANDARD)
    generator = TerraformGenerator(tool=IaCTool.TERRAFORM)
    artifacts = generator.generate(spec)

    assert artifacts.target == IaCTarget.AWS
    main_tf = artifacts.get_file("main.tf")
    variables_tf = artifacts.get_file("variables.tf")
    provider_tf = artifacts.get_file("provider.tf")

    assert main_tf is not None
    assert "aws_vpc" in main_tf.content
    assert "aws_instance" in main_tf.content
    assert "aws_db_instance" in main_tf.content

    assert variables_tf is not None
    assert "sensitive   = true" in variables_tf.content

    assert provider_tf is not None
    assert "hashicorp/aws" in provider_tf.content


def test_terraform_generator_digitalocean():
    spec = ArchitectureCatalog.get("app_database", target=IaCTarget.DIGITALOCEAN)
    generator = TerraformGenerator()
    artifacts = generator.generate(spec)

    main_tf = artifacts.get_file("main.tf")
    assert main_tf is not None
    assert "digitalocean_droplet" in main_tf.content
    assert "digitalocean_database_cluster" in main_tf.content


def test_terraform_generator_hetzner():
    spec = ArchitectureCatalog.get("simple_app", target=IaCTarget.HETZNER)
    generator = TerraformGenerator()
    artifacts = generator.generate(spec)

    main_tf = artifacts.get_file("main.tf")
    assert main_tf is not None
    assert "hcloud_server" in main_tf.content
    assert "hcloud_firewall" in main_tf.content


def test_terraform_generator_gcp():
    spec = ArchitectureCatalog.get("simple_app", target=IaCTarget.GCP)
    generator = TerraformGenerator()
    artifacts = generator.generate(spec)

    main_tf = artifacts.get_file("main.tf")
    assert main_tf is not None
    assert "google_compute_instance" in main_tf.content


def test_terraform_generator_azure():
    spec = ArchitectureCatalog.get("simple_app", target=IaCTarget.AZURE)
    generator = TerraformGenerator()
    artifacts = generator.generate(spec)

    main_tf = artifacts.get_file("main.tf")
    assert main_tf is not None
    assert "azurerm_resource_group" in main_tf.content
    assert "azurerm_virtual_network" in main_tf.content


def test_terraform_unsupported_target():
    spec = ArchitectureCatalog.get("simple_app", target=IaCTarget.LOCAL_COMPOSE)
    generator = TerraformGenerator()
    with pytest.raises(ValueError, match="Terraform generator does not support target"):
        generator.generate(spec)


def test_ansible_generator():
    spec = ArchitectureCatalog.get("simple_app", target=IaCTarget.VM)
    generator = AnsibleGenerator()
    artifacts = generator.generate(spec)

    assert artifacts.tool == IaCTool.ANSIBLE
    playbook = artifacts.get_file("playbook.yml")
    inventory = artifacts.get_file("inventory.ini")

    assert playbook is not None
    assert "docker" in playbook.content
    assert "ufw" in playbook.content

    assert inventory is not None
    assert "app_servers" in inventory.content


def test_high_level_spec_parser_portuguese():
    prompt = "Quero subir esta app Python com Postgres e nginx na AWS"
    spec = HighLevelSpecParser.parse(prompt)

    assert spec.target == IaCTarget.AWS
    assert spec.database is not None
    assert spec.database.engine == DatabaseEngine.POSTGRES
    assert spec.load_balancer is True
    assert spec.tier == ArchitectureTier.STANDARD


def test_high_level_spec_parser_with_queue():
    prompt = "App nodejs com redis, worker celery e postgres no hetzner para producao"
    spec = HighLevelSpecParser.parse(prompt)

    assert spec.target == IaCTarget.HETZNER
    assert spec.tier == ArchitectureTier.PRODUCTION
    assert spec.cache is True
    assert spec.queue_worker is True
    assert len(spec.services) == 2
