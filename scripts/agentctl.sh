#!/usr/bin/env bash
#
# agentctl.sh - lightweight orchestration harness for agent_tasks.
#
# Subcommands:
#   run <task-id>     Start Claude Code on a task in an isolated worktree.
#   review <task-id>  Start a review-only Claude session for a task. The
#                     reviewer writes a structured verdict artifact at
#                     .agentctl/reviews/<task-id>.md (front matter with
#                     `verdict:` plus required-fixes / notes sections).
#   review-status <task-id>
#                     Print the latest review verdict, artifact path, and
#                     a short summary of required fixes / optional notes
#                     for a task. Does not invoke Claude.
#   fix <task-id>     Launch Claude inside the task worktree to address the
#                     `Required fixes` from the latest review artifact.
#                     Refuses if the latest verdict is APPROVE,
#                     APPROVE_WITH_NOTES, or there is no review artifact.
#   next              Print the next recommended action without mutating
#                     any files, branches, queue statuses, or worktrees.
#   work [<task-id>] [--until-blocked] [--max-fix-attempts N]
#        [--max-tasks N] [--dry-run]
#                     Run one (or many) task lifecycles: run -> review ->
#                     auto-fix on REQUEST_CHANGES (capped by
#                     --max-fix-attempts) -> complete. Writes a journal
#                     file under .agentctl/journal/ for every invocation.
#                     Stops on REJECT, BLOCKED, max fix attempts, dirty
#                     worktree, or any subcommand failure.
#   sync <task-id>    Ensure task worktree exists and is up to date with main.
#   complete <task-id> [--dry-run] [--clean-shadow-files] [--skip-review]
#                     Run verification, merge the task's worktree branch into
#                     main, mark the task done, promote unblocked tasks, and
#                     commit the queue update. --dry-run prints what would
#                     happen without changing files or branches.
#                     --clean-shadow-files removes untracked files in main
#                     whose paths are tracked in the task branch (likely
#                     leaked from the task worktree). It never runs a broad
#                     git clean and never touches modified tracked files.
#                     --skip-review bypasses the review-verdict gate; it
#                     prints a loud warning and proceeds even if there is
#                     no review artifact. It does NOT bypass a verdict of
#                     REQUEST_CHANGES, REJECT, or BLOCKED — those still
#                     refuse, and must be addressed (e.g. via `fix`) or
#                     the artifact must be edited/removed by hand.
#   complete --continue <task-id>
#                     Resume `complete` after the operator resolved a merge
#                     conflict by hand. Finishes the merge commit, runs
#                     verification, then updates queue statuses.
#   status            Print task ids grouped by status.
#   list              Print every task with its status and title.
#   ready             Print tasks whose status is 'ready'.
#   doctor            Run a read-only preflight check of the local agent
#                     harness environment (git state, queue.yaml, tool
#                     availability, Claude permission settings, and node
#                     workspace readiness). Reports PASS / WARN / FAIL per
#                     check. Exits 0 if no FAIL items were reported.
#   plan "<goal>"     Run a local Claude Code planning session that generates
#                     scoped task files and queue entries from a high-level
#                     goal. Does not implement product code.
#   plan --ultraplan "<goal>"
#                     Write an Ultraplan-ready prompt file under .agent_plans/
#                     and print manual handoff instructions. Does not invoke
#                     Claude Code itself.
#   plan --help       Show plan-specific help.
#
# Configuration via environment variables:
#   CLAUDE_BIN                       Claude Code executable. Default: claude
#   CLAUDE_PERMISSION_MODE           Permission mode for run. Default: acceptEdits
#   CLAUDE_REVIEW_PERMISSION_MODE    Permission mode for review. Default: acceptEdits
#                                    (was 'plan' before structured review
#                                    artifacts; the reviewer now writes
#                                    exactly one file, the review artifact.)
#   CLAUDE_FIX_PERMISSION_MODE       Permission mode for fix. Default: acceptEdits
#   CLAUDE_PLAN_PERMISSION_MODE      Permission mode for plan. Default: acceptEdits
#   CLAUDE_PYTHON                    Python interpreter used to parse YAML. Default: python3
#
# Dependencies:
#   bash, git, and a Python 3 interpreter with PyYAML available.
#   See docs/contracts/agent_orchestration.md.
#
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
CLAUDE_PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-acceptEdits}"
CLAUDE_REVIEW_PERMISSION_MODE="${CLAUDE_REVIEW_PERMISSION_MODE:-acceptEdits}"
CLAUDE_FIX_PERMISSION_MODE="${CLAUDE_FIX_PERMISSION_MODE:-acceptEdits}"
CLAUDE_PLAN_PERMISSION_MODE="${CLAUDE_PLAN_PERMISSION_MODE:-acceptEdits}"
CLAUDE_PYTHON="${CLAUDE_PYTHON:-python3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
QUEUE_FILE="$REPO_ROOT/agent_tasks/queue.yaml"
PLANS_DIR="$REPO_ROOT/.agent_plans"
PLANNING_GUIDELINES="$REPO_ROOT/agent_tasks/planning_guidelines.md"

# Valid review verdicts (matches the documented enum in
# docs/contracts/agent_orchestration.md). Kept here as a shell-side
# constant so review-status, complete, and fix can validate against the
# same list without re-parsing the doc.
REVIEW_VERDICTS=(APPROVE APPROVE_WITH_NOTES REQUEST_CHANGES REJECT BLOCKED)

err() { printf 'error: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

require_queue() {
  if [[ ! -f "$QUEUE_FILE" ]]; then
    die "queue file not found: $QUEUE_FILE"
  fi
}

require_python_yaml() {
  if ! "$CLAUDE_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
    die "Python interpreter '$CLAUDE_PYTHON' cannot import PyYAML.
   Install PyYAML (e.g. 'pip install pyyaml' or use an env that has it),
   or set CLAUDE_PYTHON to a Python that does."
  fi
}

# yaml_query <mode> [task_id]
#
# Modes:
#   list           Print "<id>\t<status>\t<title>" for every task.
#   status         Print "<status>\t<id>" for every task (sorted by status).
#   ids            Print every task id, one per line.
#   field <id> <key>
#                  Print one scalar field of a task. For list fields prints
#                  each entry on its own line.
#   status_of <id> Print the status string for a single task id.
#   deps <id>      Print "<dep_id>\t<dep_status>" for each dependency.
#   resolve <ref>  Resolve a task reference to its full id. <ref> may be the
#                  full id, or an all-digit numeric shortcut (e.g. "14" or
#                  "014") that matches the NNN- prefix of exactly one task.
yaml_query() {
  require_queue
  require_python_yaml
  CLAUDE_QUEUE_FILE="$QUEUE_FILE" "$CLAUDE_PYTHON" - "$@" <<'PYEOF'
import os, sys, yaml

queue_path = os.environ["CLAUDE_QUEUE_FILE"]
with open(queue_path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
tasks = data.get("tasks") or []

mode = sys.argv[1] if len(sys.argv) > 1 else ""

def get_task(task_id):
    for t in tasks:
        if t.get("id") == task_id:
            return t
    sys.stderr.write(f"error: unknown task id: {task_id}\n")
    sys.exit(2)

if mode == "list":
    for t in tasks:
        print(f"{t.get('id','')}\t{t.get('status','')}\t{t.get('title','')}")
elif mode == "status":
    rows = [(t.get("status",""), t.get("id","")) for t in tasks]
    for status, tid in sorted(rows, key=lambda r: (r[0], r[1])):
        print(f"{status}\t{tid}")
elif mode == "ids":
    for t in tasks:
        print(t.get("id",""))
elif mode == "status_of":
    print(get_task(sys.argv[2]).get("status",""))
elif mode == "field":
    t = get_task(sys.argv[2])
    val = t.get(sys.argv[3])
    if val is None:
        pass
    elif isinstance(val, list):
        for item in val:
            print(item)
    else:
        print(val)
elif mode == "deps":
    t = get_task(sys.argv[2])
    by_id = {x.get("id"): x for x in tasks}
    for dep in (t.get("depends_on") or []):
        d = by_id.get(dep)
        st = d.get("status","") if d else "missing"
        print(f"{dep}\t{st}")
elif mode == "resolve":
    ref = sys.argv[2]
    ids = [t.get("id","") for t in tasks if t.get("id")]
    if ref in ids:
        print(ref)
    elif ref.isdigit():
        prefix = ref.zfill(3) + "-"
        matches = [tid for tid in ids if tid.startswith(prefix)]
        if len(matches) == 1:
            print(matches[0])
        elif not matches:
            sys.stderr.write(
                f"error: no task matches numeric prefix '{ref.zfill(3)}'\n")
            sys.exit(2)
        else:
            sys.stderr.write(
                f"error: numeric prefix '{ref.zfill(3)}' matches multiple tasks:\n")
            for m in matches:
                sys.stderr.write(f"  {m}\n")
            sys.exit(2)
    else:
        sys.stderr.write(f"error: unknown task id: {ref}\n")
        sys.exit(2)
else:
    sys.stderr.write(f"error: unknown yaml_query mode: {mode}\n")
    sys.exit(2)
PYEOF
}

# resolve_task_id <ref>
#
# Resolve a task reference (full id, "014", or "14") to its full task id by
# querying queue.yaml. Prints the resolved id to stdout. If the reference
# was a shortcut, also prints a "Resolved task <ref> -> <id>" notice to
# stderr so it does not pollute captured output. Exits non-zero if the
# reference matches zero or multiple tasks (yaml_query writes the error).
resolve_task_id() {
  local input="$1"
  local resolved

  resolved="$(yaml_query resolve "$input")" || exit $?

  if [[ "$resolved" != "$input" ]]; then
    printf 'Resolved task %s -> %s\n' "$input" "$resolved" >&2
  fi

  printf '%s\n' "$resolved"
}

cmd_list() {
  printf '%-30s %-10s %s\n' "ID" "STATUS" "TITLE"
  printf '%-30s %-10s %s\n' "------------------------------" "----------" "-----"
  while IFS=$'\t' read -r id status title; do
    [[ -z "$id" ]] && continue
    printf '%-30s %-10s %s\n' "$id" "$status" "$title"
  done < <(yaml_query list)
}

cmd_ready() {
  local found=0
  printf '%-30s %s\n' "ID" "TITLE"
  printf '%-30s %s\n' "------------------------------" "-----"
  while IFS=$'\t' read -r id status title; do
    [[ -z "$id" ]] && continue
    [[ "$status" == "ready" ]] || continue
    printf '%-30s %s\n' "$id" "$title"
    found=1
  done < <(yaml_query list)
  if [[ "$found" -eq 0 ]]; then
    printf '(no tasks with status=ready)\n'
  fi
}


cmd_run_interactive() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh run-interactive <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local status task_file worktree
  status="$(yaml_query status_of "$task_id")"
  task_file="$(yaml_query field "$task_id" file)"
  worktree="$(yaml_query field "$task_id" worktree)"

  [[ -n "$task_file" ]] || die "task '$task_id' has no 'file' field"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  local abs_task_file="$REPO_ROOT/$task_file"
  [[ -f "$abs_task_file" ]] || die "task file not found: $abs_task_file"

  if [[ "$status" == "done" ]]; then
    err "task '$task_id' is already marked done; refusing to re-run"
    exit 1
  fi

  check_dependencies "$task_id"
  ensure_clean_worktree

  local wt_path=""
  if [[ "$worktree" != "main" ]]; then
    wt_path="$(ensure_worktree "$worktree")"
    merge_main_if_behind "$wt_path"
    propagate_claude_permissions "$wt_path"
  fi

  local launch_dir="$REPO_ROOT"
  [[ -n "$wt_path" ]] && launch_dir="$wt_path"

  local prompt
  prompt="$(build_run_interactive_prompt "$task_id" "$abs_task_file" "$wt_path" "$REPO_ROOT")"

  printf 'Starting interactive Claude Code for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path: %s\n' "$wt_path"
  printf '  launch dir: %s\n' "$launch_dir"
  printf '  permission-mode: %s\n' "$CLAUDE_PERMISSION_MODE"
  printf '\nInteractive supervised mode: Claude will stop before committing and wait for you to type "commit".\n\n'

  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_PERMISSION_MODE" \
      "$prompt" ); then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nSession ended. Recent commits:\n'
  git -C "$launch_dir" log --oneline -5
  printf '\nGit status:\n'
  git -C "$launch_dir" status --short
}

cmd_status() {
  local current_status="" status id
  while IFS=$'\t' read -r status id; do
    [[ -z "$id" ]] && continue
    if [[ "$status" != "$current_status" ]]; then
      [[ -n "$current_status" ]] && printf '\n'
      printf '[%s]\n' "$status"
      current_status="$status"
    fi
    printf '  %s\n' "$id"
  done < <(yaml_query status)
}

ensure_clean_worktree() {
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    err "git tree is not clean; commit or stash before starting a new run:"
    git -C "$REPO_ROOT" status --short >&2
    exit 1
  fi
}

check_dependencies() {
  local task_id="$1" dep status missing=0
  while IFS=$'\t' read -r dep status; do
    [[ -z "$dep" ]] && continue
    if [[ "$status" != "done" ]]; then
      err "dependency '$dep' has status '$status' (expected 'done')"
      missing=1
    fi
  done < <(yaml_query deps "$task_id")
  [[ "$missing" -eq 0 ]] || exit 1
}

# worktree_path <name>
#
# Print the absolute path of the existing worktree whose final path segment
# matches <name>. Empty output (and exit 0) means no such worktree exists.
worktree_path() {
  local name="$1"
  git -C "$REPO_ROOT" worktree list --porcelain \
    | awk -v name="$name" '
        /^worktree / { wt=$2; if (wt ~ ("/" name "$")) { print wt; exit } }
      '
}

# ensure_worktree <name>
#
# Print the worktree path, creating the worktree if it does not yet exist.
# New worktrees are created at .claude/worktrees/<name> on a new branch
# named worktree-<name>, branched from main. Matches Claude Code's
# --worktree convention so a subsequent `claude --worktree <name>` reuses
# the same checkout.
ensure_worktree() {
  local name="$1" wt
  wt="$(worktree_path "$name")"
  if [[ -n "$wt" ]]; then
    printf '%s\n' "$wt"
    return 0
  fi
  wt="$REPO_ROOT/.claude/worktrees/$name"
  mkdir -p "$REPO_ROOT/.claude/worktrees"
  printf 'Creating worktree %s at %s\n' "$name" "$wt" >&2
  git -C "$REPO_ROOT" worktree add -b "worktree-$name" "$wt" main >&2
  printf '%s\n' "$wt"
}

# propagate_claude_permissions <worktree_path>
#
# Symlink the main checkout's .claude/settings.local.json into the task
# worktree at <worktree_path> so non-interactive Claude Code sessions
# launched there see the operator's permission allowlist. Without this,
# Claude prompts for routine commands (npm install, git add, etc.) on
# every run because the gitignored settings file does not propagate to
# worktrees on its own.
#
# Safe to call repeatedly: returns 0 silently when there is nothing to do
# (no main settings file, target is main itself, or the correct symlink
# already exists). Never reads or prints the settings contents. Never
# overwrites a non-symlink file at the target path — that case warns and
# returns 0 so the caller is not blocked.
propagate_claude_permissions() {
  local wt="$1"
  [[ -n "$wt" ]] || return 0

  local main_wt
  main_wt="$(find_main_worktree 2>/dev/null)" || return 0
  [[ -n "$main_wt" ]] || return 0

  local src="$main_wt/.claude/settings.local.json"
  [[ -f "$src" ]] || return 0

  if [[ "$wt" == "$main_wt" ]]; then
    return 0
  fi

  local dst="$wt/.claude/settings.local.json"

  if [[ -L "$dst" ]]; then
    local existing
    existing="$(readlink "$dst")"
    [[ "$existing" == "$src" ]] && return 0
  elif [[ -e "$dst" ]]; then
    err "worktree already has $dst (not a symlink); leaving in place."
    return 0
  fi

  mkdir -p "$wt/.claude"
  ln -sfn "$src" "$dst"
}

# merge_main_if_behind <worktree_path>
#
# If main has commits the worktree branch does not, merge main into the
# worktree branch with `--no-edit`. If the merge fails (conflicts), abort
# it and exit non-zero — the operator resolves manually before re-running.
merge_main_if_behind() {
  local wt="$1" main_sha base
  main_sha="$(git -C "$REPO_ROOT" rev-parse main)"
  base="$(git -C "$wt" merge-base HEAD main 2>/dev/null || true)"
  if [[ "$base" == "$main_sha" ]]; then
    return 0
  fi
  printf 'Worktree is behind main; merging main into worktree branch...\n' >&2
  if ! git -C "$wt" merge --no-edit main >&2; then
    git -C "$wt" merge --abort >/dev/null 2>&1 || true
    err "auto-merge of main into worktree failed (conflicts).
   Resolve manually in: $wt
   Then re-run: scripts/agentctl.sh run <task-id>"
    exit 1
  fi
}

build_worktree_header() {
  local worktree_path="$1" main_path="$2"
  if [[ -n "$worktree_path" && "$worktree_path" != "$main_path" ]]; then
    cat <<EOH
You are operating in this task worktree:
${worktree_path}

Do not edit the main checkout:
${main_path}

All file edits, file creation, test runs, and verification commands must
happen inside the task worktree path above. If you find yourself writing
files into the main checkout, stop and recheck your current working
directory.
EOH
  else
    cat <<EOH
You are operating directly in the main checkout:
${main_path}

This task targets main; there is no separate worktree.
EOH
  fi
}

build_run_prompt() {
  local task_id="$1" task_file="$2" worktree_path="${3:-}" main_path="${4:-$REPO_ROOT}"
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are executing agent task ${task_id}.

${header}

Read the task file below and execute it exactly. Do not exceed scope.

Required behavior:
- Read every background doc the task references.
- Stay within the task's stated scope; do not implement adjacent features.
- Touch only files inside the task's allowed_paths.
- Respect existing ADRs and contracts under docs/.
- Run every verification command listed in the task.
- Stage and commit your changes locally with the commit message the task specifies.
- Do not push.
- Do not modify agent_tasks/queue.yaml status fields; the user will mark the task done after review.

Task file: ${task_file}

----- BEGIN TASK FILE -----
$(cat "$task_file")
----- END TASK FILE -----
EOF
}

build_run_interactive_prompt() {
  local task_id="$1" task_file="$2" worktree_path="${3:-}" main_path="${4:-$REPO_ROOT}"
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are executing agent task ${task_id}.

${header}

You are running in interactive supervised mode.

Read and execute the task exactly. Stay within scope, obey allowed/forbidden paths, and do not make unrelated changes.

Implement the requested changes and run the verification commands listed in the task.

After verification, show:
- git status --short
- git diff --stat
- git diff --name-only
- test/verification results

Do not stage or commit yet.

Stop and ask the user to type "commit" before staging changes and committing with the exact commit message required by the task. Do not push.

Task file: ${task_file}

----- BEGIN TASK FILE -----
$(cat "$task_file")
----- END TASK FILE -----
EOF
}

build_review_prompt() {
  local task_id="$1" task_file="$2" worktree_path="${3:-}" main_path="${4:-$REPO_ROOT}"
  local artifact_path="$5"
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are reviewing agent task ${task_id}.

${header}

Exception to "do not edit main": you MUST write exactly one file — the
structured review artifact at the absolute path:

  ${artifact_path}

You may not edit any other file anywhere. You may not stage or commit.
You may not push.

Check the most recent commit(s) on the task branch and assess:
- Did the implementation stay within the task's scope?
- Were the task's allowed_paths respected? Flag any files changed outside them.
- Were the relevant ADRs in docs/adr/ respected?
- Are the tests meaningful (covering the behavior the task specifies) or thin?
- Was anything overbuilt beyond what the task asked for?
- Were unrelated files changed?
- Is the commit message appropriate and matches what the task required?
- Did verification actually run? Is the task worktree clean? Does the task
  branch have at least one commit beyond main?

You must end with exactly one verdict:
APPROVE, APPROVE_WITH_NOTES, REQUEST_CHANGES, REJECT, or BLOCKED.

Verdict semantics:

  APPROVE              The task satisfies the spec. It may be completed.
  APPROVE_WITH_NOTES   The task satisfies the spec. Notes are optional
                       follow-ups and do not block completion.
  REQUEST_CHANGES      The task is close but misses required behavior,
                       acceptance criteria, verification, scope, or tests.
                       It must be fixed before completion.
  REJECT               The implementation is wrong enough that it should
                       not be patched casually. The operator should abort,
                       reset, or rewrite the task.
  BLOCKED              The review could not make a decision because
                       verification did not run, the task branch is dirty,
                       the task spec is ambiguous, dependencies are
                       missing, or the branch has no commit.

A caveat that violates acceptance criteria is REQUEST_CHANGES, not
APPROVE_WITH_NOTES.
A caveat that is purely optional is APPROVE_WITH_NOTES.
If verification did not run or the branch is dirty, use BLOCKED unless the
task explicitly allows that state.

Required fixes must be concrete and actionable.
Optional notes must not block completion.
Do not use vague verdicts like "conditional pass" — map to one of the
allowed verdicts above.

Write the artifact in this exact format (front matter + sections):

  ---
  task_id: "${task_id}"
  verdict: "<ONE OF: APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | REJECT | BLOCKED>"
  reviewed_at: "<ISO 8601 UTC timestamp, e.g. 2026-05-24T12:34:56Z>"
  reviewer: "claude-code"
  ---

  # Review: ${task_id}

  ## Verdict

  <THE VERDICT AGAIN, ON ITS OWN LINE>

  ## Required fixes

  - <one bullet per concrete fix; required only when verdict is
    REQUEST_CHANGES, REJECT, or BLOCKED. Use "None." if no required fixes.>

  ## Optional notes

  - <one bullet per optional follow-up. Use "None." if there are none.>

  ## Evidence checked

  - <commits inspected, files inspected, verification output observed>

  ## Scope / allowed-path check

  <free-form summary of whether allowed_paths were respected>

  ## Verification status

  <did the listed verification commands actually run; were they green;
   was the task worktree clean; did the task branch contain a commit>

Task file: ${task_file}

----- BEGIN TASK FILE -----
$(cat "$task_file")
----- END TASK FILE -----
EOF
}

cmd_run() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh run <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  # Validate task exists and gather metadata.
  local status task_file worktree
  status="$(yaml_query status_of "$task_id")"
  task_file="$(yaml_query field "$task_id" file)"
  worktree="$(yaml_query field "$task_id" worktree)"

  [[ -n "$task_file" ]] || die "task '$task_id' has no 'file' field"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  local abs_task_file="$REPO_ROOT/$task_file"
  [[ -f "$abs_task_file" ]] || die "task file not found: $abs_task_file"

  if [[ "$status" == "done" ]]; then
    err "task '$task_id' is already marked done; refusing to re-run"
    exit 1
  fi

  check_dependencies "$task_id"
  ensure_clean_worktree

  local wt_path=""
  if [[ "$worktree" != "main" ]]; then
    wt_path="$(ensure_worktree "$worktree")"
    merge_main_if_behind "$wt_path"
    propagate_claude_permissions "$wt_path"
  fi

  local launch_dir="$REPO_ROOT"
  [[ -n "$wt_path" ]] && launch_dir="$wt_path"

  local prompt
  prompt="$(build_run_prompt "$task_id" "$abs_task_file" "$wt_path" "$REPO_ROOT")"

  printf 'Starting Claude Code for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path: %s\n' "$wt_path"
  printf '  launch dir: %s\n' "$launch_dir"
  printf '  permission-mode: %s\n' "$CLAUDE_PERMISSION_MODE"

  # Launch Claude from inside the task worktree path. The explicit cd is the
  # authoritative isolation mechanism; --worktree is passed too for builds
  # that honor it, but we do not rely on it alone (see
  # docs/contracts/agent_orchestration.md - "Worktree Isolation").
  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_PERMISSION_MODE" \
      -p "$prompt" ); then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nAgent finished. Recent commits:\n'
  git -C "$launch_dir" log --oneline -5
  printf '\nGit status:\n'
  git -C "$launch_dir" status --short
  printf '\nNext: scripts/agentctl.sh review %s\n' "$task_id"
}

