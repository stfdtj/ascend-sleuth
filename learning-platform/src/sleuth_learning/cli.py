"""sleuth-learn CLI -- see README.md for the full command reference and the
end-to-end demo. Every command here is local-only: nothing in this package
opens a network socket.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from . import render, storage
from .collector import discovery as discovery_mod
from .collector import package as package_mod
from .collector import snapshot as snapshot_mod
from .errors import SleuthLearningError
from .extraction import evidence_linker, trace_adapter, validation as validation_mod
from .fixtures import fixtures_root
from .generation import assemble as assemble_mod
from .generation import providers as providers_mod
from .generation import replay as replay_mod
from .generation import teaching as teaching_mod
from .hashing import content_hash, short


def _out(args, obj, text_lines):
    if getattr(args, "json", False):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        for line in text_lines:
            print(line)


# ---- demo-init ---------------------------------------------------------------

def cmd_demo_init(args):
    out = Path(args.out)
    (out / "traces").mkdir(parents=True, exist_ok=True)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    (out / "packages").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    src = fixtures_root()
    shutil.copytree(src / "sample_traces", out / "traces", dirs_exist_ok=True)
    shutil.copytree(src / "evidence", out / "evidence", dirs_exist_ok=True)
    print(f"Synthetic demo materials written to {out}")
    print(f"  traces:   {out / 'traces'}")
    print(f"  evidence: {out / 'evidence'}")
    print(f"  data dir: {out / 'data'} (empty -- this is where ingested snapshots/cases live)")
    print()
    print("Run the whole pipeline in one go:")
    print(f"  sleuth-learn demo-run --root {out}")
    print()
    print("...or step through it by hand, e.g.:")
    print(f"  sleuth-learn discover --root {out}")
    print(f"  sleuth-learn prepare --trace {out / 'traces' / 'complete.yaml'} "
          f"--allow-root {out} --out {out / 'packages' / 'complete'}")
    print(f"  sleuth-learn inspect --package {out / 'packages' / 'complete'}")
    print(f"  sleuth-learn ingest --package {out / 'packages' / 'complete'} --data-dir {out / 'data'}")


# ---- discover -----------------------------------------------------------------

def cmd_discover(args):
    traces_dir = Path(args.root) / "traces"
    candidates, skipped = discovery_mod.discover(traces_dir, include_in_progress=args.include_in_progress)
    rows = [c.to_dict() for c in candidates]
    lines = [f"{len(rows)} candidate session(s) in {traces_dir} "
             f"(in-progress {'included' if args.include_in_progress else 'excluded'})"]
    for c in candidates:
        lines.append(f"  {c.session_id:<32} {c.status:<10} {c.path.name}")
    for s in skipped:
        lines.append(f"  SKIPPED {s['path']}: {s['reason']}")
    _out(args, {"candidates": rows, "skipped": skipped}, lines)


# ---- prepare -------------------------------------------------------------------

def cmd_prepare(args):
    trace_path = Path(args.trace)
    allow_root = Path(args.allow_root)
    doc = discovery_mod.read_candidate(trace_path)
    plan = snapshot_mod.plan_sources(doc, trace_path, allow_root)

    if args.dry_run:
        lines = [f"Plan for {trace_path.name} (allow-root {allow_root}):",
                 f"  {len(plan.resolved)} evidence file(s) would be included:"]
        for r in plan.resolved:
            lines.append(f"    + {r.ref} ({r.size} bytes)")
        lines.append(f"  {len(plan.omitted)} reference(s) omitted:")
        for o in plan.omitted:
            lines.append(f"    - {o.source_pointer}: {o.reason}")
        _out(args, {"resolved": [r.ref for r in plan.resolved],
                    "omitted": [o.to_dict() for o in plan.omitted]}, lines)
        return

    if not args.out:
        raise SleuthLearningError("--out is required unless --dry-run is given")
    out_dir = Path(args.out)
    session_id = doc.get("session_id") or trace_path.stem
    with tempfile.TemporaryDirectory(prefix="sleuth-learn-staging-") as td:
        captured = snapshot_mod.capture_stable(plan, Path(td), settle_seconds=args.settle_seconds)
        manifest = package_mod.project_and_seal(
            captured, plan, out_dir, session_id=session_id, synthetic=not args.not_synthetic)

    lines = [f"Package sealed at {out_dir}",
             f"  snapshot_hash: {short(manifest['snapshot_hash'])}",
             f"  files: {len(manifest['content']['files'])}  omitted: {len(manifest['content']['omitted'])}",
             f"  synthetic: {manifest['content']['synthetic']}"]
    _out(args, manifest, lines)


# ---- inspect -------------------------------------------------------------------

def cmd_inspect(args):
    package_dir = Path(args.package)
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    shape_errors = package_mod.validate_manifest_shape(manifest)
    integrity_problems = package_mod.verify_blob_integrity(package_dir, manifest)
    lines = [f"Package {package_dir}",
             f"  schema_version: {manifest.get('schema_version')}",
             f"  snapshot_hash:  {manifest.get('snapshot_hash')}",
             f"  session_id:     {manifest['content']['source_identity'].get('session_id')}",
             f"  synthetic:      {manifest['content'].get('synthetic')}",
             f"  files ({len(manifest['content']['files'])}):"]
    for f in manifest["content"]["files"]:
        lines.append(f"    {f['id']:<8} {f['path']:<40} {f['bytes']:>8} bytes  {f['kind']}")
    if manifest["content"]["omitted"]:
        lines.append(f"  omitted ({len(manifest['content']['omitted'])}):")
        for o in manifest["content"]["omitted"]:
            lines.append(f"    {o['source_pointer']}: {o['reason']}")
    if shape_errors:
        lines.append("  SCHEMA ERRORS:")
        lines += [f"    - {e}" for e in shape_errors]
    if integrity_problems:
        lines.append("  INTEGRITY PROBLEMS:")
        lines += [f"    - {p['path']}: {p['problem']}" for p in integrity_problems]
    if not shape_errors and not integrity_problems:
        lines.append("  OK: schema valid, all blobs re-hashed and matched.")
    _out(args, {"manifest": manifest, "shape_errors": shape_errors,
               "integrity_problems": integrity_problems}, lines)


# ---- ingest --------------------------------------------------------------------

def cmd_ingest(args):
    result = storage.ingest_package(Path(args.package), Path(args.data_dir))
    lines = [f"snapshot_id: {result['snapshot_id']}",
             f"snapshot_hash: {short(result['snapshot_hash'])}",
             f"duplicate: {result['duplicate']}" + (
                 " (already ingested -- idempotent import, nothing re-copied)"
                 if result["duplicate"] else "")]
    _out(args, {"snapshot_id": result["snapshot_id"], "snapshot_hash": result["snapshot_hash"],
               "duplicate": result["duplicate"]}, lines)


# ---- generate ------------------------------------------------------------------

def _build_views(extracted, requested_mode, model_choice):
    """Returns (views, effective_generator_mode, provider_or_None).

    `generator.mode` is only ever "agent"/"engineer" when a model this MVP
    actually trusts produced it -- there is none here, so requesting
    mode=agent/engineer without --model mock downgrades to replay (per
    generation-design.md's "无模型时任务生成 replay" rule), and requesting
    it *with* --model mock is recorded honestly as mode="mock", never as
    "agent"/"engineer" -- this MVP never claims mock output is a real
    model's teaching judgement.
    """
    views = [replay_mod.generate_replay_view(extracted)]
    provider = providers_mod.MockModelProvider() if model_choice == "mock" else None

    if requested_mode == "replay":
        return views, "replay", None

    if requested_mode == "mock":
        provider = provider or providers_mod.MockModelProvider()
        views.append(teaching_mod.generate_view_or_unavailable(extracted, provider, "agent"))
        views.append(teaching_mod.generate_view_or_unavailable(extracted, provider, "engineer"))
        return views, "mock", provider

    if requested_mode in ("agent", "engineer"):
        if provider is None:
            views.append(teaching_mod.unavailable_view(
                requested_mode, "no model configured -- pass --model mock to use the offline "
                               "mock provider, or use --mode replay for the no-model baseline"))
            return views, "replay", None
        views.append(teaching_mod.generate_view_or_unavailable(extracted, provider, requested_mode))
        return views, "mock", provider

    raise SleuthLearningError(f"unknown mode: {requested_mode!r}")


def cmd_generate(args):
    data_dir = Path(args.data_dir)
    snap = storage.get_snapshot(data_dir, args.snapshot)
    package_dir, manifest = snap["dir"], snap["manifest"]

    registry = None
    if args.platform_registry:
        registry = json.loads(Path(args.platform_registry).read_text(encoding="utf-8"))

    extracted = trace_adapter.extract(package_dir, manifest, platform_registry=registry)
    evidence_linker.link_evidence(extracted)
    evidence_linker.verify_quotes(extracted, package_dir, manifest)

    views, effective_mode, provider = _build_views(extracted, args.mode, args.model)
    prompt_hash = providers_mod.prompt_hash() if provider else None

    case_id = storage.case_id_for_session(extracted.session_id)
    case = assemble_mod.assemble_case(extracted, manifest, effective_mode, views,
                                      case_id=case_id, provider=provider, prompt_hash=prompt_hash)
    findings = validation_mod.validate_artifact(
        case, package_dir=package_dir, manifest=manifest,
        source_event_count=extracted.source_event_count)

    key = storage.job_key(manifest["snapshot_hash"], effective_mode, case.generator.version,
                          case.generator.model_id, case.generator.prompt_hash)
    result = storage.save_case_revision(data_dir, case, findings, manifest=manifest, key=key,
                                        force=args.force)

    n_err = sum(1 for f in findings if f.severity == "error")
    n_rev = sum(1 for f in findings if f.severity == "review")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    lines = [f"case_id: {result['case_id']}", f"revision: {result['revision']}",
             f"duplicate: {result['duplicate']}" + (" (same job already generated this revision)"
                                                     if result["duplicate"] else ""),
             f"requested mode: {args.mode}  effective generator.mode: {effective_mode}",
             f"findings: {n_err} error / {n_rev} review / {n_warn} warning",
             *[f"  [{f.severity}/{f.code}] {f.pointer}: {f.message}" for f in findings]]
    if extracted.warnings:
        lines.append("extraction warnings:")
        lines += [f"  - {w}" for w in extracted.warnings]
    _out(args, {"case_id": result["case_id"], "revision": result["revision"],
               "duplicate": result["duplicate"], "effective_mode": effective_mode,
               "findings": [f.to_dict() for f in findings],
               "extraction_warnings": extracted.warnings}, lines)


# ---- validate / publish / withdraw / list -------------------------------------

def cmd_validate(args):
    data_dir = Path(args.data_dir)
    case = storage.get_case(data_dir, args.case, args.revision)
    head = storage.load_head(data_dir, args.case)
    n_err = sum(1 for f in case.validation if f.severity == "error")
    lines = [f"case {args.case} revision {case.revision}: generation_status={head['generation_status']} "
             f"publication_status={head['publication_status']}",
             f"{len(case.validation)} finding(s), {n_err} blocking (error-severity)"]
    for f in case.validation:
        lines.append(f"  [{f.severity}/{f.code}] {f.pointer}: {f.message}")
    _out(args, {"case_id": args.case, "revision": case.revision, "head": head,
               "findings": [f.to_dict() for f in case.validation]}, lines)


def cmd_publish(args):
    head = storage.publish(Path(args.data_dir), args.case, args.revision,
                           authorized=args.i_have_authorization,
                           allow_non_synthetic=args.allow_non_synthetic)
    _out(args, head, [f"case {args.case} revision {args.revision} published.",
                      f"publication_status: {head['publication_status']}"])


def cmd_withdraw(args):
    head = storage.withdraw(Path(args.data_dir), args.case, args.reason)
    _out(args, head, [f"case {args.case} withdrawn.", f"reason: {args.reason}"])


def cmd_list(args):
    data_dir = Path(args.data_dir)
    cases = storage.list_cases(data_dir)
    snaps = storage.list_snapshots(data_dir)
    lines = [f"{len(snaps)} snapshot(s):"]
    for s in snaps:
        lines.append(f"  {s['snapshot_id']}  {s['session_id']}  synthetic={s['synthetic']}")
    lines.append(f"{len(cases)} case(s):")
    for c in cases:
        lines.append(f"  {c['case_id']}  rev={c['latest_revision']}  "
                     f"gen={c['generation_status']}  pub={c['publication_status']}")
    _out(args, {"snapshots": snaps, "cases": cases}, lines)


# ---- render --------------------------------------------------------------------

def cmd_render(args):
    data_dir = Path(args.data_dir)
    case = storage.get_case(data_dir, args.case, args.revision)
    head = storage.load_head(data_dir, args.case)
    html = render.render_html(case, head)
    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"Rendered {out_path}")


# ---- demo-run ------------------------------------------------------------------

def cmd_demo_run(args):
    root = Path(args.root)
    trace_path = root / "traces" / "complete.yaml"
    if not trace_path.is_file():
        raise SleuthLearningError(f"{trace_path} not found -- run `sleuth-learn demo-init --out "
                                  f"{root}` first")
    package_dir = root / "packages" / "complete"
    data_dir = root / "data"

    doc = discovery_mod.read_candidate(trace_path)
    plan = snapshot_mod.plan_sources(doc, trace_path, root)
    with tempfile.TemporaryDirectory(prefix="sleuth-learn-staging-") as td:
        captured = snapshot_mod.capture_stable(plan, Path(td))
        manifest = package_mod.project_and_seal(captured, plan, package_dir,
                                                session_id=doc.get("session_id") or "demo",
                                                synthetic=True)
    print(f"1/6 prepared package  snapshot_hash={short(manifest['snapshot_hash'])}")

    ingested = storage.ingest_package(package_dir, data_dir)
    print(f"2/6 ingested           snapshot_id={ingested['snapshot_id']}  "
          f"duplicate={ingested['duplicate']}")

    snap = storage.get_snapshot(data_dir, ingested["snapshot_id"])
    extracted = trace_adapter.extract(snap["dir"], snap["manifest"])
    evidence_linker.link_evidence(extracted)
    evidence_linker.verify_quotes(extracted, snap["dir"], snap["manifest"])
    views, effective_mode, provider = _build_views(extracted, "mock", "mock")
    case_id = storage.case_id_for_session(extracted.session_id)
    case = assemble_mod.assemble_case(extracted, snap["manifest"], effective_mode, views,
                                      case_id=case_id, provider=provider,
                                      prompt_hash=providers_mod.prompt_hash())
    findings = validation_mod.validate_artifact(
        case, package_dir=snap["dir"], manifest=snap["manifest"],
        source_event_count=extracted.source_event_count)
    key = storage.job_key(snap["manifest"]["snapshot_hash"], effective_mode,
                          case.generator.version, case.generator.model_id, case.generator.prompt_hash)
    result = storage.save_case_revision(data_dir, case, findings, manifest=snap["manifest"], key=key)
    print(f"3/6 generated           case_id={result['case_id']}  revision={result['revision']}  "
          f"mode={effective_mode}")

    n_err = sum(1 for f in findings if f.severity == "error")
    print(f"4/6 validated           {len(findings)} finding(s), {n_err} blocking")

    stored_case = storage.get_case(data_dir, result["case_id"], result["revision"])
    artifact_hash = content_hash(stored_case.to_dict())
    published = False
    if n_err == 0:
        storage.publish(data_dir, result["case_id"], result["revision"], authorized=True)
        published = True
        print("5/6 published           (demo-run self-authorizes for this one-shot demo -- "
              "see README: real usage requires a human to pass --i-have-authorization)")
    else:
        print("5/6 publish SKIPPED     blocking findings present")

    out_html = root / "demo-case.html"
    head = storage.load_head(data_dir, result["case_id"])
    out_html.write_text(render.render_html(stored_case, head), encoding="utf-8")
    print(f"6/6 rendered            {out_html}")

    summary = {
        "case_id": result["case_id"], "revision": result["revision"],
        "snapshot_hash": snap["manifest"]["snapshot_hash"], "artifact_hash": artifact_hash,
        "published": published, "findings": len(findings), "blocking": n_err,
        "reader": str(out_html),
    }
    print()
    print("Acceptance summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


# ---- argparse wiring ------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="sleuth-learn")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, func, help_text):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.set_defaults(func=func)
        return sp

    sp = add("demo-init", cmd_demo_init, "write synthetic demo traces/evidence/data dirs")
    sp.add_argument("--out", required=True)

    sp = add("discover", cmd_discover, "list candidate trace sessions under <root>/traces")
    sp.add_argument("--root", required=True)
    sp.add_argument("--include-in-progress", action="store_true")

    sp = add("prepare", cmd_prepare, "build a local collector package from one trace")
    sp.add_argument("--trace", required=True)
    sp.add_argument("--allow-root", required=True,
                    help="safety boundary: evidence refs must resolve inside this directory")
    sp.add_argument("--out", required=False, help="package output directory (omit with --dry-run)")
    sp.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    sp.add_argument("--not-synthetic", action="store_true",
                    help="mark the package as real (non-synthetic) material; affects publish "
                         "authorization later")
    sp.add_argument("--settle-seconds", type=float, default=0.2)

    sp = add("inspect", cmd_inspect, "show a package's manifest and re-verify blob integrity")
    sp.add_argument("--package", required=True)

    sp = add("ingest", cmd_ingest, "idempotently import a package into the local store")
    sp.add_argument("--package", required=True)
    sp.add_argument("--data-dir", required=True)

    sp = add("generate", cmd_generate, "run extraction + generation for an ingested snapshot")
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--snapshot", required=True)
    sp.add_argument("--mode", choices=["replay", "mock", "agent", "engineer"], default="replay")
    sp.add_argument("--model", choices=["none", "mock"], default="none")
    sp.add_argument("--platform-registry", default=None,
                    help="optional JSON file {case_id: [platform,...]} of authorized "
                         "applicability facts")
    sp.add_argument("--force", action="store_true", help="create a new revision even if this "
                                                           "exact job already ran")

    sp = add("validate", cmd_validate, "show stored validation findings for a case revision")
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--case", required=True)
    sp.add_argument("--revision", type=int, default=None)

    sp = add("publish", cmd_publish, "publish a case revision (requires explicit authorization)")
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--case", required=True)
    sp.add_argument("--revision", type=int, required=True)
    sp.add_argument("--i-have-authorization", action="store_true")
    sp.add_argument("--allow-non-synthetic", action="store_true")

    sp = add("withdraw", cmd_withdraw, "withdraw a case from publication")
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--case", required=True)
    sp.add_argument("--reason", default="")

    sp = add("list", cmd_list, "list snapshots and cases in a data dir")
    sp.add_argument("--data-dir", required=True)

    sp = add("render", cmd_render, "render a case revision to a static HTML reader page")
    sp.add_argument("--data-dir", required=True)
    sp.add_argument("--case", required=True)
    sp.add_argument("--revision", type=int, default=None)
    sp.add_argument("--out", required=True)

    sp = add("demo-run", cmd_demo_run, "run the full pipeline end to end on the synthetic demo")
    sp.add_argument("--root", required=True)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SleuthLearningError as e:
        if getattr(args, "json", False):
            print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        else:
            print(f"error[{e.code}]: {e.message}", file=sys.stderr)
            if e.details:
                print(f"  details: {e.details}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
