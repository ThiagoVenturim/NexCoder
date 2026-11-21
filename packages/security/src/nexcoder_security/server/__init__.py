"""Server exposure, Nginx reverse proxy, hardening, privatization, and PII masking."""

from nexcoder_security.server.audit import audit_server_action
from nexcoder_security.server.hardening import (
    HardeningCheckItem,
    HardeningOptions,
    HardeningProfile,
    HardeningResult,
    ServerHardeningEngine,
    generate_bash_hardening_script,
    generate_ps1_hardening_script,
)
from nexcoder_security.server.isolation import (
    DEFAULT_INTERNAL_PORTS,
    IsolationReport,
    IsolationViolation,
    ServerIsolationAuditor,
)
from nexcoder_security.server.masking import (
    DEFAULT_MASKING_RULES,
    DataMasker,
    MaskingProfile,
    MaskingRule,
    MaskingStrategy,
)
from nexcoder_security.server.nginx import (
    NginxConfigGenerator,
    NginxOptions,
    NginxProfile,
    NginxValidationResult,
    validate_nginx_config_in_container,
    validate_nginx_config_syntax,
)

__all__ = [
    "DEFAULT_INTERNAL_PORTS",
    "DEFAULT_MASKING_RULES",
    "DataMasker",
    "HardeningCheckItem",
    "HardeningOptions",
    "HardeningProfile",
    "HardeningResult",
    "IsolationReport",
    "IsolationViolation",
    "MaskingProfile",
    "MaskingRule",
    "MaskingStrategy",
    "NginxConfigGenerator",
    "NginxOptions",
    "NginxProfile",
    "NginxValidationResult",
    "ServerHardeningEngine",
    "ServerIsolationAuditor",
    "audit_server_action",
    "generate_bash_hardening_script",
    "generate_ps1_hardening_script",
    "validate_nginx_config_in_container",
    "validate_nginx_config_syntax",
]
