import os

import typer
import uvicorn
from typing import Optional
from typing_extensions import Annotated

app = typer.Typer()


def version_callback(value: bool):
    if value:
        from open_webui.env import VERSION

        typer.echo(f"Halo WebUI version: {VERSION}")
        raise typer.Exit()


@app.command()
def main(
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=version_callback)
    ] = None,
):
    pass


@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8080,
):
    os.environ["FROM_INIT_PY"] = "true"

    if (
        os.getenv("ENABLE_LOCAL_MODEL_RUNTIME", "false") == "true"
        and os.getenv("USE_CUDA_DOCKER", "false") == "true"
    ):
        typer.echo(
            "CUDA is enabled, appending LD_LIBRARY_PATH to include torch/cudnn & cublas libraries."
        )
        LD_LIBRARY_PATH = os.getenv("LD_LIBRARY_PATH", "").split(":")
        os.environ["LD_LIBRARY_PATH"] = ":".join(
            LD_LIBRARY_PATH
            + [
                "/usr/local/lib/python3.11/site-packages/torch/lib",
                "/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib",
            ]
        )
        try:
            import torch

            assert torch.cuda.is_available(), "CUDA not available"
            typer.echo("CUDA seems to be working")
        except Exception as e:
            typer.echo(
                "Error when testing CUDA but USE_CUDA_DOCKER is true. "
                "Resetting USE_CUDA_DOCKER to false and removing "
                f"LD_LIBRARY_PATH modifications: {e}"
            )
            os.environ["USE_CUDA_DOCKER"] = "false"
            os.environ["LD_LIBRARY_PATH"] = ":".join(LD_LIBRARY_PATH)

    import open_webui.main  # we need set environment variables before importing main
    from open_webui.env import UVICORN_WORKERS  # Import the workers setting

    uvicorn.run(
        open_webui.main.app,
        host=host,
        port=port,
        forwarded_allow_ips="*",
        workers=UVICORN_WORKERS,
    )


@app.command()
def dev(
    host: str = "0.0.0.0",
    port: int = 8080,
    reload: bool = True,
):
    uvicorn.run(
        "open_webui.main:app",
        host=host,
        port=port,
        reload=reload,
        forwarded_allow_ips="*",
    )


@app.command("migrate-auto")
def migrate_auto(
    dry_run: bool = False,
    backup_only: bool = False,
    force_family: Optional[str] = None,
):
    from open_webui.runtime_migrations import migrate_auto as run_migrate_auto

    result = run_migrate_auto(
        dry_run=dry_run, backup_only=backup_only, force_family=force_family
    )
    typer.echo(result)


if __name__ == "__main__":
    app()
