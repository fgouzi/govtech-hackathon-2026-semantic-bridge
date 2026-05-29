"""Typer CLI for semantic-bridge."""

from __future__ import annotations

import asyncio
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

import typer


def _fix_typing_extensions_in_webui_env(webui_bin: str) -> None:
    """
    uv tool install on Windows sometimes skips typing_extensions.py despite
    installing the dist-info. Copy from the project venv as a workaround.
    """
    webui_bin_path = Path(webui_bin).resolve()
    # e.g. C:\Users\xxx\AppData\Roaming\uv\tools\open-webui\Scripts\open-webui.exe
    webui_site = webui_bin_path.parent.parent / "Lib" / "site-packages"
    target = webui_site / "typing_extensions.py"
    if target.exists():
        return

    # Find typing_extensions.py in the project venv or system Python
    candidates = [
        Path(sys.executable).parent.parent / "Lib" / "site-packages" / "typing_extensions.py",
        Path(sys.executable).parent / "typing_extensions.py",
    ]
    for src in candidates:
        if src.exists():
            try:
                import shutil as _shutil
                _shutil.copy2(str(src), str(target))
                typer.echo(f"  Fixed typing_extensions in Open WebUI env")
            except Exception:
                pass
            return

app = typer.Typer(
    name="semantic-bridge",
    help="Swiss I14Y interoperability platform — semantic schema matching & transformation",
    add_completion=False,
)


def _kill_process_on_port(port: int) -> None:
    """Kill any process listening on the given port (Windows/Unix)."""
    import socket
    # Quick check: is the port in use?
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return  # Port is free

    import platform
    if platform.system() == "Windows":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                                capture_output=True)
                typer.echo(f"  Killed existing process on port {port} (PID {pid})")
                time.sleep(1.5)
                break
    else:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True)
        time.sleep(1.0)


def _preconfigure_webui_db(webui_port: int) -> None:
    """Write all Open WebUI config directly to DB before startup."""
    import glob
    import importlib.util

    # Find the DB
    patterns = [
        r"C:\Users\*\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\data\webui.db",
        "/root/.local/share/open-webui/webui.db",
        str(Path.home() / ".local/share/open-webui/webui.db"),
    ]
    db_path = None
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            db_path = matches[0]
            break
    if not db_path:
        typer.echo("  [WARN] Open WebUI DB not found — skipping pre-configuration")
        return

    # Run fix_webui_db.py, register_i14y_tools.py, register_i14y_filter.py, register_matching_tools.py
    for script in [
        "scripts/fix_webui_db.py",
        "scripts/register_i14y_tools.py",
        "scripts/register_i14y_filter.py",
        "scripts/register_matching_tools.py",
    ]:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Show only OK lines
            for line in result.stdout.splitlines():
                if line.startswith("[OK]"):
                    typer.echo(f"  {line}")
        else:
            typer.echo(f"  [WARN] {script}: {result.stderr[:200]}")