cmd_review() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh review <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local task_file worktree
  task_file="$(yaml_query field "$task_id" file)"
  worktree="$(yaml_query field "$task_id" worktree)"

  [[ -n "$task_file" ]] || die "task '$task_id' has no 'file' field"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  local abs_task_file="$REPO_ROOT/$task_file"
  [[ -f "$abs_task_file" ]] || die "task file not found: $abs_task_file"

  local wt_path=""
  if [[ "$worktree" != "main" ]]; then
    wt_path="$(worktree_path "$worktree")"
    if [[ -z "$wt_path" ]]; then
      err "task worktree '$worktree' does not exist; cannot review."
      err "Create or restore it with: scripts/agentctl.sh sync $task_id"
      exit 1
    fi
    propagate_claude_permissions "$wt_path"
  fi

  local launch_dir="$REPO_ROOT"
  [[ -n "$wt_path" ]] && launch_dir="$wt_path"

  ensure_reviews_dir "$task_id"
  local artifact_path
  artifact_path="$(review_artifact_path "$task_id")"

  local prompt
  prompt="$(build_review_prompt "$task_id" "$abs_task_file" "$wt_path" "$REPO_ROOT" "$artifact_path")"

  printf 'Starting Claude Code review for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path: %s\n' "$wt_path"
  printf '  launch dir: %s\n' "$launch_dir"
  printf '  permission-mode: %s\n' "$CLAUDE_REVIEW_PERMISSION_MODE"
  printf '  review artifact: %s\n' "$artifact_path"

  # Launch from inside the task worktree path (see cmd_run for rationale).
  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_REVIEW_PERMISSION_MODE" \
      -p "$prompt" ); then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nReview session ended.\n'
  local status
  status="$(review_artifact_status "$task_id")"
  case "$status" in
    missing)
      err "no review artifact was written at $artifact_path"
      err "complete will refuse until you re-run review or pass --skip-review."
      ;;
    invalid:*)
      err "review artifact present but ${status#invalid:}"
      err "Edit the artifact to include a valid verdict before running complete."
      ;;
    ok:*)
      printf '  verdict:  %s\n' "${status#ok:}"
      printf '  artifact: %s\n' "$artifact_path"
      printf '\nNext: scripts/agentctl.sh review-status %s\n' "$task_id"
      ;;
  esac
}

cmd_sync() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh sync <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local worktree
  worktree="$(yaml_query field "$task_id" worktree)"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  if [[ "$worktree" == "main" ]]; then
    printf 'task %s targets main; nothing to sync.\n' "$task_id"
    return 0
  fi

  local wt_path
  wt_path="$(ensure_worktree "$worktree")"

  if [[ -n "$(git -C "$wt_path" status --porcelain)" ]]; then
    err "worktree '$wt_path' is not clean; commit or stash before syncing:"
    git -C "$wt_path" status --short >&2
    exit 1
  fi

  merge_main_if_behind "$wt_path"
  propagate_claude_permissions "$wt_path"

  printf 'Worktree for %s is in sync with main.\n' "$task_id"
  printf '  worktree-path: %s\n' "$wt_path"
}

# branch_merged_into_main <branch>
#
# Exit 0 if <branch> exists and is reachable from main (i.e. already merged
# into main, or main is at/ahead of the branch tip). Exit 1 if the branch
# exists but is not yet merged. Exit 0 if the branch does not exist locally
# — we treat a missing branch as already cleaned up post-merge.
branch_merged_into_main() {
  local branch="$1"
  if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null; then
    return 0
  fi
  git -C "$REPO_ROOT" merge-base --is-ancestor "$branch" main
}

# branch_has_commits_beyond_main <branch>
#
# Exit 0 if <branch> exists and has at least one commit not reachable from
# main. Exit 1 otherwise (branch missing, or branch tip is on/behind main).
branch_has_commits_beyond_main() {
  local branch="$1" count
  if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null; then
    return 1
  fi
  count="$(git -C "$REPO_ROOT" rev-list --count "main..refs/heads/$branch" 2>/dev/null || echo 0)"
  [[ "${count:-0}" -gt 0 ]]
}

# detect_shadow_files <main_wt> <branch>
#
# Print, one per line, the paths of files in <main_wt> that are currently
# untracked there but already tracked in <branch>. These are the files most
# likely to have leaked out of the task worktree into the main checkout.
#
# Prints nothing (and exits 0) when <branch> is empty, does not exist, or
# the intersection is empty. Never modifies any files.
detect_shadow_files() {
  local main_wt="$1" branch="$2"
  [[ -n "$branch" ]] || return 0
  if ! git -C "$main_wt" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null; then
    return 0
  fi
  local untracked
  untracked="$(git -C "$main_wt" ls-files --others --exclude-standard)"
  [[ -n "$untracked" ]] || return 0
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if git -C "$main_wt" cat-file -e "refs/heads/$branch:$f" 2>/dev/null; then
      printf '%s\n' "$f"
    fi
  done <<< "$untracked"
}

# print_indented_list <heading> <input>
#
# Helper: print a heading on stderr followed by each non-empty line of
# <input> indented by two spaces. No-op if <input> is empty.
print_indented_list() {
  local heading="$1" input="$2"
  [[ -n "$input" ]] || return 0
  printf '\n%s\n' "$heading" >&2
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    printf '  %s\n' "$line" >&2
  done <<< "$input"
}

# report_dirty_main <main_wt> <branch>
#
# Print a grouped diagnostic when the main worktree is dirty. Splits the
# output into tracked changes, untracked files, and likely shadow files
# from the task branch. Suggests targeted cleanup commands.
report_dirty_main() {
  local main_wt="$1" branch="$2"
  local tracked untracked shadow

  tracked="$(git -C "$main_wt" status --porcelain \
              | awk '$1 !~ /^\?\?$/ { sub(/^...[[:space:]]*/, ""); print }')"
  untracked="$(git -C "$main_wt" ls-files --others --exclude-standard)"
  shadow="$(detect_shadow_files "$main_wt" "$branch")"

  err "main worktree is not clean ($main_wt); commit or stash before completing."

  print_indented_list "Tracked changes:" "$tracked"
  print_indented_list "Untracked files:" "$untracked"

  if [[ -n "$shadow" ]]; then
    print_indented_list "Possible shadow files from task branch ($branch):" "$shadow"
    printf '\n' >&2
    printf 'Main contains untracked files that are already present in the task branch.\n' >&2
    printf 'These are likely leaked task-worktree files.\n' >&2
    printf '\nSuggested cleanup:\n\n' >&2
    printf '  git -C %s clean -f --' "$main_wt" >&2
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      printf ' %q' "$line" >&2
    done <<< "$shadow"
    printf '\n\n' >&2
    printf 'Or re-run complete with the optional flag:\n\n' >&2
    printf '  scripts/agentctl.sh complete <task-id> --clean-shadow-files\n\n' >&2
    printf 'The flag only removes the exact untracked files listed above.\n' >&2
    printf 'It does not run a broad git clean.\n' >&2
  fi
}

# clean_shadow_files <main_wt> <branch>
#
# Remove the exact files reported by detect_shadow_files using
# `git clean -f -- <path>` per file. Never runs a broad clean; never
# touches modified tracked files; never recurses into directories.
# Returns 0 if there were no shadow files or every removal succeeded.
clean_shadow_files() {
  local main_wt="$1" branch="$2" shadow
  shadow="$(detect_shadow_files "$main_wt" "$branch")"
  if [[ -z "$shadow" ]]; then
    printf 'No shadow files to clean in %s.\n' "$main_wt" >&2
    return 0
  fi
  printf 'Removing shadow files in %s (untracked here, tracked in %s):\n' \
    "$main_wt" "$branch" >&2
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    printf '  %s\n' "$f" >&2
  done <<< "$shadow"
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if ! git -C "$main_wt" clean -f -- "$f" >&2; then
      err "failed to remove shadow file: $f"
      return 1
    fi
  done <<< "$shadow"
}

# reviews_dir <task-id>
#
# Print the absolute path of the .agentctl/reviews/ directory that owns
# <task-id>'s review artifact. The directory lives inside the task's
# worktree so that `review` (which runs in the task worktree), `complete`
# (which runs in main but resolves the task worktree), and `fix` (which
# runs in the task worktree) all coordinate through one path. For tasks
# whose `worktree` field is `main`, the directory is in the main
# checkout. Falls back to the main checkout if the task worktree is not
# yet registered with git.
reviews_dir() {
  local task_id="$1"
  local worktree wt_path main_wt
  worktree="$(yaml_query field "$task_id" worktree 2>/dev/null || true)"
  if [[ -n "$worktree" && "$worktree" != "main" ]]; then
    wt_path="$(worktree_path "$worktree")"
    if [[ -n "$wt_path" ]]; then
      printf '%s/.agentctl/reviews\n' "$wt_path"
      return 0
    fi
  fi
  main_wt="$(find_main_worktree)" || return 1
  printf '%s/.agentctl/reviews\n' "$main_wt"
}

# review_artifact_path <task-id>
#
# Print the absolute path of <task-id>'s review artifact. Does not check
# whether the file exists.
review_artifact_path() {
  local task_id="$1" dir
  dir="$(reviews_dir "$task_id")" || return 1
  printf '%s/%s.md\n' "$dir" "$task_id"
}

