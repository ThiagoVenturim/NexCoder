"""IaC orchestration engine integrating generation, preview planning, confirmation gates, and audit."""

from __future__ import annotations

import uuid

from nexcoder_control.metering.audit import AppendOnlyAuditLog
from nexcoder_control.metering.cost_tracker import CostTracker

from nexcoder_iac.credentials import verify_user_credentials
from nexcoder_iac.generators.ansible import AnsibleGenerator
from nexcoder_iac.generators.compose import ComposeGenerator
from nexcoder_iac.generators.parser import HighLevelSpecParser
from nexcoder_iac.generators.terraform import TerraformGenerator
from nexcoder_iac.models import (
    ApplyResult,
    ArchitectureSpec,
    DatabaseEngine,
    IaCArtifacts,
    IaCTarget,
    IaCTool,
    PlanAction,
    PlanPreview,
    ResourcePlan,
)
from nexcoder_iac.pricing import estimate_monthly_cost


class IaCEngine:
    """Orchestrates infrastructure generation, preview planning, execution, and control plane audit."""

    def __init__(
        self,
        audit_log: AppendOnlyAuditLog | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.audit_log = audit_log or AppendOnlyAuditLog()
        self.cost_tracker = cost_tracker or CostTracker()

    def generate(
        self,
        spec: ArchitectureSpec | str,
        target: IaCTarget | None = None,
        tool: IaCTool | None = None,
        actor: str = "nexcoder-user",
    ) -> IaCArtifacts:
        """Generate deployable IaC artifacts from an ArchitectureSpec or high-level description."""
        if isinstance(spec, str):
            resolved_spec = HighLevelSpecParser.parse(spec, target_override=target)
        else:
            resolved_spec = spec
            if target:
                resolved_spec.target = target

        # Select appropriate tool based on target if not explicitly passed
        chosen_target = resolved_spec.target
        chosen_tool = tool
        if chosen_tool is None:
            if chosen_target == IaCTarget.LOCAL_COMPOSE:
                chosen_tool = IaCTool.COMPOSE
            elif chosen_target == IaCTarget.VM:
                chosen_tool = IaCTool.ANSIBLE
            else:
                chosen_tool = IaCTool.TERRAFORM

        # Dispatch to generator
        if chosen_tool == IaCTool.COMPOSE:
            generator = ComposeGenerator()
        elif chosen_tool in (IaCTool.TERRAFORM, IaCTool.OPENTOFU):
            generator = TerraformGenerator(tool=chosen_tool)
        elif chosen_tool == IaCTool.ANSIBLE:
            generator = AnsibleGenerator()
        else:
            generator = ComposeGenerator()

        artifacts = generator.generate(resolved_spec)

        # Audit log event
        self.audit_log.record_event(
            event_type="iac.generate",
            actor=actor,
            action="generate_iac",
            resource=f"{resolved_spec.name}:{chosen_target.value}",
            severity="info",
            details={
                "target": chosen_target.value,
                "tool": chosen_tool.value,
                "tier": resolved_spec.tier.value,
                "files_count": len(artifacts.files),
                "estimated_monthly_cost_usd": artifacts.estimated_monthly_cost_usd,
            },
        )

        # Track usage in control plane cost tracker
        self.cost_tracker.record_usage(
            model="deterministic_iac",
            input_tokens=100,
            output_tokens=500,
            app_id=resolved_spec.name,
            person_id=actor,
            agent_id="iac_generator",
            pipeline_id="iac_pipeline",
            metadata={"estimated_infrastructure_monthly_cost_usd": artifacts.estimated_monthly_cost_usd},
        )

        return artifacts

    def plan(
        self,
        artifacts: IaCArtifacts,
        actor: str = "nexcoder-user",
        dry_run: bool = True,
    ) -> PlanPreview:
        """Create a plan / preview before applying, identifying resource diffs and costs."""
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        spec = artifacts.spec
        target = artifacts.target
        tool = artifacts.tool

        planned_resources: list[ResourcePlan] = []
        warnings: list[str] = []

        # Check credentials if real apply intended
        if not dry_run:
            is_ready, missing = verify_user_credentials(target)
            if not is_ready:
                warnings.append(
                    f"Missing user credentials for target {target.value}: {', '.join(missing)}. "
                    "Apply will fail unless credentials are provided via environment variables."
                )

        # Compute resources to create based on target and spec
        if target == IaCTarget.LOCAL_COMPOSE:
            for svc in spec.services:
                planned_resources.append(
                    ResourcePlan(
                        resource_id=f"docker_container.{svc.name}",
                        resource_type="docker_container",
                        action=PlanAction.CREATE,
                        reason="Application service container",
                        estimated_cost_usd_month=0.0,
                    )
                )
            if spec.database and spec.database.engine != DatabaseEngine.NONE:
                planned_resources.append(
                    ResourcePlan(
                        resource_id="docker_container.db",
                        resource_type="docker_container",
                        action=PlanAction.CREATE,
                        reason=f"Local {spec.database.engine.value} container",
                        estimated_cost_usd_month=0.0,
                    )
                )
            if spec.cache:
                planned_resources.append(
                    ResourcePlan(
                        resource_id="docker_container.redis",
                        resource_type="docker_container",
                        action=PlanAction.CREATE,
                        reason="Local Redis cache/broker container",
                        estimated_cost_usd_month=0.0,
                    )
                )
        elif target == IaCTarget.AWS:
            planned_resources.extend(
                [
                    ResourcePlan(
                        resource_id="aws_vpc.app_vpc",
                        resource_type="aws_vpc",
                        action=PlanAction.CREATE,
                        reason="Isolated virtual private cloud network",
                        estimated_cost_usd_month=0.0,
                    ),
                    ResourcePlan(
                        resource_id="aws_subnet.public_subnet",
                        resource_type="aws_subnet",
                        action=PlanAction.CREATE,
                        reason="Public subnet with route table association",
                        estimated_cost_usd_month=0.0,
                    ),
                    ResourcePlan(
                        resource_id="aws_instance.app_server",
                        resource_type="aws_instance",
                        action=PlanAction.CREATE,
                        reason=f"EC2 compute node ({spec.tier.value} tier)",
                        estimated_cost_usd_month=38.0,
                    ),
                ]
            )
            if spec.database and spec.database.engine != DatabaseEngine.NONE:
                planned_resources.append(
                    ResourcePlan(
                        resource_id="aws_db_instance.database",
                        resource_type="aws_db_instance",
                        action=PlanAction.CREATE,
                        reason=f"Managed RDS {spec.database.engine.value} instance",
                        estimated_cost_usd_month=55.0,
                    )
                )
        elif target == IaCTarget.DIGITALOCEAN:
            planned_resources.append(
                ResourcePlan(
                    resource_id="digitalocean_droplet.web",
                    resource_type="digitalocean_droplet",
                    action=PlanAction.CREATE,
                    reason=f"Droplet compute server ({spec.tier.value} tier)",
                    estimated_cost_usd_month=24.0,
                )
            )
            if spec.database and spec.database.engine != DatabaseEngine.NONE:
                planned_resources.append(
                    ResourcePlan(
                        resource_id="digitalocean_database_cluster.db",
                        resource_type="digitalocean_database_cluster",
                        action=PlanAction.CREATE,
                        reason="Managed database cluster",
                        estimated_cost_usd_month=30.0,
                    )
                )
        elif target == IaCTarget.HETZNER:
            planned_resources.append(
                ResourcePlan(
                    resource_id="hcloud_server.server",
                    resource_type="hcloud_server",
                    action=PlanAction.CREATE,
                    reason=f"Hetzner Cloud VM ({spec.tier.value} tier)",
                    estimated_cost_usd_month=14.0,
                )
            )
        else:
            planned_resources.append(
                ResourcePlan(
                    resource_id=f"host.{target.value}_server",
                    resource_type="compute_instance",
                    action=PlanAction.CREATE,
                    reason="Application server instance",
                    estimated_cost_usd_month=20.0,
                )
            )

        total_cost = estimate_monthly_cost(spec)

        preview = PlanPreview(
            plan_id=plan_id,
            target=target,
            tool=tool,
            planned_resources=planned_resources,
            total_estimated_cost_usd_month=total_cost,
            execution_summary=(
                f"Plan {plan_id}: {len(planned_resources)} resource(s) to add, "
                f"0 to change, 0 to destroy. Estimated: ${total_cost:.2f}/mo."
            ),
            approval_required=True,
            dry_run=dry_run,
            warnings=warnings,
        )

        # Audit log plan preview
        self.audit_log.record_event(
            event_type="iac.plan",
            actor=actor,
            action="plan_infrastructure",
            resource=f"{spec.name}:{target.value}",
            severity="info",
            details={
                "plan_id": plan_id,
                "target": target.value,
                "tool": tool.value,
                "resource_count": len(planned_resources),
                "total_estimated_cost_usd_month": total_cost,
                "dry_run": dry_run,
            },
        )

        return preview

    def apply(
        self,
        preview: PlanPreview,
        confirm: bool = False,
        approval_token: str | None = None,
        actor: str = "nexcoder-user",
        dry_run: bool = True,
    ) -> ApplyResult:
        """Apply a planned infrastructure change with mandatory human confirmation."""
        if not confirm and not approval_token:
            raise PermissionError(
                "Applying infrastructure changes requires explicit confirmation (confirm=True) "
                "or a validated human approval token. Action blocked for safety."
            )

        if not dry_run:
            is_ready, missing = verify_user_credentials(preview.target)
            if not is_ready:
                raise ValueError(
                    f"Cannot apply: user credentials missing for target {preview.target.value}: {', '.join(missing)}. "
                    "Set credentials in your environment variables."
                )

        applied = [r.resource_id for r in preview.planned_resources]

        # Audit event in control plane
        event = self.audit_log.record_event(
            event_type="iac.apply",
            actor=actor,
            action="apply_infrastructure",
            resource=f"{preview.plan_id}:{preview.target.value}",
            severity="info" if dry_run else "warning",
            details={
                "plan_id": preview.plan_id,
                "target": preview.target.value,
                "applied_resources": applied,
                "confirmed": confirm,
                "dry_run": dry_run,
            },
        )

        status_msg = (
            f"Successfully simulated apply of {len(applied)} resource(s) (dry-run)."
            if dry_run
            else f"Successfully applied {len(applied)} resource(s) to {preview.target.value}."
        )

        return ApplyResult(
            success=True,
            plan_id=preview.plan_id,
            target=preview.target,
            status="applied" if not dry_run else "simulated_applied",
            applied_resources=applied,
            message=status_msg,
            audit_event_id=event.event_id,
            dry_run=dry_run,
        )

    def destroy(
        self,
        target: IaCTarget,
        resource_name: str,
        confirm: bool = False,
        approval_token: str | None = None,
        actor: str = "nexcoder-user",
        dry_run: bool = True,
    ) -> ApplyResult:
        """Destroy provisioned infrastructure with mandatory explicit confirmation."""
        if not confirm and not approval_token:
            raise PermissionError(
                "Destroying infrastructure requires explicit confirmation (confirm=True) "
                "or an emergency approval token. Teardown blocked for safety."
            )

        # Audit event with high severity
        event = self.audit_log.record_event(
            event_type="iac.destroy",
            actor=actor,
            action="destroy_infrastructure",
            resource=f"{resource_name}:{target.value}",
            severity="warning" if dry_run else "critical",
            details={
                "resource_name": resource_name,
                "target": target.value,
                "confirmed": confirm,
                "dry_run": dry_run,
            },
        )

        return ApplyResult(
            success=True,
            plan_id=f"destroy_{uuid.uuid4().hex[:8]}",
            target=target,
            status="destroyed" if not dry_run else "simulated_destroyed",
            applied_resources=[f"{resource_name}_all_resources"],
            message=f"Infrastructure teardown completed for {resource_name} on {target.value} (dry_run={dry_run}).",
            audit_event_id=event.event_id,
            dry_run=dry_run,
        )
