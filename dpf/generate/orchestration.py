"""Orchestration artefact renderers for Cloud Composer (Airflow), Dagster, and Prefect."""

from __future__ import annotations

from dpf.core import Product
from dpf.generate.render import marker, snake_id, timezone


def _sched_trace(p: Product) -> str:
    orch = p.manifest.get("orchestration") or {}
    scheds = orch.get("schedules") or []
    elements = [f"schedule:{s['id']}" for s in scheds]
    reqs = sorted({r for s in scheds for r in (s.get("brd_requirement_id") or [])})
    fields = {"product": p.id, "element": ",".join(elements), "implements": "generate-artefacts"}
    if reqs:
        fields["satisfies"] = ",".join(reqs)
    return marker(fields, "#")


def render_composer(p: Product, engine: str) -> dict[str, str]:
    orch = p.manifest.get("orchestration") or {}
    dep = p.manifest.get("deployment") or {}
    tz = timezone(p)
    lines = [
        _sched_trace(p),
        '"""Generated Cloud Composer (Airflow) DAGs for DPF product."""',
        "import pendulum",
        "from airflow import DAG",
    ]
    if engine == "dataform":
        lines.append("from airflow.providers.google.cloud.operators.dataform import DataformCreateWorkflowInvocationOperator")
    else:
        lines.append("from airflow.operators.bash import BashOperator")
    lines.append("")
    proj = dep.get("gcp_project") or ""
    reg = dep.get("region") or ""
    rel_name = p.id.replace("_", "-")
    for s in orch.get("schedules") or []:
        sid = snake_id(s["id"])
        dag_id = f"dpf_{p.id}_{sid}"
        lines += [
            "with DAG(",
            f"    dag_id={dag_id!r},",
            f"    schedule={s['cron']!r},",
            f"    start_date=pendulum.datetime(2026, 1, 1, tz={tz!r}),",
            "    catchup=False,",
            f"    tags=['dpf', {p.id!r}, {s['id']!r}],",
            f") as dag_{sid}:",
        ]
        if engine == "dataform":
            lines += [
                f"    run_{sid} = DataformCreateWorkflowInvocationOperator(",
                f"        task_id={('run_' + sid)!r},",
                f"        project_id={proj!r},",
                f"        region={reg!r},",
                f"        repository_id={p.id!r},",
                "        workflow_invocation={",
                f"            'release_config': f'projects/{proj}/locations/{reg}/repositories/{p.id}/releaseConfigs/{rel_name}',",
                f"            'invocation_config': {{'included_tags': [{s['id']!r}]}},",
                "        },",
                "    )",
                "",
            ]
        else:
            cmd = f"dbt build --select tag:{s['id']} --exclude tag:acceptance"
            lines += [
                f"    run_{sid} = BashOperator(",
                f"        task_id={('run_' + sid)!r},",
                f"        bash_command={cmd!r},",
                f"        env={{'TZ': {tz!r}}},",
                "    )",
                "",
            ]
    return {f"airflow/dags/{p.id}_dag.py": "\n".join(lines)}


def render_dagster(p: Product, engine: str) -> dict[str, str]:
    orch = p.manifest.get("orchestration") or {}
    tz = timezone(p)
    lines = [
        _sched_trace(p),
        '"""Generated Dagster schedules and job definitions for DPF product."""',
        "from dagster import ScheduleDefinition, Definitions, job, op",
        "import subprocess",
        "",
    ]
    sched_names = []
    for s in orch.get("schedules") or []:
        sid = snake_id(s["id"])
        cmd = (["dbt", "build", "--select", f"tag:{s['id']}", "--exclude", "tag:acceptance"]
               if engine == "dbt" else ["dataform", "run", "--tags", s["id"]])
        lines += [
            f"@op",
            f"def run_{sid}_op():",
            f"    subprocess.run({cmd!r}, check=True)",
            "",
            f"@job",
            f"def {p.id}_{sid}_job():",
            f"    run_{sid}_op()",
            "",
            f"{sid}_schedule = ScheduleDefinition(",
            f"    job={p.id}_{sid}_job,",
            f"    cron_schedule={s['cron']!r},",
            f"    execution_timezone={tz!r},",
            f")",
            "",
        ]
        sched_names.append(f"{sid}_schedule")
    lines.append(f"defs = Definitions(schedules=[{', '.join(sched_names)}])")
    lines.append("")
    return {f"dagster/{p.id}_assets.py": "\n".join(lines)}


def render_prefect(p: Product, engine: str) -> dict[str, str]:
    orch = p.manifest.get("orchestration") or {}
    tz = timezone(p)
    lines = [
        _sched_trace(p),
        '"""Generated Prefect flows for DPF product (run or deploy with prefect.serve)."""',
        "from prefect import flow, serve",
        "from prefect.client.schemas.schedules import CronSchedule",
        "import subprocess",
        "",
    ]
    deployments = []
    for s in orch.get("schedules") or []:
        sid = snake_id(s["id"])
        flow_name = f"dpf-{p.id}-{s['id']}"
        cmd = (["dbt", "build", "--select", f"tag:{s['id']}", "--exclude", "tag:acceptance"]
               if engine == "dbt" else ["dataform", "run", "--tags", s["id"]])
        lines += [
            f"@flow(name={flow_name!r})",
            f"def run_{sid}():",
            f"    \"\"\"Cron: {s['cron']} ({tz}).\"\"\"",
            f"    subprocess.run({cmd!r}, check=True)",
            "",
        ]
        deployments.append(
            f"run_{sid}.to_deployment(name={flow_name!r}, schedule=CronSchedule(cron={s['cron']!r}, timezone={tz!r}))"
        )
    if deployments:
        lines += [
            'if __name__ == "__main__":',
            f"    serve({', '.join(deployments)})",
            "",
        ]
    return {f"prefect/{p.id}_flow.py": "\n".join(lines)}


def render(p: Product, engine: str) -> dict[str, str]:
    orch_engine = (p.manifest.get("orchestration") or {}).get("engine")
    if orch_engine == "composer":
        return render_composer(p, engine)
    if orch_engine == "dagster":
        return render_dagster(p, engine)
    if orch_engine == "prefect":
        return render_prefect(p, engine)
    return {}