# ensure_reviews_dir <task-id>
#
# Create <task-id>'s .agentctl/reviews/ directory if it does not yet
# exist. Idempotent; never touches existing files.
ensure_reviews_dir() {
  local task_id="$1" dir
  dir="$(reviews_dir "$task_id")" || return 1
  mkdir -p "$dir"
}

# read_review_field <task-id> <field>
#
# Parse the YAML front matter of the review artifact and print the value of
# <field>. Returns empty (exit 0) if the artifact is missing, lacks front
# matter, or has no such field. Never errors on absence — callers
# distinguish missing-artifact from missing-field by also checking the file
# path. The parser is intentionally permissive about quoting so reviewers
# may write `verdict: APPROVE` or `verdict: "APPROVE"` interchangeably.
read_review_field() {
  local task_id="$1" field="$2"
  local path
  path="$(review_artifact_path "$task_id" 2>/dev/null)" || return 0
  [[ -n "$path" ]] || return 0
  [[ -f "$path" ]] || return 0
  require_python_yaml
  CLAUDE_REVIEW_PATH="$path" CLAUDE_REVIEW_FIELD="$field" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os, sys, yaml

path = os.environ["CLAUDE_REVIEW_PATH"]
field = os.environ["CLAUDE_REVIEW_FIELD"]
with open(path, "r", encoding="utf-8") as fh:
    text = fh.read()
if not text.startswith("---"):
    sys.exit(0)
end = text.find("\n---", 3)
if end < 0:
    sys.exit(0)
fm = text[3:end].strip()
try:
    data = yaml.safe_load(fm) or {}
except Exception:
    sys.exit(0)
val = data.get(field)
if val is None:
    sys.exit(0)
print(str(val).strip())
PYEOF
}

# read_review_section <task-id> <heading>
#
# Print the body of a markdown section under "## <heading>" from the
# review artifact. Stops at the next "## " heading or end of file. Returns
# empty (exit 0) if the artifact or section is missing.
read_review_section() {
  local task_id="$1" heading="$2"
  local path
  path="$(review_artifact_path "$task_id" 2>/dev/null)" || return 0
  [[ -n "$path" ]] || return 0
  [[ -f "$path" ]] || return 0
  CLAUDE_REVIEW_PATH="$path" CLAUDE_REVIEW_HEADING="$heading" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os, re, sys

path = os.environ["CLAUDE_REVIEW_PATH"]
heading = os.environ["CLAUDE_REVIEW_HEADING"]
with open(path, "r", encoding="utf-8") as fh:
    lines = fh.readlines()
in_section = False
out = []
target = f"## {heading}".strip()
for line in lines:
    stripped = line.rstrip("\n")
    if not in_section:
        if stripped.strip() == target:
            in_section = True
        continue
    if stripped.startswith("## "):
        break
    out.append(stripped)
while out and out[0].strip() == "":
    out.pop(0)
while out and out[-1].strip() == "":
    out.pop()
print("\n".join(out))
PYEOF
}

# is_valid_verdict <verdict>
#
# Exit 0 if the given string is one of REVIEW_VERDICTS, non-zero otherwise.
is_valid_verdict() {
  local v="$1" allowed
  for allowed in "${REVIEW_VERDICTS[@]}"; do
    [[ "$v" == "$allowed" ]] && return 0
  done
  return 1
}

# review_artifact_status <task-id>
#
# Print one of:
#   missing                — no artifact on disk
#   invalid:<text>         — artifact present but verdict missing or unknown
#   ok:<verdict>           — artifact present with a recognized verdict
#
# Single-line output so callers can split on the first colon. Never reads
# the artifact body beyond the front matter.
review_artifact_status() {
  local task_id="$1"
  local path
  path="$(review_artifact_path "$task_id" 2>/dev/null)" || { printf 'missing\n'; return 0; }
  if [[ -z "$path" || ! -f "$path" ]]; then
    printf 'missing\n'
    return 0
  fi
  local verdict
  verdict="$(read_review_field "$task_id" verdict)"
  if [[ -z "$verdict" ]]; then
    printf 'invalid:no verdict field in front matter\n'
    return 0
  fi
  if ! is_valid_verdict "$verdict"; then
    printf 'invalid:unknown verdict %q\n' "$verdict"
    return 0
  fi
  printf 'ok:%s\n' "$verdict"
}

# enforce_review_verdict <task-id> <skip-review-flag>
#
# Print a human-readable banner describing the latest review verdict, then
# return 0 if `complete` may proceed or 1 if it must refuse.
#
# Allowed verdicts:
#   APPROVE              -> proceed
#   APPROVE_WITH_NOTES   -> proceed (with banner pointing at the notes)
#
# Refused verdicts:
#   REQUEST_CHANGES      -> refuse; print required fixes and hint at `fix`
#   REJECT               -> refuse; print rejection summary
#   BLOCKED              -> refuse; print blocker summary
#   missing artifact     -> refuse, unless <skip-review-flag> is 1
#   invalid verdict text -> refuse always; --skip-review does not bypass
#                          a present-but-broken artifact, because that is
#                          a reviewer or operator typo we want surfaced.
enforce_review_verdict() {
  local task_id="$1" skip_review="${2:-0}"
  local artifact_path status verdict required notes
  artifact_path="$(review_artifact_path "$task_id")" || return 1
  status="$(review_artifact_status "$task_id")"

  case "$status" in
    missing)
      if [[ "$skip_review" -eq 1 ]]; then
        printf '\n' >&2
        printf 'WARNING: no review artifact at %s\n' "$artifact_path" >&2
        printf 'WARNING: --skip-review was passed; proceeding without a review verdict.\n' >&2
        printf '\n' >&2
        return 0
      fi
      err "no review artifact at $artifact_path"
      err "Run 'scripts/agentctl.sh review $task_id' first, or re-run complete with --skip-review."
      return 1
      ;;
    invalid:*)
      err "review artifact present but ${status#invalid:}"
      err "Path: $artifact_path"
      err "Edit the artifact so its front matter contains a valid 'verdict:' field"
      err "(one of: ${REVIEW_VERDICTS[*]})."
      err "Note: --skip-review does not bypass a malformed artifact."
      return 1
      ;;
    ok:*)
      verdict="${status#ok:}"
      ;;
    *)
      err "internal: unrecognized review artifact status '$status'"
      return 1
      ;;
  esac

  case "$verdict" in
    APPROVE)
      printf 'Review verdict: APPROVE (%s)\n' "$artifact_path"
      return 0
      ;;
    APPROVE_WITH_NOTES)
      printf 'Review verdict: APPROVE_WITH_NOTES (%s)\n' "$artifact_path"
      notes="$(read_review_section "$task_id" "Optional notes")"
      if [[ -n "$notes" ]]; then
        printf '  Optional notes (not blocking):\n'
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          printf '    %s\n' "$line"
        done <<< "$notes"
      fi
      return 0
      ;;
    REQUEST_CHANGES)
      err "Review verdict: REQUEST_CHANGES — refusing to complete $task_id."
      err "Review artifact: $artifact_path"
      required="$(read_review_section "$task_id" "Required fixes")"
      if [[ -n "$required" ]]; then
        printf '\nRequired fixes:\n' >&2
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          printf '  %s\n' "$line" >&2
        done <<< "$required"
      fi
      printf '\nNext: scripts/agentctl.sh fix %s\n' "$task_id" >&2
      printf '      (or edit the review artifact and re-run complete.)\n' >&2
      return 1
      ;;
    REJECT)
      err "Review verdict: REJECT — refusing to complete $task_id."
      err "Review artifact: $artifact_path"
      required="$(read_review_section "$task_id" "Required fixes")"
      if [[ -n "$required" ]]; then
        printf '\nReviewer notes:\n' >&2
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          printf '  %s\n' "$line" >&2
        done <<< "$required"
      fi
      printf '\nA REJECT verdict signals the implementation should not be patched casually.\n' >&2
      printf 'Consider abandoning the task (write a new task id) or rewriting the branch.\n' >&2
      return 1
      ;;
    BLOCKED)
      err "Review verdict: BLOCKED — refusing to complete $task_id."
      err "Review artifact: $artifact_path"
      required="$(read_review_section "$task_id" "Required fixes")"
      if [[ -n "$required" ]]; then
        printf '\nBlocker summary:\n' >&2
        while IFS= read -r line; do
          [[ -z "$line" ]] && continue
          printf '  %s\n' "$line" >&2
        done <<< "$required"
      fi
      printf '\nResolve the blocker (run verification, commit work, clarify spec, etc.)\n' >&2
      printf 'and re-run review.\n' >&2
      return 1
      ;;
    *)
      err "internal: unhandled verdict '$verdict'"
      return 1
      ;;
  esac
}

# find_main_worktree
#
# Print the absolute path of the worktree whose checked-out branch is `main`.
# Exits non-zero with a clear error if no such worktree is registered.
find_main_worktree() {
  local path
  path="$(git -C "$REPO_ROOT" worktree list --porcelain \
    | awk '
        /^worktree / { wt=$2; next }
        /^branch refs\/heads\/main$/ { print wt; exit }
      ')"
  if [[ -z "$path" ]]; then
    err "could not find a worktree on branch main; complete needs the main checkout."
    return 1
  fi
  printf '%s\n' "$path"
}

# --- verification state -----------------------------------------------------
#
# The verification state file records the outcome of the most recent
# `complete`-driven verification run for a task. It lives in the main
# checkout (single canonical location, accessible to both `complete` and
# `fix`) at:
#
#   <main_wt>/.agentctl/verifications/<task-id>.md
#
# Format mirrors review artifacts: YAML front matter with `task_id`,
# `status` (one of "passed" or "failed"), `exit_code`, and `recorded_at`,
# followed by markdown sections "## Failing command" and (on failure)
# "## Failure excerpt". The file is harness-owned, never committed; the
# `complete` dirty-main filter ignores untracked files under the
# verifications dir.

# verifications_dir
#
# Print the absolute path of the .agentctl/verifications/ directory in
# the main checkout. Verification state is centralized there (not in the
# task worktree) so both `complete` (running in main) and `fix`
# (resolving from main) coordinate through one path.
verifications_dir() {
  local main_wt
  main_wt="$(find_main_worktree)" || return 1
  printf '%s/.agentctl/verifications\n' "$main_wt"
}

# verification_state_path <task-id>
verification_state_path() {
  local task_id="$1" dir
  dir="$(verifications_dir)" || return 1
  printf '%s/%s.md\n' "$dir" "$task_id"
}

# ensure_verifications_dir
ensure_verifications_dir() {
  local dir
  dir="$(verifications_dir)" || return 1
  mkdir -p "$dir"
}

# read_verification_field <task-id> <field>
#
# Parse the YAML front matter of the verification state file and print
# the value of <field>. Returns empty (exit 0) when missing.
read_verification_field() {
  local task_id="$1" field="$2"
  local path
  path="$(verification_state_path "$task_id" 2>/dev/null)" || return 0
  [[ -n "$path" ]] || return 0
  [[ -f "$path" ]] || return 0
  require_python_yaml
  CLAUDE_VERIF_PATH="$path" CLAUDE_VERIF_FIELD="$field" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os, sys, yaml
path = os.environ["CLAUDE_VERIF_PATH"]
field = os.environ["CLAUDE_VERIF_FIELD"]
with open(path, "r", encoding="utf-8") as fh:
    text = fh.read()
if not text.startswith("---"):
    sys.exit(0)
end = text.find("\n---", 3)
if end < 0:
    sys.exit(0)
fm = text[3:end].strip()
try:
    data = yaml.safe_load(fm) or {}
except Exception:
    sys.exit(0)
val = data.get(field)
if val is None:
    sys.exit(0)
print(str(val).rstrip())
PYEOF
}

# read_verification_section <task-id> <heading>
#
# Print the body of the named "## <heading>" section from the
# verification state file.
read_verification_section() {
  local task_id="$1" heading="$2"
  local path
  path="$(verification_state_path "$task_id" 2>/dev/null)" || return 0
  [[ -n "$path" ]] || return 0
  [[ -f "$path" ]] || return 0
  CLAUDE_VERIF_PATH="$path" CLAUDE_VERIF_HEADING="$heading" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os
path = os.environ["CLAUDE_VERIF_PATH"]
heading = os.environ["CLAUDE_VERIF_HEADING"]
with open(path, "r", encoding="utf-8") as fh:
    lines = fh.readlines()
in_section = False
out = []
target = f"## {heading}".strip()
for line in lines:
    stripped = line.rstrip("\n")
    if not in_section:
        if stripped.strip() == target:
            in_section = True
        continue
    if stripped.startswith("## "):
        break
    out.append(stripped)
while out and out[0].strip() == "":
    out.pop(0)
while out and out[-1].strip() == "":
    out.pop()
print("\n".join(out))
PYEOF
}

# verification_state_status <task-id>
#
# Print one of:
#   missing            — no state file on disk
#   invalid:<reason>   — file present but front matter malformed
#   ok:passed          — file says verification passed
#   ok:failed          — file says verification failed
verification_state_status() {
  local task_id="$1"
  local path
  path="$(verification_state_path "$task_id" 2>/dev/null)" \
    || { printf 'missing\n'; return 0; }
  if [[ -z "$path" || ! -f "$path" ]]; then
    printf 'missing\n'
    return 0
  fi
  local status
  status="$(read_verification_field "$task_id" status)"
  if [[ -z "$status" ]]; then
    printf 'invalid:no status field in front matter\n'
    return 0
  fi
  case "$status" in
    passed|failed)
      printf 'ok:%s\n' "$status"
      ;;
    *)
      printf 'invalid:unknown status %s\n' "$status"
      ;;
  esac
}

# write_verification_state <task-id> <status> [failing-command] [exit-code] [excerpt]
#
# Overwrite the verification state file for a task. <status> must be one
# of "passed" or "failed". For "failed", <failing-command>, <exit-code>,
# and <excerpt> are recorded; for "passed" they are ignored.
write_verification_state() {
  local task_id="$1" status="$2"
  local failing_command="${3:-}" exit_code="${4:-0}" excerpt="${5:-}"
  ensure_verifications_dir || return 1
  local path
  path="$(verification_state_path "$task_id")" || return 1
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    printf -- '---\n'
    printf 'task_id: "%s"\n' "$task_id"
    printf 'status: "%s"\n' "$status"
    printf 'exit_code: %s\n' "$exit_code"
    printf 'recorded_at: "%s"\n' "$ts"
    printf -- '---\n\n'
    printf '# Verification: %s\n\n' "$task_id"
    if [[ "$status" == "failed" ]]; then
      printf '## Failing command\n\n'
      if [[ -n "$failing_command" ]]; then
        printf '%s\n\n' "$failing_command"
      else
        printf '(unknown)\n\n'
      fi
      printf '## Failure excerpt\n\n'
      printf '```\n'
      if [[ -n "$excerpt" ]]; then
        printf '%s\n' "$excerpt"
      else
        printf '(no output captured)\n'
      fi
      printf '```\n'
    else
      printf '## Status\n\nverification passed at %s.\n' "$ts"
    fi
  } > "$path"
}

# prepare_node_workspaces <dir> <task-id>
#
# Some task worktrees do not yet have node_modules installed. If the task's
# verification commands reference the `frontend` or `extension` workspace,
# run `npm install` in that workspace inside <dir> before verification runs.
#
# Safety: only installs in workspaces the verification commands actually
# reference, and only when the expected install marker is missing. Never
# runs `npm install` globally, and never touches unrelated directories.
prepare_node_workspaces() {
  local dir="$1" task_id="$2" cmd needs_frontend=0 needs_extension=0
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    if [[ "$cmd" =~ (^|[[:space:]/])frontend($|[[:space:]/]) ]]; then
      needs_frontend=1
    fi
    if [[ "$cmd" =~ (^|[[:space:]/])extension($|[[:space:]/]) ]]; then
      needs_extension=1
    fi
  done < <(yaml_query field "$task_id" verification)

  if [[ "$needs_frontend" -eq 1 \
        && -d "$dir/frontend" \
        && ! -x "$dir/frontend/node_modules/.bin/vitest" ]]; then
    printf 'Preparing frontend workspace (npm install in %s/frontend)\n' "$dir" >&2
    if ! (cd "$dir/frontend" && npm install); then
      err "npm install failed in $dir/frontend"
      return 1
    fi
  fi

  if [[ "$needs_extension" -eq 1 \
        && -d "$dir/extension" \
        && ! -d "$dir/extension/node_modules" ]]; then
    printf 'Preparing extension workspace (npm install in %s/extension)\n' "$dir" >&2
    if ! (cd "$dir/extension" && npm install); then
      err "npm install failed in $dir/extension"
      return 1
    fi
  fi
  return 0
}

