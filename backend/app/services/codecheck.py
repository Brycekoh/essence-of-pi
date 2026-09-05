"""Static checks on model-written Manim code, run before the container starts.

This is a **feedback loop, not a security boundary**. The container is the
security boundary -- no network, capped memory, capped CPU, killed on timeout.
Everything here exists because a render costs seconds and a `compile()` costs
microseconds: catching a syntax error statically turns a 5-second failed render
into an instant correction round.

Treating this file as the defence would be a mistake. Any check based on
reading source can be evaded (`getattr(__builtins__, "ev" + "al")`), which is
exactly why the sandbox does not depend on it.
"""

import ast
from dataclasses import dataclass

# Names whose presence almost always means the model has misunderstood the
# task rather than that it is attacking anything -- reaching for the filesystem
# or the network instead of drawing. Flagged so the correction prompt can say
# so; the container is what makes them harmless either way.
_SUSPICIOUS_CALLS = {
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
}
_ALLOWED_IMPORT_ROOTS = {"manim", "numpy", "math", "random", "itertools"}


class CodeRejected(ValueError):
    """The code cannot possibly render, and we know that without running it."""


@dataclass(frozen=True)
class CodeReport:
    scene_names: list[str]
    warnings: list[str]


def check(code: str, expected_scene: str) -> CodeReport:
    """Validate model-written Manim source.

    Raises `CodeRejected` with a message written to be fed straight back to the
    model as a correction prompt -- so it says what is wrong and what to do,
    not just what failed.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise CodeRejected(
            f"The code has a syntax error on line {exc.lineno}: {exc.msg}"
        ) from exc

    scenes = _scene_classes(tree)
    if not scenes:
        raise CodeRejected(
            "No Scene subclass was defined. Define exactly one class that "
            f"inherits from Scene and name it {expected_scene}."
        )
    if expected_scene not in scenes:
        raise CodeRejected(
            f"The scene class is named {scenes[0]}, but it must be named "
            f"{expected_scene}. Rename the class and keep everything else."
        )
    if len(scenes) > 1:
        raise CodeRejected(
            f"{len(scenes)} Scene classes were defined ({', '.join(scenes)}). "
            f"Define exactly one, named {expected_scene}."
        )

    if not _has_construct(tree, expected_scene):
        raise CodeRejected(
            f"{expected_scene} has no construct(self) method, so it would "
            "render an empty video. Put the animation inside construct."
        )

    for module in _imported_roots(tree):
        if module not in _ALLOWED_IMPORT_ROOTS:
            raise CodeRejected(
                f"The code imports `{module}`, which is not available. Use only "
                "manim (plus numpy and the standard math module if needed)."
            )

    warnings = [
        f"calls {name}(), which does not belong in an animation"
        for name in sorted(_called_names(tree) & _SUSPICIOUS_CALLS)
    ]
    return CodeReport(scene_names=scenes, warnings=warnings)


def _scene_classes(tree: ast.Module) -> list[str]:
    """Class names whose bases mention Scene (Scene, MovingCameraScene, ...)."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if "Scene" in name:
                found.append(node.name)
                break
    return found


def _has_construct(tree: ast.Module, class_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return any(
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "construct"
                for item in node.body
            )
    return False


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _called_names(tree: ast.Module) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
