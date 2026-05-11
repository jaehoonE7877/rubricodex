from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifacts import (
    DEFAULT_EXECUTOR,
    DEFAULT_MODE,
    ArtifactError,
    compile_goal,
    compute_scorecard,
    init_project,
    lint_goal_file,
    matrix_path,
    read_json,
    run_dir,
    validate_brief,
    validate_evidence,
    validate_matrix,
    validate_scorecard,
    write_report,
    intent_path,
)


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _result(status: str, **extra: object) -> dict:
    return {"status": status, **extra}


def _validation_result(kind: str, issues: list) -> dict:
    return _result("pass" if not issues else "fail", kind=kind, issues=[issue.as_dict() for issue in issues])


def cmd_init(args: argparse.Namespace) -> int:
    paths = init_project(args.root, mode=args.mode, executor=args.executor, force=args.force)
    _print_json(_result("pass", paths=[str(path) for path in paths]))
    return 0


def cmd_intent_validate(args: argparse.Namespace) -> int:
    data = read_json(args.file or intent_path(args.root))
    result = _validation_result("intent_brief", validate_brief(data, args.mode))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_matrix_validate(args: argparse.Namespace) -> int:
    data = read_json(args.file or matrix_path(args.root))
    result = _validation_result("evaluation_matrix", validate_matrix(data, args.mode))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_goal_compile(args: argparse.Namespace) -> int:
    paths = compile_goal(
        args.root,
        args.run_id,
        mode=args.mode,
        executor=args.executor,
        brief_file=args.brief,
        matrix_file=args.matrix,
    )
    _print_json(_result("pass", paths={name: str(path) for name, path in paths.items()}))
    return 0


def cmd_prompt_lint(args: argparse.Namespace) -> int:
    result = lint_goal_file(args.root, args.run_id, mode=args.mode, goal_file=args.file)
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_evidence_validate(args: argparse.Namespace) -> int:
    matrix = read_json(args.matrix or matrix_path(args.root))
    evidence = read_json(args.file or run_dir(args.root, args.run_id) / "evidence.json")
    result = _validation_result("evidence", validate_evidence(evidence, matrix))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_score_validate(args: argparse.Namespace) -> int:
    data = read_json(args.file or run_dir(args.root, args.run_id) / "scorecard.json")
    result = _validation_result("scorecard", validate_scorecard(data))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_score_compute(args: argparse.Namespace) -> int:
    scorecard = compute_scorecard(args.root, args.run_id, evidence_file=args.evidence, matrix_file=args.matrix)
    _print_json(_result("pass", scorecard_path=str(run_dir(args.root, args.run_id) / "scorecard.json"), decision=scorecard["decision"]))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    paths = write_report(args.root, args.run_id)
    _print_json(_result("pass", paths={name: str(path) for name, path in paths.items()}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rubricodex")
    parser.add_argument("--root", default=".", help="Project root containing .rubricodex")
    parser.add_argument("--mode", default=DEFAULT_MODE, help="Rubricodex mode")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(action: argparse.ArgumentParser) -> None:
        action.add_argument("--root", default=argparse.SUPPRESS, help="Project root containing .rubricodex")
        action.add_argument("--mode", default=argparse.SUPPRESS, help="Rubricodex mode")

    init = subparsers.add_parser("init")
    add_common(init)
    init.add_argument("--executor", default=DEFAULT_EXECUTOR)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    intent = subparsers.add_parser("intent")
    intent_sub = intent.add_subparsers(dest="intent_command", required=True)
    intent_validate = intent_sub.add_parser("validate")
    add_common(intent_validate)
    intent_validate.add_argument("--file", type=Path)
    intent_validate.set_defaults(func=cmd_intent_validate)

    matrix = subparsers.add_parser("matrix")
    matrix_sub = matrix.add_subparsers(dest="matrix_command", required=True)
    matrix_validate = matrix_sub.add_parser("validate")
    add_common(matrix_validate)
    matrix_validate.add_argument("--file", type=Path)
    matrix_validate.set_defaults(func=cmd_matrix_validate)

    goal = subparsers.add_parser("goal")
    goal_sub = goal.add_subparsers(dest="goal_command", required=True)
    goal_compile = goal_sub.add_parser("compile")
    add_common(goal_compile)
    goal_compile.add_argument("--run-id", required=True)
    goal_compile.add_argument("--executor", default=DEFAULT_EXECUTOR)
    goal_compile.add_argument("--brief", type=Path)
    goal_compile.add_argument("--matrix", type=Path)
    goal_compile.set_defaults(func=cmd_goal_compile)

    prompt = subparsers.add_parser("prompt")
    prompt_sub = prompt.add_subparsers(dest="prompt_command", required=True)
    prompt_lint = prompt_sub.add_parser("lint")
    add_common(prompt_lint)
    prompt_lint.add_argument("--run-id", required=True)
    prompt_lint.add_argument("--file", type=Path)
    prompt_lint.set_defaults(func=cmd_prompt_lint)

    evidence = subparsers.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_validate = evidence_sub.add_parser("validate")
    add_common(evidence_validate)
    evidence_validate.add_argument("--run-id", required=True)
    evidence_validate.add_argument("--file", type=Path)
    evidence_validate.add_argument("--matrix", type=Path)
    evidence_validate.set_defaults(func=cmd_evidence_validate)

    score = subparsers.add_parser("score")
    score_sub = score.add_subparsers(dest="score_command", required=True)
    score_compute = score_sub.add_parser("compute")
    add_common(score_compute)
    score_compute.add_argument("--run-id", required=True)
    score_compute.add_argument("--evidence", type=Path)
    score_compute.add_argument("--matrix", type=Path)
    score_compute.set_defaults(func=cmd_score_compute)
    score_validate = score_sub.add_parser("validate")
    add_common(score_validate)
    score_validate.add_argument("--run-id", required=True)
    score_validate.add_argument("--file", type=Path)
    score_validate.set_defaults(func=cmd_score_validate)

    report = subparsers.add_parser("report")
    add_common(report)
    report.add_argument("--run-id", required=True)
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ArtifactError as error:
        _print_json(_result("fail", issues=[issue.as_dict() for issue in error.issues]))
        return 1


if __name__ == "__main__":
    sys.exit(main())