# run_verification_commands <dir> <task-id>
#
# Run every command in the task's `verification` list inside <dir>. Prints
# each command to stderr before running it. Returns the first non-zero exit
# status; returns 0 if all commands succeed.
#
# Side effect: writes the outcome to the verification state file (see
# write_verification_state). On failure the state file records the failing
# command, exit code, and the tail of its combined stdout/stderr so that
# `fix` can launch a verification-failure repair without re-running the
# commands. On success the state file is overwritten with status=passed.
run_verification_commands() {
  local dir="$1" task_id="$2" cmd ran=0 logfile rc
  logfile="$(mktemp)"
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    ran=1
    printf '  $ %s\n' "$cmd" >&2
    : > "$logfile"
    rc=0
    # Stream the command's combined stdout/stderr to both the operator
    # (via stderr) and a log file we keep for the verification state.
    # `pipefail` is toggled off so a failing command does not propagate
    # through `tee` and trip `set -e` before we capture PIPESTATUS.
    set +o pipefail
    ( cd "$dir" && bash -c "$cmd" ) 2>&1 | tee "$logfile" >&2
    rc=${PIPESTATUS[0]}
    set -o pipefail
    if [[ "$rc" -ne 0 ]]; then
      err "verification command failed in $dir: $cmd"
      local excerpt
      excerpt="$(tail -n 80 "$logfile")"
      write_verification_state "$task_id" "failed" "$cmd" "$rc" "$excerpt" \
        || err "warning: could not record verification failure state for $task_id"
      rm -f "$logfile"
      return 1
    fi
  done < <(yaml_query field "$task_id" verification)
  rm -f "$logfile"
  if [[ "$ran" -eq 0 ]]; then
    printf '  (task %s has no verification commands)\n' "$task_id" >&2
    return 0
  fi
  write_verification_state "$task_id" "passed" \
    || err "warning: could not record verification passed state for $task_id"
  return 0
}

# update_queue_statuses <task-id> <dry-run-flag>
#
# In a single pass over queue.yaml:
#   - Mark <task-id> as "done".
#   - Promote any task whose status is "planned" and whose dependencies are
#     all "done" (after applying the change above) to "ready".
#
# Performs an in-place text edit so YAML comments and quoting are preserved.
# When <dry-run-flag> is "1" the edits are computed but the file is left
# untouched.
#
# Prints the newly-promoted task ids on stdout (one per line) so callers can
# capture them with `mapfile`. Human-readable transitions are written to
# stderr.
update_queue_statuses() {
  local task_id="$1" dry_run="$2"
  require_queue
  require_python_yaml
  CLAUDE_QUEUE_FILE="$QUEUE_FILE" \
  CLAUDE_TASK_ID="$task_id" \
  CLAUDE_DRY_RUN="$dry_run" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os, re, sys, yaml

path    = os.environ["CLAUDE_QUEUE_FILE"]
task_id = os.environ["CLAUDE_TASK_ID"]
dry_run = os.environ["CLAUDE_DRY_RUN"] == "1"

with open(path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
tasks = data.get("tasks") or []
by_id = {t.get("id"): t for t in tasks}

if task_id not in by_id:
    sys.stderr.write(f"error: unknown task id: {task_id}\n")
    sys.exit(2)

# Compute target statuses. Start by marking the completing task done, then
# walk planned tasks to see which become eligible for promotion.
new_status = {task_id: "done"}

def status_after(tid):
    if tid in new_status:
        return new_status[tid]
    t = by_id.get(tid)
    return t.get("status", "") if t else ""

promoted = []
for t in tasks:
    if t.get("status") != "planned":
        continue
    deps = t.get("depends_on") or []
    if all(status_after(d) == "done" for d in deps):
        pid = t.get("id")
        promoted.append(pid)
        new_status[pid] = "ready"

# Apply text edits.
with open(path, "r", encoding="utf-8") as fh:
    lines = fh.readlines()

id_pat     = re.compile(r'^\s*-\s*id:\s*["\']?([^"\'#\s]+)["\']?\s*$')
status_pat = re.compile(r'^(\s*)status:\s*["\']?([^"\'#\s]+)["\']?\s*(#.*)?$')

pending = dict(new_status)
current_id = None
out = []
for line in lines:
    m_id = id_pat.match(line)
    if m_id:
        current_id = m_id.group(1)
        out.append(line)
        continue
    if current_id and current_id in pending:
        m_st = status_pat.match(line)
        if m_st:
            indent, old = m_st.group(1), m_st.group(2)
            new = pending.pop(current_id)
            out.append(f'{indent}status: "{new}"\n')
            sys.stderr.write(f"  {current_id}: {old} -> {new}\n")
            continue
    out.append(line)

if pending:
    for k in pending:
        sys.stderr.write(
            f"error: could not find status line for task '{k}' in {path}\n")
    sys.exit(2)

if not dry_run:
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(out)

for pid in promoted:
    print(pid)
PYEOF
}

# print_ready_tasks
#
# Print the (possibly empty) list of tasks with status=ready, formatted for
# operator-facing output.
print_ready_tasks() {
  printf '\nReady tasks:\n'
  local found=0 id status title
  while IFS=$'\t' read -r id status title; do
    [[ -z "$id" ]] && continue
    [[ "$status" == "ready" ]] || continue
    printf '  %-30s %s\n' "$id" "$title"
    found=1
  done < <(yaml_query list)
  if [[ "$found" -eq 0 ]]; then
    printf '  (no tasks with status=ready)\n'
  fi
}

# commit_queue_update <main_worktree>
#
# Stage agent_tasks/queue.yaml in the given main worktree and commit it with
# the canonical status-update commit message. No-op if there is nothing to
# commit (e.g. the file was already in the desired state).
commit_queue_update() {
  local main_wt="$1"
  git -C "$main_wt" add agent_tasks/queue.yaml
  if git -C "$main_wt" diff --cached --quiet; then
    printf 'No queue.yaml changes to commit.\n' >&2
    return 0
  fi
  git -C "$main_wt" commit -m "Update agent task statuses" >&2
}

# print_dry_run_promotions <promoted...>
#
# Emit the "would promote" line for dry-run mode.
print_dry_run_promotions() {
  if [[ "$#" -eq 0 ]]; then
    printf 'would promote (no tasks)\n'
  else
    printf 'would promote %s\n' "$*"
  fi
}

# complete_continue <task-id> <status> <worktree>
#
# Resume `complete` after the operator hand-resolved a merge conflict. If no
# merge is in progress and the branch is already merged into main, behaves
# like a normal `complete` from the post-merge point: runs verification,
# updates statuses, and commits the queue update.
complete_continue() {
  local task_id="$1" status="$2" worktree="$3"

  local main_wt
  main_wt="$(find_main_worktree)" || exit 1

  local branch=""
  if [[ "$worktree" != "main" ]]; then
    branch="worktree-$worktree"
  fi

  local in_merge=0
  if git -C "$main_wt" rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    in_merge=1
  fi

  local already_merged=0
  if [[ -z "$branch" ]] || branch_merged_into_main "$branch"; then
    already_merged=1
  fi

  if [[ "$in_merge" -eq 0 && "$already_merged" -eq 0 ]]; then
    err "no merge in progress and branch '$branch' is not merged into main."
    err "Run 'scripts/agentctl.sh complete $task_id' instead."
    exit 1
  fi

  if [[ "$in_merge" -eq 1 ]]; then
    local conflicted
    conflicted="$(git -C "$main_wt" diff --name-only --diff-filter=U)"
    if [[ -n "$conflicted" ]]; then
      err "unresolved conflicts remain in the merge:"
      printf '%s\n' "$conflicted" >&2
      err "Resolve them, 'git add' the fixed files, then re-run complete --continue."
      exit 1
    fi
  fi

  if ! prepare_node_workspaces "$main_wt" "$task_id"; then
    err "workspace preparation failed; not marking $task_id done"
    exit 1
  fi
  printf 'Running verification in %s\n' "$main_wt" >&2
  if ! run_verification_commands "$main_wt" "$task_id"; then
    err "verification failed; not marking $task_id done"
    err ""
    err "Verification failed. Run:"
    err "  scripts/agentctl.sh fix $task_id"
    exit 1
  fi

  if [[ "$in_merge" -eq 1 ]]; then
    printf 'Finalizing merge commit...\n' >&2
    if ! git -C "$main_wt" commit --no-edit >&2; then
      die "failed to finalize the merge commit; resolve in $main_wt and retry."
    fi
  fi

  if [[ "$status" == "done" ]]; then
    printf 'Task %s is already done.\n' "$task_id"
    print_ready_tasks
    return 0
  fi

  printf 'Updating queue statuses...\n' >&2
  local promoted=()
  mapfile -t promoted < <(update_queue_statuses "$task_id" 0)

  commit_queue_update "$main_wt"

  print_ready_tasks
}

cmd_complete() {
  local task_id="" dry_run=0 continue_mode=0 clean_shadow=0 skip_review=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --continue) continue_mode=1; shift ;;
      --clean-shadow-files) clean_shadow=1; shift ;;
      --skip-review) skip_review=1; shift ;;
      -*) die "usage: agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files] [--skip-review]
       agentctl.sh complete --continue <task-id>" ;;
      *)
        [[ -z "$task_id" ]] || die "complete: only one task id may be given"
        task_id="$1"; shift ;;
    esac
  done
  [[ -n "$task_id" ]] || die "usage: agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files] [--skip-review]
       agentctl.sh complete --continue <task-id>"

  if [[ "$continue_mode" -eq 1 && "$dry_run" -eq 1 ]]; then
    die "complete: --continue and --dry-run are mutually exclusive"
  fi
  if [[ "$continue_mode" -eq 1 && "$clean_shadow" -eq 1 ]]; then
    die "complete: --continue and --clean-shadow-files are mutually exclusive"
  fi
  if [[ "$continue_mode" -eq 1 && "$skip_review" -eq 1 ]]; then
    die "complete: --continue and --skip-review are mutually exclusive"
  fi

  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local status worktree
  status="$(yaml_query status_of "$task_id")"
  worktree="$(yaml_query field "$task_id" worktree)"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  if [[ "$continue_mode" -eq 1 ]]; then
    complete_continue "$task_id" "$status" "$worktree"
    return $?
  fi

  if [[ "$status" == "done" ]]; then
    printf 'Task %s is already done.\n' "$task_id"
    return 0
  fi

  local main_wt
  main_wt="$(find_main_worktree)" || exit 1

  local branch=""
  if [[ "$worktree" != "main" ]]; then
    branch="worktree-$worktree"
  fi

  # Review verdict gate. Runs before any expensive work so the operator
  # gets fast feedback. --skip-review allows proceeding when there is no
  # artifact at all, but never silences a present REQUEST_CHANGES /
  # REJECT / BLOCKED verdict; those must be addressed (see `fix`) or the
  # artifact must be edited or removed by hand.
  if ! enforce_review_verdict "$task_id" "$skip_review"; then
    exit 1
  fi

  # Optional targeted shadow-file cleanup BEFORE the dirty-main check. Only
  # removes untracked files in main that are tracked in the task branch.
  if [[ "$clean_shadow" -eq 1 && -n "$branch" ]]; then
    if [[ "$dry_run" -eq 1 ]]; then
      local shadow_preview
      shadow_preview="$(detect_shadow_files "$main_wt" "$branch")"
      if [[ -n "$shadow_preview" ]]; then
        printf 'would remove shadow files (untracked in main, tracked in %s):\n' "$branch"
        while IFS= read -r f; do
          [[ -z "$f" ]] && continue
          printf '  %s\n' "$f"
        done <<< "$shadow_preview"
      else
        printf 'would skip shadow-file cleanup (none detected)\n'
      fi
    else
      clean_shadow_files "$main_wt" "$branch" || exit 1
    fi
  fi

  # Untracked review artifacts under .agentctl/reviews/ and verification
  # state under .agentctl/verifications/ are harness-owned and must not
  # block complete. Everything else still counts as dirty.
  local dirty_after_filter
  dirty_after_filter="$(git -C "$main_wt" status --porcelain \
    | grep -v '^?? \.agentctl/reviews/' \
    | grep -v '^?? \.agentctl/verifications/' || true)"
  if [[ -n "$dirty_after_filter" ]]; then
    report_dirty_main "$main_wt" "$branch"
    exit 1
  fi

  local task_wt="$main_wt"
  if [[ -n "$branch" ]]; then
    task_wt="$(worktree_path "$worktree")"
    if [[ -z "$task_wt" ]]; then
      err "task worktree '$worktree' does not exist."
      err "Create or restore it with: scripts/agentctl.sh sync $task_id"
      exit 1
    fi
  fi

  # Determine whether the branch is already merged. A branch whose tip is
  # reachable from main (including the case where the branch tip equals main)
  # is treated as already merged — we skip the merge step.
  local already_merged=0
  if [[ -z "$branch" ]] || branch_merged_into_main "$branch"; then
    already_merged=1
  fi

  # If the branch is not already merged, it must have at least one commit
  # beyond main; otherwise there is nothing to integrate.
  if [[ "$already_merged" -eq 0 ]]; then
    if ! branch_has_commits_beyond_main "$branch"; then
      err "branch '$branch' has no commits beyond main and is not merged."
      err "Verify the agent committed its work before running complete."
      exit 1
    fi
  fi

  # Verification.
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'would run verification (in %s)\n' "$task_wt"
  else
    if ! prepare_node_workspaces "$task_wt" "$task_id"; then
      err "workspace preparation failed; not marking $task_id done"
      exit 1
    fi
    printf 'Running verification in %s\n' "$task_wt" >&2
    if ! run_verification_commands "$task_wt" "$task_id"; then
      err "verification failed; not marking $task_id done"
      err ""
      err "Verification failed. Run:"
      err "  scripts/agentctl.sh fix $task_id"
      exit 1
    fi
  fi

  # Merge.
  if [[ -n "$branch" && "$already_merged" -eq 0 ]]; then
    if [[ "$dry_run" -eq 1 ]]; then
      printf 'would merge branch %s into main\n' "$branch"
    else
      printf 'Merging %s into main (in %s)...\n' "$branch" "$main_wt" >&2
      if ! git -C "$main_wt" merge --no-ff --no-edit "$branch" >&2; then
        cat >&2 <<EOF

Merge conflict while completing $task_id.

Resolve conflicts in main, then run:

  git status
  bash -n scripts/agentctl.sh
  scripts/agentctl.sh complete --continue $task_id
EOF
        exit 1
      fi
    fi
  else
    if [[ "$dry_run" -eq 1 ]]; then
      if [[ -n "$branch" ]]; then
        printf 'would skip merge (branch %s already merged into main)\n' "$branch"
      else
        printf 'would skip merge (task targets main; no separate branch)\n'
      fi
    else
      if [[ -n "$branch" ]]; then
        printf 'Branch %s already merged into main; skipping merge.\n' "$branch" >&2
      fi
    fi
  fi

  # Status updates.
  local promoted=()
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'would mark %s done\n' "$task_id"
    mapfile -t promoted < <(update_queue_statuses "$task_id" 1 2>/dev/null)
    print_dry_run_promotions "${promoted[@]}"
    printf 'would commit queue update\n'
    return 0
  fi

  printf 'Updating queue statuses...\n' >&2
  mapfile -t promoted < <(update_queue_statuses "$task_id" 0)

  commit_queue_update "$main_wt"

  print_ready_tasks
}

# --- review-status ----------------------------------------------------------

cmd_review_status() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh review-status <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local artifact_path status verdict
  artifact_path="$(review_artifact_path "$task_id")"
  status="$(review_artifact_status "$task_id")"

  printf 'task id:        %s\n' "$task_id"
  case "$status" in
    missing)
      printf 'latest verdict: (none — no review artifact)\n'
      printf 'artifact path:  %s (does not exist)\n' "$artifact_path"
      printf '\nNext: scripts/agentctl.sh review %s\n' "$task_id"
      return 0
      ;;
    invalid:*)
      printf 'latest verdict: (invalid — %s)\n' "${status#invalid:}"
      printf 'artifact path:  %s\n' "$artifact_path"
      printf '\nEdit the artifact so its front matter contains a valid verdict\n'
      printf '(one of: %s).\n' "${REVIEW_VERDICTS[*]}"
      return 0
      ;;
    ok:*)
      verdict="${status#ok:}"
      ;;
  esac

  printf 'latest verdict: %s\n' "$verdict"
  printf 'artifact path:  %s\n' "$artifact_path"

  local required notes
  required="$(read_review_section "$task_id" "Required fixes")"
  notes="$(read_review_section "$task_id" "Optional notes")"

  printf '\nRequired fixes:\n'
  if [[ -z "$required" ]]; then
    printf '  (section missing)\n'
  else
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      printf '  %s\n' "$line"
    done <<< "$required"
  fi

  printf '\nOptional notes:\n'
  if [[ -z "$notes" ]]; then
    printf '  (section missing)\n'
  else
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      printf '  %s\n' "$line"
    done <<< "$notes"
  fi
}