@app.command()
def serve(
    api_port: Annotated[int, typer.Option("--api-port", help="FastAPI port")] = 8000,
    ui_port: Annotated[int, typer.Option("--ui-port", help="Streamlit port")] = 8501,
    mock_port: Annotated[int, typer.Option("--mock-port", help="Mock MCP port")] = 8002,
    webui_port: Annotated[int, typer.Option("--webui-port", help="Open WebUI chat port")] = 8080,
    seed: Annotated[bool, typer.Option(help="Seed mock concepts on startup")] = True,
    no_webui: Annotated[bool, typer.Option("--no-webui", help="Skip Open WebUI")] = False,
) -> None:
    """Start FastAPI backend + Streamlit UI + Mock MCP server + Open WebUI chat."""
    typer.echo("Starting semantic-bridge platform...")

    if seed:
        typer.echo("  Seeding mock I14Y concepts...")
        result = subprocess.run(
            [sys.executable, "-m", "scripts.seed_mock_concepts"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            subprocess.run([sys.executable, "scripts/seed_mock_concepts.py"])

    processes: list[subprocess.Popen] = []
    webui_proc: subprocess.Popen | None = None

    try:
        # 1. Mock MCP server
        typer.echo(f"  Starting Mock MCP server on :{mock_port}...")
        mock_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "adapters.mock_mcp.server:app",
                "--host", "0.0.0.0",
                "--port", str(mock_port),
                "--log-level", "warning",
            ],
        )
        processes.append(mock_proc)
        time.sleep(1.5)

        # 2. FastAPI backend
        typer.echo(f"  Starting FastAPI backend on :{api_port}...")
        api_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", str(api_port),
                "--log-level", "info",
            ],
        )
        processes.append(api_proc)
        time.sleep(2.0)

        # 3. Streamlit UI
        typer.echo(f"  Starting Streamlit UI on :{ui_port}...")
        ui_proc = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run",
                "ui/main.py",
                "--server.port", str(ui_port),
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
            ],
        )
        processes.append(ui_proc)

        # 4. Open WebUI chat (optional — requires `uv tool install open-webui`)
        webui_proc = None
        if not no_webui:
            import shutil
            webui_bin = shutil.which("open-webui")
            if webui_bin:
                # Fix: uv tool install sometimes skips typing_extensions .py on Windows
                _fix_typing_extensions_in_webui_env(webui_bin)

                # Kill any existing process on webui_port to avoid [Errno 10048]
                _kill_process_on_port(webui_port)

                # Pre-configure DB (default model, tools, MCP) BEFORE starting Open WebUI
                # so the config is loaded on startup without needing API auth
                typer.echo("  Pre-configuring Open WebUI DB...")
                _preconfigure_webui_db(webui_port)

                typer.echo(f"  Starting Open WebUI chat on :{webui_port}...")
                import os
                webui_env = os.environ.copy()
                webui_env["WEBUI_AUTH"] = "False"
                webui_env["WEBUI_NAME"] = "Semantic Bridge - Decouverte Datasets I14Y"
                webui_env["PORT"] = str(webui_port)
                # Pre-configure LLM provider via env (OpenAI-compatible)
                from core.config import get_settings
                settings = get_settings()
                if settings.using_infomaniak:
                    webui_env["OPENAI_API_KEY"] = settings.infomaniak_api_key
                    webui_env["OPENAI_API_BASE_URL"] = settings.infomaniak_base_url
                elif settings.using_claude:
                    webui_env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
                webui_proc = subprocess.Popen(
                    [webui_bin, "serve", "--port", str(webui_port), "--host", "0.0.0.0"],
                    env=webui_env,
                )
                processes.append(webui_proc)
                time.sleep(3.0)
            else:
                typer.echo("  Open WebUI not installed — skipping chat UI")
                typer.echo("    Install with: uv tool install open-webui")

        typer.echo("")
        typer.echo("semantic-bridge is running!")
        if webui_proc is not None:
            typer.echo(f"   Chat (decouverte datasets) -> http://localhost:{webui_port}")
        typer.echo(f"   Streamlit UI  -> http://localhost:{ui_port}")
        typer.echo(f"   FastAPI docs  -> http://localhost:{api_port}/docs")
        typer.echo(f"   Health check  -> http://localhost:{api_port}/health")
        typer.echo(f"   Mock MCP      -> http://localhost:{mock_port}/mcp")
        typer.echo("")
        typer.echo("Press Ctrl+C to stop all services.")

        # Wait for any process to exit
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    typer.echo(f"  WARNING: Process {proc.pid} exited unexpectedly")
                    raise KeyboardInterrupt
            time.sleep(1)

    except KeyboardInterrupt:
        typer.echo("\nStopping all services...")
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        typer.echo("Stopped.")


