from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifacts import (
    DEFAULT_EXECUTOR,
    DEFAULT_MODE,
    ArtifactError,
    collect_app_artifacts,
    compile_goal,
    compute_scorecard,
    draft_harness,
    import_app_session,
    init_project,
    lint_goal_file,
    matrix_path,
    orchestrate_run,
    orchestrate_status,
    plan_probes,
    read_json,
    run_local,
    run_probes,
    run_dir,
    validate_brief,
    validate_evidence,
    validate_app_cards,
    validate_app_session,
    validate_matrix,
    validate_scorecard,
    verify_matrix_lock,
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


def cmd_matrix_lock(args: argparse.Namespace) -> int:
    result = verify_matrix_lock(
        args.root,
        args.run_id,
        mode=args.mode,
        revision_reason=args.approve_revision,
        brief_file=args.brief,
        matrix_file=args.matrix,
        goal_file=args.goal,
    )
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_plan_draft(args: argparse.Namespace) -> int:
    result = draft_harness(
        args.root,
        args.run_id,
        args.goal,
        mode=args.plan_mode,
        task_kind=args.task_kind,
        executor=args.executor,
    )
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


def cmd_run_local(args: argparse.Namespace) -> int:
    result = run_local(
        args.root,
        args.run_id,
        mode=args.mode,
        execute=args.execute,
        codex_bin=args.codex_bin,
        result_summary=args.summary,
        verification_commands=args.verification_command,
        changed_files=args.changed_file,
    )
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_probe_plan(args: argparse.Namespace) -> int:
    result = plan_probes(
        args.root,
        args.run_id,
        mode=args.mode,
        criterion_ids=args.criterion_id,
        include_supporting=args.include_supporting,
        parallel=args.parallel,
    )
    _print_json(result)
    return 0


def cmd_probe_run(args: argparse.Namespace) -> int:
    result = run_probes(
        args.root,
        args.run_id,
        mode=args.mode,
        parallel=args.parallel,
        execute=args.execute,
        codex_bin=args.codex_bin,
    )
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_app_session_import(args: argparse.Namespace) -> int:
    result = import_app_session(args.root, args.source, mode=args.mode)
    _print_json(result)
    return 0


def cmd_app_collect(args: argparse.Namespace) -> int:
    result = collect_app_artifacts(args.root, args.run_id, mode=args.mode)
    _print_json(result)
    return 0


def cmd_app_session_validate(args: argparse.Namespace) -> int:
    data = read_json(args.file)
    result = _validation_result("app_session", validate_app_session(data))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_app_cards_validate(args: argparse.Namespace) -> int:
    data = read_json(args.file)
    result = _validation_result("app_cards", validate_app_cards(data))
    _print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_orchestrate_run(args: argparse.Namespace) -> int:
    result = orchestrate_run(
        args.root,
        args.run_id,
        mode=args.mode,
        backend=args.backend,
        parallel=args.parallel,
        execute=args.execute,
        codex_bin=args.codex_bin,
    )
    _print_json(result)
    return 0 if result["status"] in {"pass", "needs_retune"} else 1


def cmd_orchestrate_status(args: argparse.Namespace) -> int:
    result = orchestrate_status(args.root, args.run_id)
    _print_json(result)
    return 0 if result["status"] == "complete" else 1


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

    plan = subparsers.add_parser("plan")
    plan_sub = plan.add_subparsers(dest="plan_command", required=True)
    plan_draft = plan_sub.add_parser("draft")
    plan_draft.add_argument("--root", default=argparse.SUPPRESS, help="Project root containing .rubricodex")
    plan_draft.add_argument("--run-id", required=True)
    plan_draft.add_argument("--goal", required=True)
    plan_draft.add_argument("--plan-mode", "--mode", dest="plan_mode", default="auto", help="auto, micro, quick, standard, strict, or audit")
    plan_draft.add_argument("--task-kind", default="implementation")
    plan_draft.add_argument("--executor", default=DEFAULT_EXECUTOR)
    plan_draft.set_defaults(func=cmd_plan_draft)

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
    matrix_lock = matrix_sub.add_parser("lock")
    add_common(matrix_lock)
    matrix_lock.add_argument("--run-id", required=True)
    matrix_lock.add_argument("--approve-revision")
    matrix_lock.add_argument("--brief", type=Path)
    matrix_lock.add_argument("--matrix", type=Path)
    matrix_lock.add_argument("--goal", type=Path)
    matrix_lock.set_defaults(func=cmd_matrix_lock)

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

    run = subparsers.add_parser("run")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_local_parser = run_sub.add_parser("local")
    add_common(run_local_parser)
    run_local_parser.add_argument("--run-id", required=True)
    run_local_parser.add_argument("--execute", action="store_true")
    run_local_parser.add_argument("--codex-bin", default="codex")
    run_local_parser.add_argument("--summary")
    run_local_parser.add_argument("--verification-command", action="append", default=[])
    run_local_parser.add_argument("--changed-file", action="append", default=[])
    run_local_parser.set_defaults(func=cmd_run_local)

    probe = subparsers.add_parser("probe")
    probe_sub = probe.add_subparsers(dest="probe_command", required=True)
    probe_plan = probe_sub.add_parser("plan")
    add_common(probe_plan)
    probe_plan.add_argument("--run-id", required=True)
    probe_plan.add_argument("--criterion-id", action="append", default=[])
    probe_plan.add_argument("--include-supporting", action="store_true")
    probe_plan.add_argument("--parallel", type=int, default=4)
    probe_plan.set_defaults(func=cmd_probe_plan)
    probe_run = probe_sub.add_parser("run")
    add_common(probe_run)
    probe_run.add_argument("--run-id", required=True)
    probe_run.add_argument("--parallel", type=int, default=4)
    probe_run.add_argument("--execute", action="store_true")
    probe_run.add_argument("--codex-bin", default="codex")
    probe_run.set_defaults(func=cmd_probe_run)

    app = subparsers.add_parser("app")
    app_sub = app.add_subparsers(dest="app_command", required=True)
    app_session = app_sub.add_parser("session")
    app_session_sub = app_session.add_subparsers(dest="app_session_command", required=True)
    app_session_import = app_session_sub.add_parser("import")
    add_common(app_session_import)
    app_session_import.add_argument("--from", dest="source", type=Path, required=True)
    app_session_import.set_defaults(func=cmd_app_session_import)
    app_session_validate = app_session_sub.add_parser("validate")
    add_common(app_session_validate)
    app_session_validate.add_argument("--file", type=Path, required=True)
    app_session_validate.set_defaults(func=cmd_app_session_validate)
    app_collect = app_sub.add_parser("collect")
    add_common(app_collect)
    app_collect.add_argument("--run-id", "--run", dest="run_id", required=True)
    app_collect.set_defaults(func=cmd_app_collect)
    app_cards = app_sub.add_parser("cards")
    app_cards_sub = app_cards.add_subparsers(dest="app_cards_command", required=True)
    app_cards_validate = app_cards_sub.add_parser("validate")
    add_common(app_cards_validate)
    app_cards_validate.add_argument("--file", type=Path, required=True)
    app_cards_validate.set_defaults(func=cmd_app_cards_validate)

    orchestrate = subparsers.add_parser("orchestrate")
    orchestrate_sub = orchestrate.add_subparsers(dest="orchestrate_command", required=True)
    orchestrate_run_parser = orchestrate_sub.add_parser("run")
    add_common(orchestrate_run_parser)
    orchestrate_run_parser.add_argument("--run-id", "--run", dest="run_id", required=True)
    orchestrate_run_parser.add_argument("--backend", default="codex-cli-local")
    orchestrate_run_parser.add_argument("--parallel", type=int, default=4)
    orchestrate_run_parser.add_argument("--execute", action="store_true")
    orchestrate_run_parser.add_argument("--codex-bin", default="codex")
    orchestrate_run_parser.set_defaults(func=cmd_orchestrate_run)
    orchestrate_status_parser = orchestrate_sub.add_parser("status")
    add_common(orchestrate_status_parser)
    orchestrate_status_parser.add_argument("--run-id", "--run", dest="run_id", required=True)
    orchestrate_status_parser.set_defaults(func=cmd_orchestrate_status)
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