# --- fix --------------------------------------------------------------------

# build_fix_prompt <task-id> <task-file> <worktree-path> <main-path> <artifact-path>
#
# Build the Claude prompt for `fix`. The prompt explicitly limits the agent
# to addressing the latest review's `Required fixes`, refuses scope
# expansion, requires verification, and asks the agent to amend the
# existing task commit when safe to do so.
build_fix_prompt() {
  local task_id="$1" task_file="$2" worktree_path="${3:-}" main_path="${4:-$REPO_ROOT}"
  local artifact_path="$5"
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are fixing agent task ${task_id} based ONLY on the latest review.

${header}

Read the review artifact first:

  ${artifact_path}

Address every item under "## Required fixes". Do not implement optional
notes unless they are trivial and clearly in-scope for this task.

Stay strictly within the task's stated scope and allowed_paths. Do not
expand scope. Do not refactor adjacent code. Do not edit files outside
allowed_paths.

After making the fix:

1. Run every command in the task's verification list.
2. If verification passes, prefer to amend the existing task commit so
   the branch keeps a single coherent commit per the original task:

     git add -A
     git commit --amend --no-edit

   If amending is not safe (for example, the original commit was already
   merged into another branch, or the fix is significant enough that an
   amend would hide important history), make a small follow-up commit
   with a short message that references the review.

3. Do NOT push.

For your reference, the task file follows.

Task file: ${task_file}

----- BEGIN TASK FILE -----
$(cat "$task_file")
----- END TASK FILE -----

For your reference, the review artifact follows.

----- BEGIN REVIEW ARTIFACT -----
$(cat "$artifact_path")
----- END REVIEW ARTIFACT -----
EOF
}

# build_fix_verification_prompt <task-id> <task-file> <worktree-path> <main-path>
#                               <state-path> <failing-command> <failure-excerpt>
#
# Build the Claude prompt for `fix` when verification failed. The prompt
# instructs the agent to diagnose and repair the failing verification
# command in the existing worktree, without bypassing or weakening tests.
build_fix_verification_prompt() {
  local task_id="$1" task_file="$2" worktree_path="${3:-}" main_path="${4:-$REPO_ROOT}"
  local state_path="$5" failing_command="${6:-(unknown)}" failure_excerpt="${7:-}"
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are repairing a VERIFICATION FAILURE for agent task ${task_id}.

${header}

Task ${task_id} passed review, but its verification commands failed when
\`scripts/agentctl.sh complete\` ran them. The recorded verification state
is at:

  ${state_path}

Failing command:

  ${failing_command}

Failure excerpt:

----- BEGIN FAILURE EXCERPT -----
${failure_excerpt}
----- END FAILURE EXCERPT -----

Repair the verification failure in the existing worktree above.

Required behavior:

- Determine whether the code under test is wrong, or whether the test
  expectation is genuinely obsolete. Read the failing test and the code
  it exercises before deciding.
- Make the smallest correct change. Stay strictly within the task's
  allowed_paths.
- Run the targeted failing test first to confirm the diagnosis and fix.
- Then run every command in the task's verification list to confirm the
  full suite is green.
- Do NOT bypass or weaken tests. Do not skip, xfail, comment out, or
  delete tests. Only adjust a test expectation if the expectation is
  genuinely obsolete, and document the reason in the commit message.
- Prefer \`git add -A && git commit --amend --no-edit\` so the task
  branch keeps one coherent commit. Fall back to a small follow-up commit
  if amending would hide important history (for example, if the original
  commit was already merged elsewhere).
- Do NOT push.
- Do NOT modify agent_tasks/queue.yaml status fields.
- Do NOT run \`scripts/agentctl.sh complete\`. The operator will re-run
  complete after this session to merge and mark the task done.

For your reference, the task file follows.

Task file: ${task_file}

----- BEGIN TASK FILE -----
$(cat "$task_file")
----- END TASK FILE -----

For your reference, the recorded verification state follows.

----- BEGIN VERIFICATION STATE -----
$(cat "$state_path" 2>/dev/null || printf '(state file unreadable)')
----- END VERIFICATION STATE -----
EOF
}

# journal_verification_fix_start <task-id> <failing-command> <failure-excerpt>
#
# Initialize a verification-fix journal file in the main checkout's
# .agentctl/journal/ directory and print its absolute path. Records the
# task id, failing command, failure excerpt, and start timestamp. Returns
# non-zero (and prints nothing) if the main checkout cannot be located.
journal_verification_fix_start() {
  local task_id="$1" failing_command="${2:-}" failure_excerpt="${3:-}"
  local main_wt
  main_wt="$(find_main_worktree 2>/dev/null)" || return 1
  local dir="$main_wt/$JOURNAL_DIR"
  mkdir -p "$dir"
  local ts path
  ts="$(date -u +%Y-%m-%dT%H%M%SZ)"
  path="$dir/${ts}-${task_id}-verification-fix.md"
  {
    printf '# Verification fix journal: %s\n\n' "$task_id"
    printf 'task_id: %s\n' "$task_id"
    printf 'command: fix %s\n' "$task_id"
    printf 'verification_failure_fix_started: yes\n'
    printf 'repair_started_at: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [[ -n "$failing_command" ]]; then
      printf 'failing_command: |\n'
      while IFS= read -r line; do
        printf '  %s\n' "$line"
      done <<< "$failing_command"
    fi
    if [[ -n "$failure_excerpt" ]]; then
      printf '\n## Failure excerpt\n\n'
      printf '%s\n' "$failure_excerpt"
    fi
  } > "$path"
  printf '%s\n' "$path"
}

# journal_verification_fix_end <journal-path> <task-id> <exit-code>
#
# Append the post-fix outcome to a verification-fix journal file. The
# post_fix_verification_result reflects the on-disk verification state
# *as written by the most recent run_verification_commands*; running
# `fix` does not itself update the state file because the agent runs
# verification inside its own session. The operator must run `complete`
# again to refresh the state.
journal_verification_fix_end() {
  local journal_path="$1" task_id="$2" rc="$3"
  {
    printf '\nrepair_completed_at: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'repair_exit_code: %s\n' "$rc"
    local verif_status
    verif_status="$(verification_state_status "$task_id" 2>/dev/null || printf missing)"
    printf 'post_fix_verification_result: %s\n' "$verif_status"
    printf 'note: run `scripts/agentctl.sh complete %s` to refresh the verification state.\n' \
      "$task_id"
  } >> "$journal_path"
}

# cmd_fix_verification_failure <task-id> <task-file> <abs-task-file>
#                              <worktree> <wt-path> <launch-dir>
#
# Launch a verification-failure repair agent. Called by cmd_fix when the
# latest verification state is "failed", regardless of review verdict.
cmd_fix_verification_failure() {
  local task_id="$1" task_file="$2" abs_task_file="$3"
  local worktree="$4" wt_path="$5" launch_dir="$6"

  # Read what we know about the failure so the operator banner and the
  # repair prompt agree.
  local state_path failing_command failure_excerpt
  state_path="$(verification_state_path "$task_id")"
  failing_command="$(read_verification_section "$task_id" "Failing command")"
  failure_excerpt="$(read_verification_section "$task_id" "Failure excerpt")"
  [[ -n "$failing_command" ]] || failing_command="(unknown)"

  # Print the verdict-context banner the task spec calls for.
  local artifact_status review_descriptor=""
  artifact_status="$(review_artifact_status "$task_id")"
  case "$artifact_status" in
    ok:*)        review_descriptor="${artifact_status#ok:}" ;;
    missing)     review_descriptor="(no review artifact yet)" ;;
    invalid:*)   review_descriptor="(invalid: ${artifact_status#invalid:})" ;;
  esac
  printf 'Latest review verdict is %s, but verification failed.\n' "$review_descriptor"
  printf 'Launching verification-failure repair agent.\n'

  local journal_path=""
  journal_path="$(journal_verification_fix_start \
    "$task_id" "$failing_command" "$failure_excerpt" 2>/dev/null || true)"

  local prompt
  prompt="$(build_fix_verification_prompt "$task_id" "$abs_task_file" \
    "$wt_path" "$REPO_ROOT" "$state_path" \
    "$failing_command" "$failure_excerpt")"

  printf 'Starting Claude Code verification-fix session for task %s\n' "$task_id"
  printf '  task file:        %s\n' "$task_file"
  printf '  worktree:         %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path:    %s\n' "$wt_path"
  printf '  launch dir:       %s\n' "$launch_dir"
  printf '  permission-mode:  %s\n' "$CLAUDE_FIX_PERMISSION_MODE"
  printf '  verification:     %s (status: failed)\n' "$state_path"
  printf '  failing command:  %s\n' "$failing_command"
  [[ -n "$journal_path" ]] && printf '  journal:          %s\n' "$journal_path"

  local rc=0
  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_FIX_PERMISSION_MODE" \
      -p "$prompt" ); then
    rc=$?
  fi

  [[ -n "$journal_path" ]] && journal_verification_fix_end "$journal_path" "$task_id" "$rc"

  if [[ "$rc" -ne 0 ]]; then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nVerification-fix session ended. Recent commits:\n'
  git -C "$launch_dir" log --oneline -5
  printf '\nGit status:\n'
  git -C "$launch_dir" status --short
  printf '\nNext: scripts/agentctl.sh complete %s\n' "$task_id"
  printf '      (complete will re-run verification and refresh the state.)\n'
}

cmd_fix() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh fix <task-id>"
  require_queue
  require_python_yaml
  task_id="$(resolve_task_id "$task_id")"

  local status task_file worktree
  status="$(yaml_query status_of "$task_id")"
  task_file="$(yaml_query field "$task_id" file)"
  worktree="$(yaml_query field "$task_id" worktree)"

  [[ -n "$task_file" ]] || die "task '$task_id' has no 'file' field"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  local abs_task_file="$REPO_ROOT/$task_file"
  [[ -f "$abs_task_file" ]] || die "task file not found: $abs_task_file"

  if [[ "$status" == "done" ]]; then
    err "task '$task_id' is already marked done; refusing to run fix."
    exit 1
  fi

  # Resolve the task worktree up front — both repair branches need it.
  local wt_path=""
  if [[ "$worktree" != "main" ]]; then
    wt_path="$(worktree_path "$worktree")"
    if [[ -z "$wt_path" ]]; then
      err "task worktree '$worktree' does not exist; cannot fix."
      err "Create or restore it with: scripts/agentctl.sh sync $task_id"
      exit 1
    fi
    propagate_claude_permissions "$wt_path"
  fi
  local launch_dir="$REPO_ROOT"
  [[ -n "$wt_path" ]] && launch_dir="$wt_path"

  # 1) Verification-failure repair takes precedence over review verdict.
  #    A task that passed review can still have a failed verification
  #    because verification runs in `complete`, after review.
  local verif_status
  verif_status="$(verification_state_status "$task_id")"
  case "$verif_status" in
    ok:failed)
      cmd_fix_verification_failure "$task_id" "$task_file" "$abs_task_file" \
        "$worktree" "$wt_path" "$launch_dir"
      return 0
      ;;
    invalid:*)
      err "verification state file present but ${verif_status#invalid:}"
      err "Path: $(verification_state_path "$task_id")"
      err "Delete or fix the state file by hand if it is wrong."
      exit 1
      ;;
    ok:passed|missing)
      :  # fall through to review-verdict logic
      ;;
  esac

  # 2) Review-feedback repair.
  local artifact_status verdict artifact_path
  artifact_path="$(review_artifact_path "$task_id")"
  artifact_status="$(review_artifact_status "$task_id")"
  case "$artifact_status" in
    missing)
      err "no review artifact at $artifact_path"
      err "Run 'scripts/agentctl.sh review $task_id' first."
      exit 1
      ;;
    invalid:*)
      err "review artifact present but ${artifact_status#invalid:}"
      err "Path: $artifact_path"
      err "Edit the artifact so its front matter contains a valid 'verdict:' field"
      err "(one of: ${REVIEW_VERDICTS[*]}) before running fix."
      exit 1
      ;;
    ok:*)
      verdict="${artifact_status#ok:}"
      ;;
  esac

  case "$verdict" in
    APPROVE|APPROVE_WITH_NOTES)
      err "latest review verdict for $task_id is $verdict; nothing to fix."
      err "Run 'scripts/agentctl.sh complete $task_id' instead."
      exit 1
      ;;
    REQUEST_CHANGES|REJECT|BLOCKED)
      :  # proceed
      ;;
    *)
      err "internal: unhandled verdict '$verdict'"
      exit 1
      ;;
  esac

  local prompt
  prompt="$(build_fix_prompt "$task_id" "$abs_task_file" "$wt_path" "$REPO_ROOT" "$artifact_path")"

  printf 'Starting Claude Code fix session for task %s\n' "$task_id"
  printf '  task file:       %s\n' "$task_file"
  printf '  worktree:        %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path:   %s\n' "$wt_path"
  printf '  launch dir:      %s\n' "$launch_dir"
  printf '  permission-mode: %s\n' "$CLAUDE_FIX_PERMISSION_MODE"
  printf '  review artifact: %s (verdict: %s)\n' "$artifact_path" "$verdict"

  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_FIX_PERMISSION_MODE" \
      -p "$prompt" ); then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nFix session ended. Recent commits:\n'
  git -C "$launch_dir" log --oneline -5
  printf '\nGit status:\n'
  git -C "$launch_dir" status --short
  printf '\nNext: scripts/agentctl.sh review %s\n' "$task_id"
}

# --- next / work ------------------------------------------------------------
#
# `next` and `work` are higher-level orchestration commands that wrap the
# existing run / review / fix / complete commands. `next` is purely
# advisory; `work` invokes the lifecycle and writes a journal entry under
# .agentctl/journal/ for every invocation.

JOURNAL_DIR=".agentctl/journal"
WORK_DEFAULT_MAX_FIX_ATTEMPTS=2
WORK_DEFAULT_MAX_TASKS=10

# select_next_ready_id
#
# Print the id of the first task with status=ready (in queue order), or an
# empty string if none exist. Never mutates anything.
select_next_ready_id() {
  yaml_query list | awk -F'\t' '$2=="ready"{print $1; exit}'
}

# init_journal_file <task-id>
#
# Create an empty journal file at .agentctl/journal/<ts>-<task-id>.md in
# the main checkout and print its absolute path. The directory is created
# if it does not exist. Filenames are timestamped so concurrent runs and
# repeat invocations do not collide.
init_journal_file() {
  local task_id="$1" main_wt
  main_wt="$(find_main_worktree)" || return 1
  local dir="$main_wt/$JOURNAL_DIR"
  mkdir -p "$dir"
  local ts path
  ts="$(date -u +%Y-%m-%dT%H%M%SZ)"
  path="$dir/${ts}-${task_id}.md"
  : > "$path"
  printf '%s\n' "$path"
}

# journal_kv <path> <key> <value>
#
# Append a single `key: value` line to the journal file.
journal_kv() {
  printf '%s: %s\n' "$2" "$3" >> "$1"
}

# journal_section <path> <heading>
#
# Append a blank line plus a markdown `## <heading>` to the journal.
journal_section() {
  printf '\n## %s\n\n' "$2" >> "$1"
}

# journal_block <path> <key> <body>
#
# Append `key: |` followed by the body indented by two spaces. Use for
# multi-line values like required-fixes summaries.
journal_block() {
  local path="$1" key="$2" body="$3"
  [[ -n "$body" ]] || return 0
  {
    printf '%s: |\n' "$key"
    while IFS= read -r line; do
      printf '  %s\n' "$line"
    done <<< "$body"
  } >> "$path"
}

# work_stop <task-id> <journal-path> <worktree> <reason> <slug> <next>
#
# Finalize the journal file and print the operator-facing Stopped block.
# Always invoked from `work_one_task`; callers should `return 1` after.
work_stop() {
  local task_id="$1" journal_path="$2" worktree="$3"
  local reason="$4" slug="$5" nxt="$6"
  local wt_path=""
  if [[ -n "$worktree" && "$worktree" != "main" ]]; then
    wt_path="$(worktree_path "$worktree" 2>/dev/null || true)"
  fi
  local end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    printf '\nend_time: %s\n' "$end_time"
    printf 'stop_reason: %s\n' "$reason"
    printf 'stop_slug: %s\n' "$slug"
    printf 'next_suggestion: %s\n' "$nxt"
  } >> "$journal_path"

  printf '\nStopped: %s\n' "$reason" >&2
  printf '\nTask:\n  %s\n' "$task_id" >&2
  if [[ -n "$wt_path" ]]; then
    printf '\nWorktree:\n  %s\n' "$wt_path" >&2
  elif [[ "$worktree" == "main" ]]; then
    printf '\nWorktree:\n  (main checkout)\n' >&2
  fi
  printf '\nJournal:\n  %s\n' "$journal_path" >&2
  printf '\nNext:\n  %s\n' "$nxt" >&2
}