@app.command()
def match(
    file: Annotated[Path, typer.Argument(help="CSV file to match")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSON path")] = Path("mapping.json"),
    api_url: Annotated[str, typer.Option(help="FastAPI base URL")] = "http://localhost:8000",
    use_ai: Annotated[bool, typer.Option(help="Use AI enrichment")] = True,
) -> None:
    """Match a CSV schema against I14Y concepts."""
    asyncio.run(_match(file, output, api_url, use_ai))


async def _match(file: Path, output: Path, api_url: str, use_ai: bool) -> None:
    import httpx
    import pandas as pd
    from domain.schema import DatasetSchema

    typer.echo(f"Reading {file}...")
    df = pd.read_csv(file)
    schema = DatasetSchema.from_dataframe(df, name=file.stem)
    typer.echo(f"Schema: {len(schema.fields)} fields, {schema.row_count} rows")

    typer.echo("Matching against I14Y concepts...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{api_url}/match",
            json={"schema_": schema.model_dump(), "use_ai": use_ai},
        )
        resp.raise_for_status()
        plan = resp.json()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=False))

    mappings = plan.get("mappings", [])
    typer.echo(f"\nResults ({len(mappings)} fields):")
    for m in mappings:
        concept = m.get("matched_concept")
        name = concept["name"] if concept else "—"
        conf = m.get("confidence", 0)
        icon = "✅" if conf >= 0.7 else "⚠️ " if conf >= 0.5 else "❌"
        typer.echo(f"  {icon} {m['source_field']} → {name} ({conf:.0%})")

    typer.echo(f"\nSaved to {output}")


@app.command()
def transform(
    mapping: Annotated[Path, typer.Argument(help="Mapping JSON file")],
    data: Annotated[Path, typer.Argument(help="CSV data file")],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("transformed.json"),
    api_url: Annotated[str, typer.Option()] = "http://localhost:8000",
) -> None:
    """Apply transformation plan to CSV records."""
    asyncio.run(_transform(mapping, data, output, api_url))


async def _transform(mapping_path: Path, data_path: Path, output: Path, api_url: str) -> None:
    import httpx
    import pandas as pd

    mapping = json.loads(mapping_path.read_text())
    df = pd.read_csv(data_path)
    records = df.to_dict(orient="records")

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{api_url}/transform",
            json={"mapping": mapping, "records": records},
        )
        resp.raise_for_status()
        result = resp.json()

    output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    typer.echo(f"Transformed {len(result['transformed'])} records → {output}")


@app.command()
def validate(
    mapping: Annotated[Path, typer.Argument(help="Mapping JSON file")],
    api_url: Annotated[str, typer.Option()] = "http://localhost:8000",
) -> None:
    """Validate a mapping plan."""
    asyncio.run(_validate(mapping, api_url))


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    resource_type: Annotated[str, typer.Option("--type", "-t", help="all|dataset|concept|dataservice")] = "all",
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    api_url: Annotated[str, typer.Option()] = "http://localhost:8000",
) -> None:
    """Search I14Y datasets, concepts and data services."""
    asyncio.run(_search(query, resource_type, limit, api_url))


async def _validate(mapping_path: Path, api_url: str) -> None:
    import httpx

    mapping = json.loads(mapping_path.read_text())

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{api_url}/validate", json={"mapping": mapping})
        resp.raise_for_status()
        report = resp.json()

    passed = report.get("passed", False)
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])

    typer.echo(f"\nValidation: {'✅ PASSED' if passed else '❌ FAILED'}")
    typer.echo(f"  {len(errors)} error(s), {len(warnings)} warning(s)")

    for issue in errors:
        typer.echo(f"  ❌ [{issue['issue']}] {issue['field']}: {issue['detail']}")
    for issue in warnings:
        typer.echo(f"  ⚠️  [{issue['issue']}] {issue['field']}: {issue['detail']}")

    raise typer.Exit(0 if passed else 1)


async def _search(query: str, resource_type: str, limit: int, api_url: str) -> None:
    import httpx

    typer.echo(f'Searching I14Y for "{query}" ({resource_type})...')
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{api_url}/search",
            params={"q": query, "resource_type": resource_type, "page_size": limit},
        )
        resp.raise_for_status()
        data = resp.json()

    total = data.get("total", 0)
    results = data.get("results", [])
    typer.echo(f"\n{total} total results (showing {len(results)}):\n")

    for r in results:
        rtype = r.get("type", "?")
        title = r.get("title") or r.get("identifier") or r.get("id", "")[:8]
        desc = r.get("description", "")[:80]
        identifier = r.get("identifier", "")
        typer.echo(f"  [{rtype}] {title}")
        if identifier:
            typer.echo(f"          identifier: {identifier}")
        if desc:
            typer.echo(f"          {desc}")


if __name__ == "__main__":
    app()
