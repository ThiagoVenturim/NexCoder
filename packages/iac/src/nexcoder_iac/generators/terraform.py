"""Terraform and OpenTofu IaC generator for cloud and VM deployment targets."""

from __future__ import annotations

from nexcoder_iac.credentials import generate_env_example, get_required_env_vars, scan_for_secrets
from nexcoder_iac.generators.base import BaseGenerator
from nexcoder_iac.models import (
    ArchitectureSpec,
    ArchitectureTier,
    DatabaseEngine,
    GeneratedFile,
    IaCArtifacts,
    IaCTarget,
    IaCTool,
)
from nexcoder_iac.pricing import estimate_monthly_cost


class TerraformGenerator(BaseGenerator):
    """Generates production-grade Terraform / OpenTofu configurations."""

    def __init__(self, tool: IaCTool = IaCTool.TERRAFORM) -> None:
        self.tool = tool

    def generate(self, spec: ArchitectureSpec) -> IaCArtifacts:
        target = spec.target
        if target == IaCTarget.AWS:
            files = self._generate_aws(spec)
        elif target == IaCTarget.DIGITALOCEAN:
            files = self._generate_digitalocean(spec)
        elif target == IaCTarget.HETZNER:
            files = self._generate_hetzner(spec)
        elif target == IaCTarget.GCP:
            files = self._generate_gcp(spec)
        elif target == IaCTarget.AZURE:
            files = self._generate_azure(spec)
        elif target == IaCTarget.VM:
            files = self._generate_generic_vm(spec)
        else:
            raise ValueError(f"Terraform generator does not support target '{target.value}'. Use ComposeGenerator.")

        instructions = self._generate_instructions(spec)
        env_example = generate_env_example(target, spec)

        all_files = [
            *files,
            GeneratedFile(
                filename=".env.example",
                content=env_example,
                file_type="env",
                description="Sample environment credentials file",
            ),
            GeneratedFile(
                filename="README.md",
                content=instructions,
                file_type="markdown",
                description="Deployment instructions and credential usage guide",
            ),
        ]

        # Scan for inadvertent secrets
        for f in all_files:
            findings = scan_for_secrets(f.content)
            if findings:
                raise ValueError(f"Secret detected in generated file {f.filename}: {findings}")

        monthly_cost = estimate_monthly_cost(spec)
        return IaCArtifacts(
            spec=spec,
            target=target,
            tool=self.tool,
            files=all_files,
            instructions=instructions,
            required_env_vars=get_required_env_vars(target),
            estimated_monthly_cost_usd=monthly_cost,
        )

    def _generate_aws(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        app_name = spec.name.replace("-", "_")
        instance_type = (
            "t4g.small"
            if spec.tier == ArchitectureTier.STARTER
            else ("t4g.medium" if spec.tier == ArchitectureTier.STANDARD else "t4g.xlarge")
        )
        rds_class = (
            "db.t4g.micro"
            if spec.tier == ArchitectureTier.STARTER
            else ("db.t4g.small" if spec.tier == ArchitectureTier.STANDARD else "db.t4g.medium")
        )

        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
"""

        variables_tf = f"""variable "aws_region" {{
  description = "Target AWS Region"
  type        = string
  default     = "us-east-1"
}}

variable "environment" {{
  description = "Deployment environment"
  type        = string
  default     = "{spec.tier.value}"
}}

variable "instance_type" {{
  description = "EC2 instance type for application servers"
  type        = string
  default     = "{instance_type}"
}}
"""
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            variables_tf += """
variable "db_username" {
  description = "Database administrator username"
  type        = string
  default     = "appuser"
}

variable "db_password" {
  description = "Database administrator password"
  type        = string
  sensitive   = true
}
"""

        main_tf = f"""# VPC and Networking
resource "aws_vpc" "{app_name}_vpc" {{
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {{
    Name        = "{spec.name}-vpc"
    Environment = var.environment
  }}
}}

resource "aws_subnet" "{app_name}_subnet_public_1" {{
  vpc_id            = aws_vpc.{app_name}_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${{var.aws_region}}a"
  map_public_ip_on_launch = true

  tags = {{
    Name = "{spec.name}-public-1"
  }}
}}

resource "aws_subnet" "{app_name}_subnet_public_2" {{
  vpc_id            = aws_vpc.{app_name}_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${{var.aws_region}}b"
  map_public_ip_on_launch = true

  tags = {{
    Name = "{spec.name}-public-2"
  }}
}}

resource "aws_internet_gateway" "{app_name}_igw" {{
  vpc_id = aws_vpc.{app_name}_vpc.id

  tags = {{
    Name = "{spec.name}-igw"
  }}
}}

resource "aws_route_table" "{app_name}_rt" {{
  vpc_id = aws_vpc.{app_name}_vpc.id

  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.{app_name}_igw.id
  }}
}}