# work_one_task <task-id> <dry-run> <max-fix-attempts>
#
# Run the full lifecycle for one task. Returns 0 on successful completion,
# 1 on any stop condition. All Claude-invoking subcommands run as
# subprocesses (`"$0" run|review|fix|complete <id>`) so that a failure
# does not unwind this function via set -e.
work_one_task() {
  local task_id="$1" dry_run="$2" max_fix_attempts="$3"

  task_id="$(resolve_task_id "$task_id")"

  local status worktree title task_file
  status="$(yaml_query status_of "$task_id")"
  worktree="$(yaml_query field "$task_id" worktree)"
  title="$(yaml_query field "$task_id" title)"
  task_file="$(yaml_query field "$task_id" file)"

  if [[ "$status" != "ready" ]]; then
    err "task '$task_id' is not ready (status: $status); cannot start work."
    return 1
  fi

  local main_wt main_sha
  main_wt="$(find_main_worktree)" || return 1
  main_sha="$(git -C "$main_wt" rev-parse main 2>/dev/null || echo unknown)"

  local branch=""
  [[ "$worktree" != "main" ]] && branch="worktree-$worktree"

  local journal_path
  journal_path="$(init_journal_file "$task_id")" || {
    err "could not initialize journal file"
    return 1
  }

  local start_time
  start_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    printf '# Work journal: %s\n\n' "$task_id"
    printf 'task_id: %s\n' "$task_id"
    printf 'task_title: %s\n' "$title"
    printf 'task_file: %s\n' "$task_file"
    printf 'branch: %s\n' "${branch:-(none; worktree=main)}"
    printf 'worktree: %s\n' "$worktree"
    printf 'main_commit_at_start: %s\n' "$main_sha"
    printf 'command: work %s\n' "$task_id"
    printf 'start_time: %s\n' "$start_time"
    printf 'dry_run: %s\n' "$([[ "$dry_run" -eq 1 ]] && printf yes || printf no)"
    printf 'max_fix_attempts: %d\n' "$max_fix_attempts"
  } >> "$journal_path"

  printf 'Selected task: %s\n' "$task_id"
  printf '  title:   %s\n' "$title"
  printf '  branch:  %s\n' "${branch:-(none)}"
  printf '  journal: %s\n' "$journal_path"

  # --- Stage 1: Run --------------------------------------------------------
  printf '\n[1/4] Run\n'
  journal_section "$journal_path" "Stage 1: Run"

  if [[ "$dry_run" -eq 1 ]]; then
    printf '  (dry-run) would invoke: %s run %s\n' "$0" "$task_id"
    journal_kv "$journal_path" "result" "(dry-run) skipped"
  else
    local run_rc=0
    "$0" run "$task_id" || run_rc=$?
    if [[ "$run_rc" -ne 0 ]]; then
      journal_kv "$journal_path" "result" "FAIL (exit $run_rc)"
      work_stop "$task_id" "$journal_path" "$worktree" \
        "task run did not produce a clean committed result (run exit $run_rc)" \
        "run-failed" \
        "fix the run failure above, then re-run: scripts/agentctl.sh work $task_id"
      return 1
    fi
    journal_kv "$journal_path" "result" "PASS"

    if [[ -n "$branch" ]]; then
      local wt_path
      wt_path="$(worktree_path "$worktree")"
      if [[ -z "$wt_path" ]]; then
        journal_kv "$journal_path" "post_run_check" "worktree missing"
        work_stop "$task_id" "$journal_path" "$worktree" \
          "task worktree '$worktree' missing after run" \
          "worktree-missing" \
          "scripts/agentctl.sh sync $task_id"
        return 1
      fi
      if [[ -n "$(git -C "$wt_path" status --porcelain)" ]]; then
        journal_kv "$journal_path" "post_run_check" "dirty"
        work_stop "$task_id" "$journal_path" "$worktree" \
          "task worktree is dirty after run" \
          "dirty-after-run" \
          "cd $wt_path && git status; finish, commit, or clean"
        return 1
      fi
      if ! branch_has_commits_beyond_main "$branch"; then
        journal_kv "$journal_path" "post_run_check" "no-commit"
        work_stop "$task_id" "$journal_path" "$worktree" \
          "task branch '$branch' has no commit beyond main after run" \
          "no-commit-after-run" \
          "inspect $wt_path; the agent did not commit any work"
        return 1
      fi
      journal_kv "$journal_path" "post_run_check" "clean + committed"
    fi
    printf '  PASS task branch has committed changes\n'
  fi

  # --- Stage 2 + 3: Review (+ auto-fix loop) ------------------------------
  local final_verdict="" attempt=0
  while true; do
    printf '\n[2/4] Review (attempt %d)\n' "$((attempt + 1))"
    journal_section "$journal_path" "Stage 2: Review (attempt $((attempt + 1)))"

    if [[ "$dry_run" -eq 1 ]]; then
      printf '  (dry-run) would invoke: %s review %s\n' "$0" "$task_id"
      local artifact_status
      artifact_status="$(review_artifact_status "$task_id" 2>/dev/null || printf missing)"
      case "$artifact_status" in
        ok:*)
          final_verdict="${artifact_status#ok:}"
          printf '  (dry-run) existing verdict: %s\n' "$final_verdict"
          journal_kv "$journal_path" "verdict" "(dry-run) existing: $final_verdict"
          ;;
        *)
          final_verdict="APPROVE"
          printf '  (dry-run) no existing verdict; assuming APPROVE for the would-do flow.\n'
          journal_kv "$journal_path" "verdict" "(dry-run) assumed APPROVE"
          ;;
      esac
    else
      local review_rc=0
      "$0" review "$task_id" || review_rc=$?
      if [[ "$review_rc" -ne 0 ]]; then
        journal_kv "$journal_path" "result" "FAIL (review exit $review_rc)"
        work_stop "$task_id" "$journal_path" "$worktree" \
          "review command failed (exit $review_rc)" \
          "review-subcommand-failed" \
          "scripts/agentctl.sh review $task_id"
        return 1
      fi

      local artifact_status verdict
      artifact_status="$(review_artifact_status "$task_id")"
      case "$artifact_status" in
        missing)
          journal_kv "$journal_path" "verdict" "(none — artifact missing)"
          work_stop "$task_id" "$journal_path" "$worktree" \
            "review did not produce an artifact" \
            "review-no-artifact" \
            "scripts/agentctl.sh review $task_id"
          return 1
          ;;
        invalid:*)
          journal_kv "$journal_path" "verdict" "(invalid — ${artifact_status#invalid:})"
          work_stop "$task_id" "$journal_path" "$worktree" \
            "review did not produce a structured verdict (${artifact_status#invalid:})" \
            "review-invalid-verdict" \
            "edit $(review_artifact_path "$task_id") to include a valid verdict"
          return 1
          ;;
        ok:*)
          verdict="${artifact_status#ok:}"
          journal_kv "$journal_path" "verdict" "$verdict"
          printf '  Verdict: %s\n' "$verdict"
          ;;
      esac
      final_verdict="$verdict"
    fi

    case "$final_verdict" in
      APPROVE|APPROVE_WITH_NOTES)
        break
        ;;
      REJECT)
        work_stop "$task_id" "$journal_path" "$worktree" \
          "review returned REJECT (human decision required)" \
          "verdict-REJECT" \
          "review $(review_artifact_path "$task_id"); decide whether to abandon, reset, or rewrite the task"
        return 1
        ;;
      BLOCKED)
        work_stop "$task_id" "$journal_path" "$worktree" \
          "review returned BLOCKED" \
          "verdict-BLOCKED" \
          "resolve the blocker described in $(review_artifact_path "$task_id"); then re-run scripts/agentctl.sh review $task_id"
        return 1
        ;;
      REQUEST_CHANGES)
        if [[ "$attempt" -ge "$max_fix_attempts" ]]; then
          work_stop "$task_id" "$journal_path" "$worktree" \
            "max fix attempts ($max_fix_attempts) reached for $task_id" \
            "max-fix-attempts" \
            "inspect $(review_artifact_path "$task_id"); then scripts/agentctl.sh fix $task_id manually"
          return 1
        fi
        attempt=$((attempt + 1))
        printf '\n[3/4] Fix attempt %d/%d\n' "$attempt" "$max_fix_attempts"
        journal_section "$journal_path" "Stage 3: Fix attempt $attempt"

        local required
        required="$(read_review_section "$task_id" "Required fixes" 2>/dev/null || true)"
        journal_block "$journal_path" "required_fixes" "$required"

        if [[ "$dry_run" -eq 1 ]]; then
          printf '  (dry-run) would invoke: %s fix %s\n' "$0" "$task_id"
          journal_kv "$journal_path" "result" "(dry-run) skipped"
          work_stop "$task_id" "$journal_path" "$worktree" \
            "(dry-run) would auto-fix REQUEST_CHANGES; stopping in dry-run" \
            "dry-run-stop-at-fix" \
            "scripts/agentctl.sh work $task_id  (live, not --dry-run)"
          return 0
        fi

        local fix_rc=0
        "$0" fix "$task_id" || fix_rc=$?
        if [[ "$fix_rc" -ne 0 ]]; then
          journal_kv "$journal_path" "result" "FAIL (exit $fix_rc)"
          work_stop "$task_id" "$journal_path" "$worktree" \
            "fix command failed (exit $fix_rc)" \
            "fix-failed" \
            "scripts/agentctl.sh fix $task_id  (after inspecting why)"
          return 1
        fi
        journal_kv "$journal_path" "result" "PASS"

        if [[ -n "$branch" ]]; then
          local wt_path
          wt_path="$(worktree_path "$worktree")"
          if [[ -n "$wt_path" && -n "$(git -C "$wt_path" status --porcelain)" ]]; then
            journal_kv "$journal_path" "post_fix_check" "dirty"
            work_stop "$task_id" "$journal_path" "$worktree" \
              "task worktree is dirty after fix" \
              "dirty-after-fix" \
              "cd $wt_path && git status; finish, commit, or clean"
            return 1
          fi
          journal_kv "$journal_path" "post_fix_check" "clean"
        fi
        # Fall through; loop re-reviews.
        ;;
      *)
        work_stop "$task_id" "$journal_path" "$worktree" \
          "internal: unhandled verdict '$final_verdict'" \
          "internal-error" \
          "inspect $(review_artifact_path "$task_id")"
        return 1
        ;;
    esac
  done

  # --- Stage 4: Complete ---------------------------------------------------
  printf '\n[4/4] Complete\n'
  journal_section "$journal_path" "Stage 4: Complete"

  if [[ "$dry_run" -eq 1 ]]; then
    printf '  (dry-run) would invoke: %s complete %s\n' "$0" "$task_id"
    journal_kv "$journal_path" "result" "(dry-run) skipped"
  else
    local complete_rc=0
    "$0" complete "$task_id" || complete_rc=$?
    if [[ "$complete_rc" -ne 0 ]]; then
      journal_kv "$journal_path" "result" "FAIL (exit $complete_rc)"
      work_stop "$task_id" "$journal_path" "$worktree" \
        "complete command failed (exit $complete_rc)" \
        "complete-failed" \
        "scripts/agentctl.sh complete $task_id  (after resolving the failure)"
      return 1
    fi
    journal_kv "$journal_path" "result" "PASS"
  fi

  local end_time
  end_time="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    printf '\nend_time: %s\n' "$end_time"
    printf 'stop_reason: completed normally\n'
  } >> "$journal_path"

  printf '\nDone: %s\n' "$task_id"
  printf 'Journal: %s\n' "$journal_path"
  return 0
}

# work_loop <dry-run> <max-fix-attempts> <max-tasks>
#
# --until-blocked driver. Picks the next ready task each iteration and
# runs work_one_task. Stops when no ready tasks remain, max-tasks is
# reached, or work_one_task hits a stop condition.
work_loop() {
  local dry_run="$1" max_fix_attempts="$2" max_tasks="$3"
  local count=0 next_id
  while true; do
    if [[ "$count" -ge "$max_tasks" ]]; then
      printf '\nReached --max-tasks=%d; stopping.\n' "$max_tasks"
      return 0
    fi
    next_id="$(select_next_ready_id)"
    if [[ -z "$next_id" ]]; then
      printf '\nNo ready tasks remain.\n'
      return 0
    fi
    count=$((count + 1))
    printf '\n=== work --until-blocked task %d/%d: %s ===\n' \
      "$count" "$max_tasks" "$next_id"
    if ! work_one_task "$next_id" "$dry_run" "$max_fix_attempts"; then
      printf '\nStopping --until-blocked after %d task(s).\n' "$count"
      return 1
    fi
  done
}

work_help() {
  cat <<'EOF'
agentctl.sh work - run task lifecycle with auto-fix and journaling

Usage:
  scripts/agentctl.sh work [<task-id>]
  scripts/agentctl.sh work --until-blocked
  scripts/agentctl.sh work --help

Options:
  <task-id>                Run lifecycle for this task. Must be `ready`.
                           Without an id, work picks the next ready task.
  --until-blocked          Loop over ready tasks until a stop condition.
  --max-tasks N            Cap on tasks processed in --until-blocked mode
                           (default: 10).
  --max-fix-attempts N     Cap on auto-fix attempts per task on
                           REQUEST_CHANGES (default: 2).
  --dry-run                Print what would happen without invoking
                           Claude or mutating queue.yaml.

Lifecycle per task:

  [1/4] run      scripts/agentctl.sh run <id>
  [2/4] review   scripts/agentctl.sh review <id>; read structured verdict
  [3/4] fix      on REQUEST_CHANGES: scripts/agentctl.sh fix <id>; re-review
                 up to --max-fix-attempts. APPROVE/APPROVE_WITH_NOTES
                 proceed to complete. REJECT/BLOCKED stop for human
                 judgment (never auto-fixed).
  [4/4] complete scripts/agentctl.sh complete <id>

Stop conditions print: Stopped reason, Task id, Worktree path, Journal
path, and a suggested next command. Every invocation writes a journal
file at .agentctl/journal/<timestamp>-<task-id>.md.

work never pushes, never resets, never broad-cleans, never silences a
REJECT or BLOCKED verdict, and never modifies product code itself.

See docs/contracts/agent_orchestration.md for the full contract.
EOF
}

cmd_work() {
  local task_id="" until_blocked=0 dry_run=0
  local max_fix_attempts="$WORK_DEFAULT_MAX_FIX_ATTEMPTS"
  local max_tasks="$WORK_DEFAULT_MAX_TASKS"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help) work_help; return 0 ;;
      --until-blocked) until_blocked=1; shift ;;
      --dry-run)       dry_run=1; shift ;;
      --max-fix-attempts)
        [[ -n "${2:-}" ]] || die "work: --max-fix-attempts requires a number"
        max_fix_attempts="$2"; shift 2 ;;
      --max-fix-attempts=*)
        max_fix_attempts="${1#*=}"; shift ;;
      --max-tasks)
        [[ -n "${2:-}" ]] || die "work: --max-tasks requires a number"
        max_tasks="$2"; shift 2 ;;
      --max-tasks=*)
        max_tasks="${1#*=}"; shift ;;
      -*) die "work: unknown flag: $1 (see 'work --help')" ;;
      *)
        [[ -z "$task_id" ]] || die "work: only one task id may be given"
        task_id="$1"; shift ;;
    esac
  done

  if ! [[ "$max_fix_attempts" =~ ^[0-9]+$ ]]; then
    die "work: --max-fix-attempts must be a non-negative integer (got: $max_fix_attempts)"
  fi
  if ! [[ "$max_tasks" =~ ^[0-9]+$ ]] || [[ "$max_tasks" -lt 1 ]]; then
    die "work: --max-tasks must be a positive integer (got: $max_tasks)"
  fi

  if [[ "$until_blocked" -eq 1 && -n "$task_id" ]]; then
    die "work: --until-blocked and <task-id> are mutually exclusive"
  fi

  require_queue
  require_python_yaml

  if [[ "$until_blocked" -eq 1 ]]; then
    work_loop "$dry_run" "$max_fix_attempts" "$max_tasks"
    return $?
  fi

  if [[ -z "$task_id" ]]; then
    task_id="$(select_next_ready_id)"
    if [[ -z "$task_id" ]]; then
      printf 'No ready tasks.\n'
      return 0
    fi
  fi
  work_one_task "$task_id" "$dry_run" "$max_fix_attempts"
}

