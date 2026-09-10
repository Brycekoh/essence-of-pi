"""How files reach a sandbox -- on the host, and under docker compose.

Under compose the backend's own paths are invisible to the Docker daemon, so a
bind mount would silently point at nothing. These pin down the volume-subpath
alternative, including the two refusals that keep a sandbox from seeing more
than its own scratch directory.
"""

from pathlib import Path

import pytest

from app.services.container import CONTAINER_WORKDIR, ContainerError, build_argv, mount_args


def _argv(**kw) -> list[str]:
    return build_argv(image="img", command=["true"], container="eop-test", **kw)


def test_host_mode_bind_mounts_an_absolute_path(tmp_path):
    argv = _argv(workdir=tmp_path / "videos" / ".render-1", storage_volume="")

    assert "--mount" not in argv
    source = argv[argv.index("--volume") + 1].rsplit(":", 1)[0]
    assert Path(source).is_absolute()


def test_compose_mode_mounts_only_the_subdirectory():
    argv = _argv(
        workdir=Path("/data/videos/.render-1"),
        storage_volume="essence-of-pi-storage",
        storage_root="/data",
    )

    assert "--volume" not in argv, "a bind mount would name a path the daemon cannot see"
    assert argv[argv.index("--mount") + 1] == (
        "type=volume,src=essence-of-pi-storage,dst=/work,volume-subpath=videos/.render-1"
    )


def test_compose_mode_keeps_every_sandbox_flag():
    argv = _argv(workdir=Path("/data/videos/.render-1"), storage_volume="v", storage_root="/data")

    assert argv[argv.index("--network") + 1] == "none"
    assert "--memory" in argv and "--cpus" in argv
    assert "--rm" in argv and "--name" in argv
    assert argv[argv.index("--workdir") + 1] == CONTAINER_WORKDIR


def test_a_path_outside_the_volume_is_refused():
    with pytest.raises(ContainerError, match="outside the storage volume"):
        mount_args(Path("/tmp/elsewhere"), storage_volume="v", storage_root="/data")


def test_the_whole_volume_is_never_mounted_into_a_sandbox():
    """Model-written code gets its scratch directory, not every upload."""
    with pytest.raises(ContainerError, match="whole storage volume"):
        mount_args(Path("/data"), storage_volume="v", storage_root="/data")


def test_the_environment_selects_compose_mode(monkeypatch):
    monkeypatch.setenv("STORAGE_VOLUME", "from-env")
    monkeypatch.setenv("STORAGE_ROOT", "/data")

    argv = _argv(workdir=Path("/data/uploads/.x"))

    assert "src=from-env" in argv[argv.index("--mount") + 1]


def test_scratch_directories_are_writable_by_any_sandbox_user(tmp_path):
    """The render image runs as uid 1000; the backend creating the dir is root.

    In a named volume a root-owned 755 directory is read-only to uid 1000, and
    manim died with `Permission denied: '/work/media'` the first time it ran
    under compose. On a Windows host the mode cannot be asserted -- chmod there
    only toggles read-only -- so the compose run itself is the real proof.
    """
    import os
    import stat

    from app.services.container import make_scratch

    path = make_scratch(tmp_path / "videos" / ".render-1")

    assert path.is_dir()
    assert make_scratch(path) == path, "idempotent: an existing directory is fine"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o777
