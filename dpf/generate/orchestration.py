"""Orchestration artefact renderers for Cloud Composer (Airflow), Dagster, and Prefect."""

from __future__ import annotations

from dpf.core import Product
from dpf.generate.render import marker, project_vars, snake_id, timezone


def _policy_tag_var_names(p: Product) -> list[str]:
    return [k for k in project_vars(p) if k.startswith("policy_tag_")]


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
    tag_vars = _policy_tag_var_names(p)
    lines = [
        _sched_trace(p),
        '"""Generated Cloud Composer (Airflow) DAGs for DPF product."""',
        "import os",
        "import pendulum",
        "from airflow import DAG",
    ]
    if engine == "dataform":
        lines += [
            "from airflow.models import Variable",
            "from airflow.providers.google.cloud.operators.dataform import (",
            "    DataformCreateCompilationResultOperator,",
            "    DataformCreateWorkflowInvocationOperator,",
            ")",
        ]
    else:
        lines.append("from airflow.operators.bash import BashOperator")
    lines.append("")
    proj = dep.get("gcp_project") or ""
    reg = dep.get("region") or ""
    rel_name = p.id.replace("_", "-")
    if engine == "dataform":
        lines.append(f"DATAFORM_REPO = Variable.get('dpf_{p.id}_dataform_repository', default_var={rel_name!r})")
        lines.append("")
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
                f"    compile_{sid} = DataformCreateCompilationResultOperator(",
                f"        task_id={('compile_' + sid)!r},",
                f"        project_id={proj!r},",
                f"        region={reg!r},",
                "        repository_id=DATAFORM_REPO,",
                "        compilation_result={",
                f"            'release_config': f'projects/{proj}/locations/{reg}/repositories/{{DATAFORM_REPO}}/releaseConfigs/{rel_name}',",
                "        },",
                "    )",
                f"    run_{sid} = DataformCreateWorkflowInvocationOperator(",
                f"        task_id={('run_' + sid)!r},",
                f"        project_id={proj!r},",
                f"        region={reg!r},",
                "        repository_id=DATAFORM_REPO,",
                "        workflow_invocation={",
                f"            'compilation_result': \"{{{{ task_instance.xcom_pull('compile_{sid}')['name'] }}}}\",",
                f"            'invocation_config': {{'included_tags': [{s['id']!r}]}},",
                "        },",
                "    )",
                f"    compile_{sid} >> run_{sid}",
                "",
            ]
        else:
            if tag_vars:
                vars_expr = ", ".join(f'\\"{k}\\": \\"${{DPF_{k.upper()}}}\\"' for k in tag_vars)
                cmd = f"dbt build --select tag:{s['id']} --exclude tag:acceptance --vars '{{{vars_expr}}}'"
            else:
                cmd = f"dbt build --select tag:{s['id']} --exclude tag:acceptance"
            lines += [
                f"    run_{sid} = BashOperator(",
                f"        task_id={('run_' + sid)!r},",
                f"        bash_command={cmd!r},",
                f"        env={{'TZ': {tz!r}, **{{k: v for k, v in os.environ.items() if k.startswith('DPF_')}}}},",
                "    )",
                "",
            ]
    return {f"airflow/dags/{p.id}_dag.py": "\n".join(lines)}


def _runtime_vars_helper(engine: str, tag_vars: list[str]) -> list[str]:
    if not tag_vars:
        return []
    if engine == "dbt":
        return [
            "def _var_args() -> list[str]:",
            "    import json, os",
            f"    vals = {{k: os.environ['DPF_' + k.upper()] for k in {tag_vars!r} if os.environ.get('DPF_' + k.upper())}}",
            "    return ['--vars', json.dumps(vals)] if vals else []",
            "",
        ]
    return [
        "def _var_args() -> list[str]:",
        "    import os",
        f"    pairs = [f'{{k}}={{os.environ[\"DPF_\" + k.upper()]}}' for k in {tag_vars!r} if os.environ.get('DPF_' + k.upper())]",
        "    return ['--vars', ','.join(pairs)] if pairs else []",
        "",
    ]


def render_dagster(p: Product, engine: str) -> dict[str, str]:
    orch = p.manifest.get("orchestration") or {}
    tz = timezone(p)
    tag_vars = _policy_tag_var_names(p)
    lines = [
        _sched_trace(p),
        '"""Generated Dagster schedules and job definitions for DPF product."""',
        "from dagster import ScheduleDefinition, Definitions, job, op",
        "import subprocess",
        "",
        *_runtime_vars_helper(engine, tag_vars),
    ]
    sched_names = []
    for s in orch.get("schedules") or []:
        sid = snake_id(s["id"])
        cmd = (["dbt", "build", "--select", f"tag:{s['id']}", "--exclude", "tag:acceptance"]
               if engine == "dbt" else ["dataform", "run", "--tags", s["id"]])
        run_expr = f"{cmd!r} + _var_args()" if tag_vars else f"{cmd!r}"
        lines += [
            "@op",
            f"def run_{sid}_op():",
            f"    subprocess.run({run_expr}, check=True)",
            "",
            "@job",
            f"def {p.id}_{sid}_job():",
            f"    run_{sid}_op()",
            "",
            f"{sid}_schedule = ScheduleDefinition(",
            f"    job={p.id}_{sid}_job,",
            f"    cron_schedule={s['cron']!r},",
            f"    execution_timezone={tz!r},",
            ")",
            "",
        ]
        sched_names.append(f"{sid}_schedule")
    lines.append(f"defs = Definitions(schedules=[{', '.join(sched_names)}])")
    lines.append("")
    return {f"dagster/{p.id}_assets.py": "\n".join(lines)}


def render_prefect(p: Product, engine: str) -> dict[str, str]:
    orch = p.manifest.get("orchestration") or {}
    tz = timezone(p)
    tag_vars = _policy_tag_var_names(p)
    lines = [
        _sched_trace(p),
        '"""Generated Prefect flows for DPF product (run or deploy with prefect.serve)."""',
        "from prefect import flow, serve",
        "from prefect.client.schemas.schedules import CronSchedule",
        "import subprocess",
        "",
        *_runtime_vars_helper(engine, tag_vars),
    ]
    deployments = []
    for s in orch.get("schedules") or []:
        sid = snake_id(s["id"])
        flow_name = f"dpf-{p.id}-{s['id']}"
        cmd = (["dbt", "build", "--select", f"tag:{s['id']}", "--exclude", "tag:acceptance"]
               if engine == "dbt" else ["dataform", "run", "--tags", s["id"]])
        run_expr = f"{cmd!r} + _var_args()" if tag_vars else f"{cmd!r}"
        lines += [
            f"@flow(name={flow_name!r})",
            f"def run_{sid}():",
            f"    \"\"\"Cron: {s['cron']} ({tz}).\"\"\"",
            f"    subprocess.run({run_expr}, check=True)",
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