# cmd_next
#
# Read-only: print the next recommended action without mutating anything.
# Surfaces tasks with REQUEST_CHANGES / REJECT / BLOCKED verdicts, dirty
# task worktrees, and (failing all of those) the next ready task or the
# fact that none exist. Also lists queue-level blocked tasks separately.
cmd_next() {
  require_queue
  require_python_yaml

  local main_wt
  main_wt="$(find_main_worktree 2>/dev/null || true)"

  local request_changes_ids=() reject_ids=() blocked_ids=()
  local id status artifact_status
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    status="$(yaml_query status_of "$id" 2>/dev/null || printf '')"
    [[ "$status" == "done" ]] && continue
    artifact_status="$(review_artifact_status "$id" 2>/dev/null || printf missing)"
    case "$artifact_status" in
      ok:REQUEST_CHANGES) request_changes_ids+=("$id") ;;
      ok:REJECT)          reject_ids+=("$id") ;;
      ok:BLOCKED)         blocked_ids+=("$id") ;;
    esac
  done < <(yaml_query ids)

  local dirty_worktrees=()
  if [[ -n "$main_wt" ]]; then
    local line wt
    while IFS= read -r line; do
      [[ "$line" =~ ^worktree[[:space:]](.+)$ ]] || continue
      wt="${BASH_REMATCH[1]}"
      [[ "$wt" == "$main_wt" ]] && continue
      if [[ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]]; then
        dirty_worktrees+=("$wt")
      fi
    done < <(git -C "$main_wt" worktree list --porcelain 2>/dev/null || true)
  fi

  local ready_id queue_blocked_ids=()
  ready_id="$(select_next_ready_id)"
  while IFS=$'\t' read -r id status _title; do
    [[ -z "$id" ]] && continue
    [[ "$status" == "blocked" ]] && queue_blocked_ids+=("$id")
  done < <(yaml_query list)

  if [[ "${#request_changes_ids[@]}" -gt 0 ]]; then
    printf 'Tasks with verdict REQUEST_CHANGES:\n'
    for id in "${request_changes_ids[@]}"; do
      printf '  scripts/agentctl.sh fix %s\n' "$id"
    done
    printf '\n'
  fi
  if [[ "${#reject_ids[@]}" -gt 0 ]]; then
    printf 'Tasks with verdict REJECT (human decision required):\n'
    for id in "${reject_ids[@]}"; do
      printf '  %s\n    artifact: %s\n' "$id" "$(review_artifact_path "$id")"
    done
    printf '\n'
  fi
  if [[ "${#blocked_ids[@]}" -gt 0 ]]; then
    printf 'Tasks with verdict BLOCKED:\n'
    for id in "${blocked_ids[@]}"; do
      printf '  %s\n    artifact: %s\n' "$id" "$(review_artifact_path "$id")"
    done
    printf '\n'
  fi
  if [[ "${#dirty_worktrees[@]}" -gt 0 ]]; then
    printf 'Dirty task worktrees (finish, commit, or clean):\n'
    local wt
    for wt in "${dirty_worktrees[@]}"; do
      printf '  %s\n' "$wt"
    done
    printf '\n'
  fi

  if [[ "${#request_changes_ids[@]}" -gt 0 ]]; then
    printf 'Next: scripts/agentctl.sh fix %s\n' "${request_changes_ids[0]}"
  elif [[ "${#reject_ids[@]}" -gt 0 ]]; then
    printf 'Next: review the REJECT verdict for %s by hand (human decision required).\n' \
      "${reject_ids[0]}"
  elif [[ "${#blocked_ids[@]}" -gt 0 ]]; then
    printf 'Next: resolve the blocker for %s and re-run scripts/agentctl.sh review %s\n' \
      "${blocked_ids[0]}" "${blocked_ids[0]}"
  elif [[ "${#dirty_worktrees[@]}" -gt 0 ]]; then
    printf 'Next: finish, commit, or clean the dirty worktree(s) above.\n'
  elif [[ -n "$ready_id" ]]; then
    printf 'Next: scripts/agentctl.sh work %s\n' "$ready_id"
  else
    printf 'No ready tasks.\n'
  fi

  if [[ "${#queue_blocked_ids[@]}" -gt 0 ]]; then
    printf '\nQueue-blocked tasks (status=blocked):\n'
    for id in "${queue_blocked_ids[@]}"; do
      printf '  %s\n' "$id"
    done
  fi
}

# --- doctor -----------------------------------------------------------------
#
# `doctor` runs a read-only preflight check of the local agent harness so
# common setup problems surface BEFORE a task is dispatched. It never
# installs anything, never runs verification commands, never mutates files,
# and never prints secrets.
#
# Reports use three severities:
#   PASS  green-path check succeeded
#   WARN  something to attend to, but not fatal (e.g. missing optional tool)
#   FAIL  blocks task execution (e.g. queue.yaml unparseable, main dirty)
#
# Exit code: 0 when there are no FAIL items (warnings only is still success);
# 1 when at least one FAIL was emitted.

DOCTOR_PASS=0
DOCTOR_WARN=0
DOCTOR_FAIL=0

doctor_pass() { printf '  PASS %s\n' "$*"; DOCTOR_PASS=$((DOCTOR_PASS+1)); }
doctor_warn() { printf '  WARN %s\n' "$*"; DOCTOR_WARN=$((DOCTOR_WARN+1)); }
doctor_fail() { printf '  FAIL %s\n' "$*"; DOCTOR_FAIL=$((DOCTOR_FAIL+1)); }

# doctor_git_checks <main_wt_out_var>
#
# Inspect git state of the main checkout and any registered task worktrees.
# Sets the named variable to the resolved main worktree path (empty string
# if the harness could not find one).
doctor_git_checks() {
  local -n _out="$1"
  _out=""
  printf 'Git\n'

  if ! command -v git >/dev/null 2>&1; then
    doctor_fail "git not found in PATH"
    printf '\n'
    return 0
  fi

  local main_wt
  if main_wt="$(find_main_worktree 2>/dev/null)" && [[ -n "$main_wt" ]]; then
    _out="$main_wt"
    doctor_pass "main worktree: $main_wt"

    local branch
    branch="$(git -C "$main_wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
    if [[ "$branch" == "main" ]]; then
      doctor_pass "main worktree on branch 'main'"
    else
      doctor_warn "main worktree HEAD is '$branch' (expected 'main')"
    fi

    if [[ -z "$(git -C "$main_wt" status --porcelain)" ]]; then
      doctor_pass "main worktree clean"
    else
      doctor_fail "main worktree is not clean"
      git -C "$main_wt" status --short | sed 's/^/    /'
    fi

    if git -C "$main_wt" rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
      doctor_fail "merge in progress in main worktree (resolve before dispatch)"
    else
      doctor_pass "no merge in progress"
    fi
  else
    doctor_fail "could not find a worktree on branch 'main'"
  fi

  # Confirm every task worktree referenced by queue.yaml that exists on
  # disk is still registered with git. A stale .claude/worktrees/<name>
  # directory after `git worktree remove` would be a confusing setup bug.
  if [[ -f "$QUEUE_FILE" ]] && "$CLAUDE_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
    local wt_names
    wt_names="$(yaml_query list 2>/dev/null | awk -F'\t' '{print $1}' \
                 | while IFS= read -r id; do
                     [[ -z "$id" ]] && continue
                     yaml_query field "$id" worktree 2>/dev/null
                   done | sort -u)"
    local missing_count=0 present_count=0 name dir_path registered
    while IFS= read -r name; do
      [[ -z "$name" || "$name" == "main" ]] && continue
      dir_path="$REPO_ROOT/.claude/worktrees/$name"
      [[ -d "$dir_path" ]] || continue
      registered="$(worktree_path "$name")"
      if [[ -z "$registered" ]]; then
        doctor_warn "directory exists but not a registered worktree: $dir_path"
        missing_count=$((missing_count + 1))
      else
        present_count=$((present_count + 1))
      fi
    done <<< "$wt_names"
    if [[ "$present_count" -gt 0 && "$missing_count" -eq 0 ]]; then
      doctor_pass "task worktrees registered with git ($present_count present)"
    fi
  fi

  printf '\n'
}

# doctor_queue_checks
#
# Parse queue.yaml and report on structural correctness. All real work is
# done by a Python helper so we can do JSON-like graph checks without
# spawning a forest of bash subshells.
doctor_queue_checks() {
  printf 'Queue\n'

  if [[ ! -f "$QUEUE_FILE" ]]; then
    doctor_fail "queue file not found: $QUEUE_FILE"
    printf '\n'
    return 0
  fi
  doctor_pass "queue file present: $QUEUE_FILE"

  if ! "$CLAUDE_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
    doctor_fail "Python interpreter '$CLAUDE_PYTHON' cannot import PyYAML"
    printf '\n'
    return 0
  fi

  local report
  if ! report="$(CLAUDE_QUEUE_FILE="$QUEUE_FILE" CLAUDE_REPO_ROOT="$REPO_ROOT" \
                 "$CLAUDE_PYTHON" - <<'PYEOF' 2>&1
import os, sys, yaml

queue_path = os.environ["CLAUDE_QUEUE_FILE"]
repo_root  = os.environ["CLAUDE_REPO_ROOT"]

try:
    with open(queue_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
except Exception as e:
    print(f"FAIL queue does not parse as YAML: {e}")
    sys.exit(0)
print("PASS queue parses as YAML")

tasks = data.get("tasks") or []
ids = [t.get("id", "") for t in tasks]
id_set = set(ids)

dups = sorted({i for i in ids if ids.count(i) > 1 and i})
if dups:
    print(f"FAIL duplicate task ids: {', '.join(dups)}")
else:
    print("PASS task ids unique")

valid = {"planned", "ready", "running", "review", "blocked", "done", "failed"}
bad_status = [(t.get("id"), t.get("status")) for t in tasks
              if t.get("status") not in valid]
if bad_status:
    for tid, st in bad_status:
        print(f"FAIL invalid status: {tid} -> {st}")
else:
    print("PASS task statuses valid")

missing_files = []
for t in tasks:
    f = t.get("file")
    if f and not os.path.isfile(os.path.join(repo_root, f)):
        missing_files.append((t.get("id"), f))
if missing_files:
    for tid, f in missing_files:
        print(f"FAIL task file missing: {tid} -> {f}")
else:
    print("PASS task files exist on disk")

bad_deps = []
for t in tasks:
    for d in (t.get("depends_on") or []):
        if d not in id_set:
            bad_deps.append((t.get("id"), d))
if bad_deps:
    for tid, d in bad_deps:
        print(f"FAIL unknown dependency: {tid} depends_on {d}")
else:
    print("PASS dependencies reference known tasks")

status_of = {t.get("id"): t.get("status") for t in tasks}
bad_ready = []
for t in tasks:
    if t.get("status") != "ready":
        continue
    for d in (t.get("depends_on") or []):
        s = status_of.get(d, "missing")
        if s != "done":
            bad_ready.append((t.get("id"), d, s))
if bad_ready:
    for tid, d, s in bad_ready:
        print(f"WARN ready task {tid} has dep {d} (status={s})")
else:
    print("PASS ready tasks have all dependencies done")
PYEOF
                )"; then
    doctor_fail "queue inspection helper failed: $report"
    printf '\n'
    return 0
  fi

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      PASS\ *) doctor_pass "${line#PASS }" ;;
      WARN\ *) doctor_warn "${line#WARN }" ;;
      FAIL\ *) doctor_fail "${line#FAIL }" ;;
      *)       printf '    %s\n' "$line" ;;
    esac
  done <<< "$report"
  printf '\n'
}

# doctor_tool_checks
#
# Check availability of the tools the harness and most tasks rely on. We
# do not fail when an optional tool is missing here — `doctor_workspace_checks`
# and `doctor_ready_task_checks` raise warnings if a missing tool is needed
# for a currently-ready task.
doctor_tool_checks() {
  printf 'Tools\n'
  local tool path
  for tool in git python python3 claude npm pytest; do
    path="$(command -v "$tool" 2>/dev/null || true)"
    if [[ -n "$path" ]]; then
      doctor_pass "$tool: $path"
    else
      doctor_warn "$tool not found in PATH"
    fi
  done
  printf '\n'
}

# doctor_settings_checks <main_wt>
#
# Inspect the operator's Claude Code permission settings. Never prints the
# settings contents (they may contain operator-specific paths). Only reports
# whether each well-known permission pattern is present in `allow`.
doctor_settings_checks() {
  printf 'Claude permissions\n'
  local main_wt="$1"
  local base="${main_wt:-$REPO_ROOT}"
  local settings="$base/.claude/settings.local.json"

  if [[ ! -f "$settings" ]]; then
    doctor_warn "no .claude/settings.local.json under $base"
    doctor_warn "Claude Code will surface a permission prompt for every command"
    printf '\n'
    return 0
  fi
  doctor_pass "settings.local.json present"

  if ! CLAUDE_SETTINGS_FILE="$settings" "$CLAUDE_PYTHON" -c '
import json, os, sys
with open(os.environ["CLAUDE_SETTINGS_FILE"], "r", encoding="utf-8") as fh:
    json.load(fh)
' >/dev/null 2>&1; then
    doctor_fail "settings.local.json is not valid JSON"
    printf '\n'
    return 0
  fi
  doctor_pass "settings.local.json is valid JSON"

  local missing
  missing="$(CLAUDE_SETTINGS_FILE="$settings" "$CLAUDE_PYTHON" - <<'PYEOF' 2>/dev/null
import json, os
with open(os.environ["CLAUDE_SETTINGS_FILE"], "r", encoding="utf-8") as fh:
    data = json.load(fh)
allow = set((data.get("permissions") or {}).get("allow") or [])
for pat in [
    "Bash(git add:*)",
    "Bash(git commit:*)",
    "Bash(npm install:*)",
    "Bash(npm test:*)",
    "Bash(npm run build:*)",
    "Bash(pytest:*)",
    "Bash(bash -n:*)",
]:
    if pat not in allow:
        print(pat)
PYEOF
)"
  if [[ -z "$missing" ]]; then
    doctor_pass "common Claude permission patterns present"
  else
    while IFS= read -r pat; do
      [[ -z "$pat" ]] && continue
      doctor_warn "missing useful permission pattern: $pat"
    done <<< "$missing"
  fi

  # Report whether each registered task worktree can see the settings.
  # Claude reads .claude/settings.local.json relative to its working
  # directory, so a missing file inside a worktree means routine commands
  # will surface permission prompts despite main being configured.
  local main_wt_for_iter="${main_wt:-$REPO_ROOT}"
  local wt_path wt_name dst
  while IFS= read -r line; do
    [[ "$line" =~ ^worktree[[:space:]](.+)$ ]] || continue
    wt_path="${BASH_REMATCH[1]}"
    [[ "$wt_path" == "$main_wt_for_iter" ]] && continue
    wt_name="${wt_path##*/}"
    dst="$wt_path/.claude/settings.local.json"
    if [[ -e "$dst" ]]; then
      doctor_pass "worktree $wt_name has Claude settings visible"
    else
      doctor_warn "worktree $wt_name missing .claude/settings.local.json"
    fi
  done < <(git -C "$main_wt_for_iter" worktree list --porcelain 2>/dev/null || true)

  printf '\n'
}

# doctor_workspace_checks <main_wt>
#
# Check that node package workspaces referenced by tasks are prepared.
# We never run `npm install`; we only check whether the install marker
# exists and print the exact preparation command otherwise.
doctor_workspace_checks() {
  printf 'Workspaces\n'
  local main_wt="$1"
  local base="${main_wt:-$REPO_ROOT}"
  local found=0

  if [[ -f "$base/frontend/package.json" ]]; then
    found=1
    if [[ -x "$base/frontend/node_modules/.bin/vitest" ]]; then
      doctor_pass "frontend workspace ready (node_modules/.bin/vitest present)"
    else
      doctor_warn "frontend node_modules missing in $base/frontend"
      printf '       prepare with: cd %s/frontend && npm install\n' "$base"
    fi
  fi

  if [[ -f "$base/extension/package.json" ]]; then
    found=1
    if [[ -d "$base/extension/node_modules" ]]; then
      doctor_pass "extension workspace ready (node_modules present)"
    else
      doctor_warn "extension node_modules missing in $base/extension"
      printf '       prepare with: cd %s/extension && npm install\n' "$base"
    fi
  fi

  if [[ "$found" -eq 0 ]]; then
    printf '  (no frontend/ or extension/ package.json found at %s)\n' "$base"
  fi
  printf '\n'
}

