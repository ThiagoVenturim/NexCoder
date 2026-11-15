"""Ansible playbook and role generator for VM-based provisioning."""

from __future__ import annotations

import yaml

from nexcoder_iac.credentials import generate_env_example, get_required_env_vars, scan_for_secrets
from nexcoder_iac.generators.base import BaseGenerator
from nexcoder_iac.models import (
    ArchitectureSpec,
    GeneratedFile,
    IaCArtifacts,
    IaCTarget,
    IaCTool,
)
from nexcoder_iac.pricing import estimate_monthly_cost


class AnsibleGenerator(BaseGenerator):
    """Generates Ansible playbooks, tasks, and inventories for VM configuration."""

    def generate(self, spec: ArchitectureSpec) -> IaCArtifacts:
        # 1. Main playbook
        playbook_data = [
            {
                "name": f"Configure server for {spec.name}",
                "hosts": "app_servers",
                "become": True,
                "tasks": [
                    {
                        "name": "Update apt cache and install base packages",
                        "apt": {
                            "update_cache": True,
                            "name": ["apt-transport-https", "ca-certificates", "curl", "gnupg", "ufw"],
                            "state": "present",
                        },
                    },
                    {
                        "name": "Ensure Docker service is installed and running",
                        "apt": {
                            "name": ["docker.io", "docker-compose-v2"],
                            "state": "present",
                        },
                    },
                    {
                        "name": "Ensure Docker service is active and enabled",
                        "service": {
                            "name": "docker",
                            "state": "started",
                            "enabled": True,
                        },
                    },
                    {
                        "name": "Configure firewall to allow SSH",
                        "ufw": {
                            "rule": "allow",
                            "port": "22",
                            "proto": "tcp",
                        },
                    },
                    {
                        "name": "Configure firewall to allow HTTP traffic",
                        "ufw": {
                            "rule": "allow",
                            "port": "80",
                            "proto": "tcp",
                        },
                    },
                    {
                        "name": "Enable UFW firewall",
                        "ufw": {
                            "state": "enabled",
                        },
                    },
                    {
                        "name": f"Create deployment directory /opt/{spec.name}",
                        "file": {
                            "path": f"/opt/{spec.name}",
                            "state": "directory",
                            "mode": "0755",
                        },
                    },
                ],
            }
        ]

        playbook_yaml = yaml.dump(playbook_data, sort_keys=False, default_flow_style=False)

        # 2. Inventory file
        inventory_ini = (
            "# Ansible inventory file\n"
            "# Replace SERVER_HOST with your target machine IP or hostname\n\n"
            "[app_servers]\n"
            "target_server ansible_host={{ lookup('env', 'SERVER_HOST') | default('127.0.0.1', true) }} "
            "ansible_user={{ lookup('env', 'SSH_USER') | default('ubuntu', true) }} "
            "ansible_ssh_private_key_file="
            "{{ lookup('env', 'SSH_PRIVATE_KEY_PATH') | default('~/.ssh/id_rsa', true) }}\n"
        )

        instructions = (
            f"# Ansible Provisioning Guide for {spec.name}\n\n"
            "## 1. Supply Host Credentials\n"
            "```bash\n"
            "export SERVER_HOST=203.0.113.10\n"
            "export SSH_USER=ubuntu\n"
            "export SSH_PRIVATE_KEY_PATH=~/.ssh/my_key.pem\n"
            "```\n\n"
            "## 2. Check Connection (Dry-Run Ping)\n"
            "```bash\n"
            "ansible -i inventory.ini app_servers -m ping\n"
            "```\n\n"
            "## 3. Run Playbook (Provision Server)\n"
            "```bash\n"
            "ansible-playbook -i inventory.ini playbook.yml\n"
            "```\n"
        )

        env_example = generate_env_example(IaCTarget.VM, spec)

        files = [
            GeneratedFile(
                filename="playbook.yml",
                content=playbook_yaml,
                file_type="yaml",
                description="Ansible server configuration playbook",
            ),
            GeneratedFile(
                filename="inventory.ini",
                content=inventory_ini,
                file_type="ini",
                description="Ansible inventory using environment variables for host access",
            ),
            GeneratedFile(
                filename=".env.example",
                content=env_example,
                file_type="env",
                description="Environment variable template for server access",
            ),
            GeneratedFile(
                filename="README.md",
                content=instructions,
                file_type="markdown",
                description="Ansible execution guide",
            ),
        ]

        # Scan for accidental secrets
        for f in files:
            findings = scan_for_secrets(f.content)
            if findings:
                raise ValueError(f"Secret detected in generated file {f.filename}: {findings}")

        monthly_cost = estimate_monthly_cost(spec)
        return IaCArtifacts(
            spec=spec,
            target=IaCTarget.VM,
            tool=IaCTool.ANSIBLE,
            files=files,
            instructions=instructions,
            required_env_vars=get_required_env_vars(IaCTarget.VM),
            estimated_monthly_cost_usd=monthly_cost,
        )