resource "aws_route_table_association" "{app_name}_rta_1" {{
  subnet_id      = aws_subnet.{app_name}_subnet_public_1.id
  route_table_id = aws_route_table.{app_name}_rt.id
}}

resource "aws_security_group" "{app_name}_sg" {{
  name        = "{spec.name}-sg"
  description = "Allow inbound web traffic"
  vpc_id      = aws_vpc.{app_name}_vpc.id

  ingress {{
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  ingress {{
    description = "App Port"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}

resource "aws_instance" "{app_name}_app" {{
  ami           = "ami-0c7217cdde317cfec" # Amazon Linux 2023 ARM/x86 base
  instance_type = var.instance_type
  subnet_id     = aws_subnet.{app_name}_subnet_public_1.id
  vpc_security_group_ids = [aws_security_group.{app_name}_sg.id]

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y docker
              systemctl start docker
              systemctl enable docker
              EOF

  tags = {{
    Name        = "{spec.name}-server"
    Environment = var.environment
  }}
}}
"""
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            main_tf += f"""
# Managed Relational Database (RDS)
resource "aws_db_subnet_group" "{app_name}_db_subnet" {{
  name       = "{spec.name}-db-subnet-group"
  subnet_ids = [
    aws_subnet.{app_name}_subnet_public_1.id,
    aws_subnet.{app_name}_subnet_public_2.id
  ]
}}

resource "aws_db_instance" "{app_name}_database" {{
  identifier             = "{spec.name}-db"
  allocated_storage      = {spec.database.storage_gb}
  engine                 = "{spec.database.engine.value}"
  engine_version         = "{spec.database.version}"
  instance_class         = "{rds_class}"
  db_name                = "{spec.database.database_name}"
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.{app_name}_db_subnet.name
  vpc_security_group_ids = [aws_security_group.{app_name}_sg.id]
  skip_final_snapshot    = true
}}
"""

        outputs_tf = f"""output "app_public_ip" {{
  description = "Public IP of the application server"
  value       = aws_instance.{app_name}_app.public_ip
}}

output "app_public_dns" {{
  description = "Public DNS of the application server"
  value       = aws_instance.{app_name}_app.public_dns
}}
"""
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            outputs_tf += f"""
output "database_endpoint" {{
  description = "Endpoint address of the managed database"
  value       = aws_db_instance.{app_name}_database.endpoint
}}
"""

        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_digitalocean(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        app_name = spec.name.replace("-", "_")
        size = (
            "s-1vcpu-1gb"
            if spec.tier == ArchitectureTier.STARTER
            else ("s-2vcpu-4gb" if spec.tier == ArchitectureTier.STANDARD else "g-2vcpu-8gb")
        )

        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.30"
    }
  }
}

provider "digitalocean" {
  token = var.do_token
}
"""

        variables_tf = f"""variable "do_token" {{
  description = "DigitalOcean Personal Access Token"
  type        = string
  sensitive   = true
}}

variable "region" {{
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}}

variable "droplet_size" {{
  description = "Droplet instance size"
  type        = string
  default     = "{size}"
}}
"""
        main_tf = f"""resource "digitalocean_vpc" "{app_name}_vpc" {{
  name   = "{spec.name}-vpc"
  region = var.region
}}

resource "digitalocean_droplet" "{app_name}_web" {{
  name     = "{spec.name}-web"
  image    = "docker-20-04"
  region   = var.region
  size     = var.droplet_size
  vpc_uuid = digitalocean_vpc.{app_name}_vpc.id

  tags = ["{spec.name}", "{spec.tier.value}"]
}}

resource "digitalocean_firewall" "{app_name}_firewall" {{
  name        = "{spec.name}-firewall"
  droplet_ids = [digitalocean_droplet.{app_name}_web.id]

  inbound_rule {{
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }}

  inbound_rule {{
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }}

  inbound_rule {{
    protocol         = "tcp"
    port_range       = "8000"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }}

  outbound_rule {{
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }}
}}
"""
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            main_tf += f"""
resource "digitalocean_database_cluster" "{app_name}_db" {{
  name       = "{spec.name}-db"
  engine     = "{'pg' if spec.database.engine == DatabaseEngine.POSTGRES else 'mysql'}"
  version    = "{spec.database.version}"
  size       = "db-s-1vcpu-1gb"
  region     = var.region
  node_count = 1
}}
"""

        outputs_tf = f"""output "droplet_ip" {{
  description = "Public IP address of the DigitalOcean Droplet"
  value       = digitalocean_droplet.{app_name}_web.ipv4_address
}}
"""
        if spec.database and spec.database.engine != DatabaseEngine.NONE:
            outputs_tf += f"""
output "database_uri" {{
  description = "Managed Database Connection URI"
  value       = digitalocean_database_cluster.{app_name}_db.uri
  sensitive   = true
}}
"""

        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_hetzner(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        app_name = spec.name.replace("-", "_")
        server_type = (
            "cx22"
            if spec.tier == ArchitectureTier.STARTER
            else ("cpx31" if spec.tier == ArchitectureTier.STANDARD else "cpx41")
        )

        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}
"""

        variables_tf = f"""variable "hcloud_token" {{
  description = "Hetzner Cloud API Token"
  type        = string
  sensitive   = true
}}

variable "server_type" {{
  description = "Hetzner Cloud server type"
  type        = string
  default     = "{server_type}"
}}

variable "location" {{
  description = "Datacenter location (fsn1, nbg1, hel1, ash)"
  type        = string
  default     = "fsn1"
}}
"""

        main_tf = f"""resource "hcloud_network" "{app_name}_net" {{
  name     = "{spec.name}-net"
  ip_range = "10.0.0.0/16"
}}

resource "hcloud_network_subnet" "{app_name}_subnet" {{
  network_id   = hcloud_network.{app_name}_net.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = "10.0.1.0/24"
}}

resource "hcloud_firewall" "{app_name}_firewall" {{
  name = "{spec.name}-firewall"

  rule {{
    direction = "in"
    port      = "22"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }}

  rule {{
    direction = "in"
    port      = "80"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }}

  rule {{
    direction = "in"
    port      = "8000"
    protocol  = "tcp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }}
}}

resource "hcloud_server" "{app_name}_server" {{
  name        = "{spec.name}-server"
  image       = "ubuntu-24.04"
  server_type = var.server_type
  location    = var.location
  firewall_ids = [hcloud_firewall.{app_name}_firewall.id]

  user_data = <<-EOF
              #!/bin/bash
              apt-get update
              apt-get install -y docker.io docker-compose-plugin
              systemctl start docker
              systemctl enable docker
              EOF
}}
"""

        outputs_tf = f"""output "server_ipv4" {{
  description = "Public IPv4 address of the Hetzner Cloud server"
  value       = hcloud_server.{app_name}_server.ipv4_address
}}
"""

        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_gcp(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        app_name = spec.name.replace("-", "_")
        machine_type = (
            "e2-small"
            if spec.tier == ArchitectureTier.STARTER
            else ("e2-medium" if spec.tier == ArchitectureTier.STANDARD else "e2-standard-4")
        )

        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}
"""

        variables_tf = f"""variable "gcp_project_id" {{
  description = "Google Cloud Project ID"
  type        = string
}}

variable "gcp_region" {{
  description = "Target GCP Region"
  type        = string
  default     = "us-central1"
}}

variable "machine_type" {{
  description = "GCP Compute Engine machine type"
  type        = string
  default     = "{machine_type}"
}}
"""

        main_tf = f"""resource "google_compute_network" "{app_name}_vpc" {{
  name                    = "{spec.name}-vpc"
  auto_create_subnetworks = true
}}

resource "google_compute_firewall" "{app_name}_fw_http" {{
  name    = "{spec.name}-allow-http"
  network = google_compute_network.{app_name}_vpc.name

  allow {{
    protocol = "tcp"
    ports    = ["80", "8000"]
  }}

  source_ranges = ["0.0.0.0/0"]
}}

resource "google_compute_instance" "{app_name}_vm" {{
  name         = "{spec.name}-vm"
  machine_type = var.machine_type
  zone         = "${{var.gcp_region}}-a"

  boot_disk {{
    initialize_params {{
      image = "cos-cloud/cos-stable"
    }}
  }}

  network_interface {{
    network = google_compute_network.{app_name}_vpc.name
    access_config {{
      # Ephemeral public IP
    }}
  }}
}}
"""

        outputs_tf = f"""output "vm_external_ip" {{
  description = "External IP address of the GCP Compute Engine instance"
  value       = google_compute_instance.{app_name}_vm.network_interface[0].access_config[0].nat_ip
}}
"""

        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_azure(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        app_name = spec.name.replace("-", "_")
        vm_size = (
            "Standard_B1s"
            if spec.tier == ArchitectureTier.STARTER
            else ("Standard_B2s" if spec.tier == ArchitectureTier.STANDARD else "Standard_D2s_v5")
        )

        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}
"""

        variables_tf = f"""variable "azure_location" {{
  description = "Azure region location"
  type        = string
  default     = "eastus"
}}

variable "vm_size" {{
  description = "Virtual Machine SKU"
  type        = string
  default     = "{vm_size}"
}}

variable "admin_username" {{
  description = "VM Administrator username"
  type        = string
  default     = "azureuser"
}}
"""

        main_tf = f"""resource "azurerm_resource_group" "{app_name}_rg" {{
  name     = "{spec.name}-rg"
  location = var.azure_location
}}

resource "azurerm_virtual_network" "{app_name}_vnet" {{
  name                = "{spec.name}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.{app_name}_rg.location
  resource_group_name = azurerm_resource_group.{app_name}_rg.name
}}

resource "azurerm_subnet" "{app_name}_subnet" {{
  name                 = "{spec.name}-subnet"
  resource_group_name  = azurerm_resource_group.{app_name}_rg.name
  virtual_network_name = azurerm_virtual_network.{app_name}_vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}}

resource "azurerm_public_ip" "{app_name}_pip" {{
  name                = "{spec.name}-pip"
  location            = azurerm_resource_group.{app_name}_rg.location
  resource_group_name = azurerm_resource_group.{app_name}_rg.name
  allocation_method   = "Static"
}}

resource "azurerm_network_interface" "{app_name}_nic" {{
  name                = "{spec.name}-nic"
  location            = azurerm_resource_group.{app_name}_rg.location
  resource_group_name = azurerm_resource_group.{app_name}_rg.name

  ip_configuration {{
    name                          = "internal"
    subnet_id                     = azurerm_subnet.{app_name}_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.{app_name}_pip.id
  }}
}}
"""

        outputs_tf = f"""output "public_ip_address" {{
  description = "Public IP address of the Azure VM"
  value       = azurerm_public_ip.{app_name}_pip.ip_address
}}
"""

        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_generic_vm(self, spec: ArchitectureSpec) -> list[GeneratedFile]:
        # VM target using cloud-init / null_resource or local executor
        app_name = spec.name.replace("-", "_")
        provider_tf = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}
"""
        variables_tf = """variable "server_host" {
  description = "Target server IP address or hostname"
  type        = string
}

variable "ssh_user" {
  description = "SSH username for remote provisioning"
  type        = string
  default     = "ubuntu"
}
"""
        main_tf = f"""resource "local_file" "{app_name}_inventory" {{
  content  = "[app_servers]\\n${{var.server_host}} ansible_user=${{var.ssh_user}}\\n"
  filename = "${{path.module}}/hosts.ini"
}}
"""
        outputs_tf = """output "inventory_file" {
  description = "Path to generated Ansible inventory file"
  value       = local_file.app_inventory.filename
}
"""
        return [
            GeneratedFile(filename="provider.tf", content=provider_tf, file_type="hcl"),
            GeneratedFile(filename="variables.tf", content=variables_tf, file_type="hcl"),
            GeneratedFile(filename="main.tf", content=main_tf, file_type="hcl"),
            GeneratedFile(filename="outputs.tf", content=outputs_tf, file_type="hcl"),
        ]

    def _generate_instructions(self, spec: ArchitectureSpec) -> str:
        tool_cmd = "tofu" if self.tool == IaCTool.OPENTOFU else "terraform"
        target_name = spec.target.value.upper()
        return (
            f"# Infrastructure Deployment Guide for {spec.name} ({target_name})\n\n"
            f"This directory contains {self.tool.value.title()} code to provision {spec.name}.\n\n"
            "## 1. Prerequisites\n"
            "- Install Terraform (>= 1.5.0) or OpenTofu (>= 1.6.0)\n"
            f"- Have your own {target_name} account credentials ready.\n\n"
            "## 2. Supply Your Credentials\n"
            "Copy the sample file and supply your real secret credentials in your shell or `.env`:\n\n"
            "```bash\n"
            "cp .env.example .env\n"
            "# Export your credentials into your shell session:\n"
            "export $(cat .env | grep -v '^#' | xargs)\n"
            "```\n\n"
            "## 3. Initialize Provider Plugins\n"
            "```bash\n"
            f"{tool_cmd} init\n"
            "```\n\n"
            "## 4. Preview Plan (Dry-Run)\n"
            "```bash\n"
            f"{tool_cmd} plan\n"
            "```\n\n"
            "## 5. Apply (Provision Infrastructure)\n"
            "```bash\n"
            f"{tool_cmd} apply\n"
            "```\n\n"
            "## 6. Teardown / Destroy\n"
            "```bash\n"
            f"{tool_cmd} destroy\n"
            "```\n"
        )