# doctor_ready_task_checks
#
# For each task whose status is `ready`, print a compact summary the
# operator can scan before dispatching. Never executes the task's
# verification commands.
doctor_ready_task_checks() {
  printf 'Ready tasks\n'
  if [[ ! -f "$QUEUE_FILE" ]] || ! "$CLAUDE_PYTHON" -c 'import yaml' >/dev/null 2>&1; then
    printf '  (queue not available)\n\n'
    return 0
  fi

  local ready_ids any=0
  ready_ids="$(yaml_query list 2>/dev/null | awk -F'\t' '$2=="ready"{print $1}')"
  if [[ -z "$ready_ids" ]]; then
    printf '  (no tasks with status=ready)\n\n'
    return 0
  fi

  local id worktree wt_path verif kind
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    any=1
    worktree="$(yaml_query field "$id" worktree 2>/dev/null)"
    verif="$(yaml_query field "$id" verification 2>/dev/null)"
    kind=""
    [[ "$verif" == *"frontend"* ]] && kind="$kind frontend"
    [[ "$verif" == *"extension"* ]] && kind="$kind extension"
    [[ "$verif" == *"pytest"* ]]    && kind="$kind backend"
    [[ -z "$kind" ]] && kind=" (other)"
    printf '  %s\n' "$id"
    printf '    verification kind:%s\n' "$kind"
    if [[ "$worktree" == "main" ]]; then
      printf '    worktree: main (in-place)\n'
    else
      wt_path="$(worktree_path "$worktree" 2>/dev/null)"
      if [[ -n "$wt_path" ]]; then
        printf '    worktree: %s (exists at %s)\n' "$worktree" "$wt_path"
      else
        printf '    worktree: %s (not yet created)\n' "$worktree"
      fi
    fi
    if [[ -n "$verif" ]]; then
      printf '    verification commands:\n'
      while IFS= read -r cmd; do
        [[ -z "$cmd" ]] && continue
        printf '      $ %s\n' "$cmd"
      done <<< "$verif"
    fi
  done <<< "$ready_ids"

  [[ "$any" -eq 1 ]] || printf '  (no tasks with status=ready)\n'
  printf '\n'
}

cmd_doctor() {
  # Task-specific `doctor <task-id>` is documented as future work — we accept
  # the argument so we can fail clearly instead of mysteriously, and the
  # operator-facing message points at the global form they probably wanted.
  if [[ $# -gt 0 ]]; then
    err "doctor: task-specific form (doctor <task-id>) is not yet implemented;"
    err "       run 'scripts/agentctl.sh doctor' for the global preflight report."
    exit 2
  fi

  DOCTOR_PASS=0
  DOCTOR_WARN=0
  DOCTOR_FAIL=0

  printf 'Agent Harness Doctor\n\n'

  local main_wt=""
  doctor_git_checks main_wt
  doctor_queue_checks
  doctor_tool_checks
  doctor_settings_checks "$main_wt"
  doctor_workspace_checks "$main_wt"
  doctor_ready_task_checks

  printf 'Summary: %d PASS, %d WARN, %d FAIL\n' \
    "$DOCTOR_PASS" "$DOCTOR_WARN" "$DOCTOR_FAIL"

  if [[ "$DOCTOR_FAIL" -gt 0 ]]; then
    exit 1
  fi
}

cmd_help() {
  cat <<'EOF'
agentctl.sh - agent task orchestration harness

Usage:
  scripts/agentctl.sh run <task-id>
  scripts/agentctl.sh run-interactive <task-id>
  scripts/agentctl.sh review <task-id>
  scripts/agentctl.sh review-status <task-id>
  scripts/agentctl.sh fix <task-id>
  scripts/agentctl.sh sync <task-id>
  scripts/agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files] [--skip-review]
  scripts/agentctl.sh complete --continue <task-id>
  scripts/agentctl.sh next
  scripts/agentctl.sh work [<task-id>] [--until-blocked] [--max-fix-attempts N]
                           [--max-tasks N] [--dry-run]
  scripts/agentctl.sh work --help
  scripts/agentctl.sh status
  scripts/agentctl.sh list
  scripts/agentctl.sh ready
  scripts/agentctl.sh doctor
  scripts/agentctl.sh plan "<high-level goal>"
  scripts/agentctl.sh plan --ultraplan "<high-level goal>"
  scripts/agentctl.sh plan --help

See docs/contracts/agent_orchestration.md for the full contract,
including the review verdict enum (APPROVE / APPROVE_WITH_NOTES /
REQUEST_CHANGES / REJECT / BLOCKED) and the review/fix/complete flow.
EOF
}

plan_help() {
  cat <<'EOF'
agentctl.sh plan - generate scoped agent task packs from a high-level goal

Usage:
  scripts/agentctl.sh plan "<high-level goal>"
       Launch a local Claude Code planning session. The planner reads the
       current queue, architecture docs, ADRs, and contracts, then produces
       one or more scoped task markdown files under agent_tasks/ and matching
       entries in agent_tasks/queue.yaml. The planner does not implement
       product code and does not mark new tasks as done.

  scripts/agentctl.sh plan --ultraplan "<high-level goal>"
       Do not invoke Claude Code. Instead, write a self-contained
       Ultraplan-ready prompt file under .agent_plans/<timestamp>-ultraplan.md
       that includes current queue context, references to docs/ADRs/contracts,
       and task-generation instructions. Then print manual handoff steps.

  scripts/agentctl.sh plan --help
       Show this help text.

Planner safety boundaries (enforced via prompt; the operator should
double-check the diff):
  May edit:    agent_tasks/**, docs/contracts/agent_orchestration.md,
               .agent_plans/**, .gitignore
  Must not edit: backend/**, frontend/**, extension/**, runtime_prompts/**,
                 candidate_context/**, runs/**, docs/adr/**,
                 docs/product_requirements.md, docs/architecture.md

See docs/contracts/agent_orchestration.md and agent_tasks/planning_guidelines.md
for the full planner contract.
EOF
}

# build_planner_directives
#
# Print the shared list of instructions both the local planner prompt and the
# Ultraplan prompt embed verbatim. Keeping it in one place keeps the two
# planner surfaces in sync.
build_planner_directives() {
  cat <<'EOF'
You are a planning agent, not an implementation agent.

Create scoped implementation task files and queue entries only.

Do not implement product code.

Prefer several small tasks over one large task.

Respect ADRs and contracts.

Preserve completed queue history.

Do not change product direction.

Do not mark new tasks as done.

Keep allowed_paths narrow and non-overlapping where possible.

You may edit only:
  agent_tasks/**
  docs/contracts/agent_orchestration.md
  .agent_plans/**
  .gitignore

You must not edit:
  backend/**
  frontend/**
  extension/**
  runtime_prompts/**
  candidate_context/**
  runs/**
  docs/adr/**
  docs/product_requirements.md
  docs/architecture.md

Each generated task markdown file must include these sections:
  Goal
  Background
  Scope
  Allowed files
  Forbidden files
  Out of scope
  Acceptance criteria
  Verification
  Git instructions

Each generated queue entry in agent_tasks/queue.yaml must include:
  id
  title
  file
  branch
  worktree
  status        (one of: planned, ready, blocked)
  depends_on
  verification
  allowed_paths
EOF
}

# write_ultraplan_prompt <goal> <output_path>
#
# Build the Ultraplan-ready markdown prompt file. Uses Python with PyYAML so
# the current queue can be parsed and split by status; mirrors yaml_query's
# strategy for keeping the bash side dependency-light.
write_ultraplan_prompt() {
  local goal="$1" out_path="$2"
  require_queue
  require_python_yaml
  local directives
  directives="$(build_planner_directives)"
  CLAUDE_QUEUE_FILE="$QUEUE_FILE" \
  CLAUDE_PLAN_GOAL="$goal" \
  CLAUDE_PLAN_OUT="$out_path" \
  CLAUDE_PLAN_DIRECTIVES="$directives" \
    "$CLAUDE_PYTHON" - <<'PYEOF'
import os, sys, yaml, datetime

queue_path = os.environ["CLAUDE_QUEUE_FILE"]
out_path   = os.environ["CLAUDE_PLAN_OUT"]
goal       = os.environ["CLAUDE_PLAN_GOAL"]
directives = os.environ["CLAUDE_PLAN_DIRECTIVES"]

with open(queue_path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
tasks = data.get("tasks") or []

done    = [t for t in tasks if t.get("status") == "done"]
open_   = [t for t in tasks if t.get("status") in ("ready", "planned", "blocked", "running", "review")]
other   = [t for t in tasks if t not in done and t not in open_]

def fmt_task(t):
    return f"- {t.get('id','?')} [{t.get('status','?')}] — {t.get('title','')} ({t.get('file','')})"

now = datetime.datetime.now().isoformat(timespec="seconds")

body = []
body.append(f"# Ultraplan Prompt: {goal}")
body.append("")
body.append(f"_Generated by scripts/agentctl.sh plan --ultraplan on {now}._")
body.append("")
body.append("## High-level goal")
body.append("")
body.append(goal)
body.append("")
body.append("## What to produce")
body.append("")
body.append("Generate a small, ordered pack of scoped implementation tasks that move the")
body.append("project toward the high-level goal above. For each task, produce:")
body.append("")
body.append("1. A markdown task file under `agent_tasks/<NNN>-<slug>.md` following the")
body.append("   section structure listed in the planner directives below.")
body.append("2. A matching entry in `agent_tasks/queue.yaml` using the keys listed in the")
body.append("   planner directives below.")
body.append("")
body.append("Pick the next free numeric id by continuing the existing sequence in")
body.append("`agent_tasks/queue.yaml` (see 'Current queue' below).")
body.append("")
body.append("## Planner directives")
body.append("")
body.append("```text")
body.append(directives)
body.append("```")
body.append("")
body.append("## Current queue (completed history — do not rewrite)")
body.append("")
if done:
    for t in done:
        body.append(fmt_task(t))
else:
    body.append("_(no completed tasks)_")
body.append("")
body.append("## Current queue (open tasks — ready / planned / blocked / running / review)")
body.append("")
if open_:
    for t in open_:
        body.append(fmt_task(t))
else:
    body.append("_(no open tasks)_")
if other:
    body.append("")
    body.append("## Other queue entries")
    body.append("")
    for t in other:
        body.append(fmt_task(t))
body.append("")
body.append("## Reference documents the planner should read first")
body.append("")
body.append("- docs/product_requirements.md  (product scope and non-goals)")
body.append("- docs/architecture.md          (component boundaries)")
body.append("- docs/contracts/agent_orchestration.md  (task / queue / planner contract)")
body.append("- docs/contracts/*.md           (other contracts, e.g. capture payload, run dir)")
body.append("- docs/adr/*.md                 (architectural decisions — respect, do not override)")
body.append("- agent_tasks/planning_guidelines.md  (planner-specific guidance)")
body.append("- agent_tasks/queue.yaml        (current queue — preserve completed history)")
body.append("")
body.append("## Output requirements summary")
body.append("")
body.append("- Do not implement product code as part of planning.")
body.append("- Preserve every existing completed task entry in queue.yaml verbatim.")
body.append("- Do not mark any new task `done`. Use `planned`, `ready`, or `blocked`.")
body.append("- Keep `allowed_paths` narrow and non-overlapping between sibling tasks.")
body.append("- Prefer several small tasks over one large task.")
body.append("- Each new task must specify its own verification commands and commit message.")
body.append("")

with open(out_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(body))
print(out_path)
PYEOF
}

plan_ultraplan() {
  local goal="$1"
  [[ -n "$goal" ]] || die "usage: agentctl.sh plan --ultraplan \"<high-level goal>\""
  mkdir -p "$PLANS_DIR"
  local ts out_path
  ts="$(date +%Y-%m-%d-%H%M%S)"
  out_path="$PLANS_DIR/${ts}-ultraplan.md"
  write_ultraplan_prompt "$goal" "$out_path" >/dev/null

  local rel_path="${out_path#$REPO_ROOT/}"
  printf 'Wrote Ultraplan prompt: %s\n' "$rel_path"
  printf '\n'
  printf 'Next steps (manual handoff):\n'
  printf '  1. Open Claude Code in this repo.\n'
  printf '  2. Run /ultraplan and supply the prompt above, e.g.:\n'
  printf '       /ultraplan %s\n' "$rel_path"
  printf '     (If your Claude Code build does not support /ultraplan, paste the\n'
  printf '     contents of %s into a planning session.)\n' "$rel_path"
  printf '  3. Review the generated plan. When ready, save the new task files under\n'
  printf '     agent_tasks/ and add matching entries to agent_tasks/queue.yaml.\n'
  printf '  4. Do not implement product code as part of planning.\n'
  printf '\n'
  printf 'Files under .agent_plans/ are gitignored by default; promote a plan by\n'
  printf 'copying its scoped task files into agent_tasks/ and committing those.\n'
}

build_local_plan_prompt() {
  local goal="$1"
  local directives
  directives="$(build_planner_directives)"
  cat <<EOF
You are running scripts/agentctl.sh plan in local planning mode.

High-level goal:

${goal}

You are a planning agent. Generate a small, ordered pack of scoped
implementation tasks that move the project toward the high-level goal.

Read first (do not skip):
- docs/product_requirements.md
- docs/architecture.md
- docs/contracts/agent_orchestration.md
- docs/contracts/*.md
- docs/adr/*.md
- agent_tasks/planning_guidelines.md
- agent_tasks/queue.yaml

Then, for each task you propose:

1. Create a markdown task file at agent_tasks/<NNN>-<slug>.md using the next
   available numeric id (continue the sequence already in queue.yaml).
2. Add a matching entry to agent_tasks/queue.yaml.

Planner directives (follow exactly):

----- BEGIN PLANNER DIRECTIVES -----
${directives}
----- END PLANNER DIRECTIVES -----

After writing the new task files and queue entries:
- Do not stage or commit. The operator will review the diff and commit.
- Print a short summary listing each new task id, title, status, and file path.
EOF
}

plan_local() {
  local goal="$1"
  [[ -n "$goal" ]] || die "usage: agentctl.sh plan \"<high-level goal>\""
  require_queue
  require_python_yaml
  ensure_clean_worktree

  local prompt
  prompt="$(build_local_plan_prompt "$goal")"

  printf 'Starting local Claude Code planning session\n'
  printf '  goal: %s\n' "$goal"
  printf '  permission-mode: %s\n' "$CLAUDE_PLAN_PERMISSION_MODE"
  printf '  (planner may edit only agent_tasks/**, docs/contracts/agent_orchestration.md,\n'
  printf '   .agent_plans/**, and .gitignore. See plan --help for the full boundary.)\n\n'

  if ! "$CLAUDE_BIN" \
      --permission-mode "$CLAUDE_PLAN_PERMISSION_MODE" \
      -p "$prompt"; then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nPlanner finished. Review the diff before committing:\n'
  git -C "$REPO_ROOT" status --short
}

cmd_plan() {
  local mode="local" goal=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        plan_help
        return 0
        ;;
      --ultraplan)
        mode="ultraplan"
        shift
        ;;
      --)
        shift
        [[ $# -gt 0 ]] || die "usage: agentctl.sh plan [--ultraplan] \"<high-level goal>\""
        if [[ -n "$goal" ]]; then
          die "plan: multiple goals supplied; pass a single quoted string"
        fi
        goal="$1"
        shift
        ;;
      -*)
        err "unknown plan flag: $1"
        plan_help
        exit 2
        ;;
      *)
        if [[ -n "$goal" ]]; then
          die "plan: multiple goals supplied; pass a single quoted string"
        fi
        goal="$1"
        shift
        ;;
    esac
  done

  if [[ -z "$goal" ]]; then
    err "plan: missing high-level goal"
    plan_help
    exit 2
  fi

  case "$mode" in
    ultraplan) plan_ultraplan "$goal" ;;
    local)     plan_local "$goal" ;;
  esac
}

main() {
  local cmd="${1:-}"
  if [[ "$#" -gt 0 ]]; then shift; fi
  case "$cmd" in
    run)    cmd_run "$@" ;;
    run-interactive) cmd_run_interactive "$@" ;;
    review) cmd_review "$@" ;;
    review-status) cmd_review_status "$@" ;;
    fix)    cmd_fix "$@" ;;
    sync)   cmd_sync "$@" ;;
    complete) cmd_complete "$@" ;;
    next)   cmd_next "$@" ;;
    work)   cmd_work "$@" ;;
    status) cmd_status "$@" ;;
    list)   cmd_list "$@" ;;
    ready)  cmd_ready "$@" ;;
    doctor) cmd_doctor "$@" ;;
    plan)   cmd_plan "$@" ;;
    ""|help|-h|--help) cmd_help ;;
    *) err "unknown command: $cmd"; cmd_help; exit 2 ;;
  esac
}

main "$@"
