#!/usr/bin/env bash
#
# agentctl.sh - lightweight orchestration harness for agent_tasks.
#
# Subcommands:
#   run <task-id>     Start Claude Code on a task in an isolated worktree.
#   review <task-id>  Start a review-only Claude session for a task.
#   sync <task-id>    Ensure task worktree exists and is up to date with main.
#   complete <task-id> [--dry-run] [--clean-shadow-files]
#                     Run verification, merge the task's worktree branch into
#                     main, mark the task done, promote unblocked tasks, and
#                     commit the queue update. --dry-run prints what would
#                     happen without changing files or branches.
#                     --clean-shadow-files removes untracked files in main
#                     whose paths are tracked in the task branch (likely
#                     leaked from the task worktree). It never runs a broad
#                     git clean and never touches modified tracked files.
#   complete --continue <task-id>
#                     Resume `complete` after the operator resolved a merge
#                     conflict by hand. Finishes the merge commit, runs
#                     verification, then updates queue statuses.
#   status            Print task ids grouped by status.
#   list              Print every task with its status and title.
#   ready             Print tasks whose status is 'ready'.
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
#   CLAUDE_REVIEW_PERMISSION_MODE    Permission mode for review. Default: plan
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
CLAUDE_REVIEW_PERMISSION_MODE="${CLAUDE_REVIEW_PERMISSION_MODE:-plan}"
CLAUDE_PLAN_PERMISSION_MODE="${CLAUDE_PLAN_PERMISSION_MODE:-acceptEdits}"
CLAUDE_PYTHON="${CLAUDE_PYTHON:-python3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
QUEUE_FILE="$REPO_ROOT/agent_tasks/queue.yaml"
PLANS_DIR="$REPO_ROOT/.agent_plans"
PLANNING_GUIDELINES="$REPO_ROOT/agent_tasks/planning_guidelines.md"

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
  local header
  header="$(build_worktree_header "$worktree_path" "$main_path")"
  cat <<EOF
You are reviewing agent task ${task_id}. Do not modify files.

${header}

Check the most recent commit(s) on this worktree and assess:
- Did the implementation stay within the task's scope?
- Were the task's allowed_paths respected? Flag any files changed outside them.
- Were the relevant ADRs in docs/adr/ respected?
- Are the tests meaningful (covering the behavior the task specifies) or thin?
- Was anything overbuilt beyond what the task asked for?
- Were unrelated files changed?
- Is the commit message appropriate and matches what the task required?

Produce a structured review with sections for: Scope, Allowed Paths, ADR Compliance,
Tests, Overbuild, Unrelated Changes, Commit Message, and Overall Verdict.

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
  fi

  local launch_dir="$REPO_ROOT"
  [[ -n "$wt_path" ]] && launch_dir="$wt_path"

  local prompt
  prompt="$(build_review_prompt "$task_id" "$abs_task_file" "$wt_path" "$REPO_ROOT")"

  printf 'Starting Claude Code review for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  [[ -n "$wt_path" ]] && printf '  worktree-path: %s\n' "$wt_path"
  printf '  launch dir: %s\n' "$launch_dir"
  printf '  permission-mode: %s\n' "$CLAUDE_REVIEW_PERMISSION_MODE"

  # Launch from inside the task worktree path (see cmd_run for rationale).
  if ! ( cd "$launch_dir" && "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_REVIEW_PERMISSION_MODE" \
      -p "$prompt" ); then
    die "Claude Code exited with a non-zero status"
  fi
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

# run_verification_commands <dir> <task-id>
#
# Run every command in the task's `verification` list inside <dir>. Prints
# each command to stderr before running it. Returns the first non-zero exit
# status; returns 0 if all commands succeed.
run_verification_commands() {
  local dir="$1" task_id="$2" cmd ran=0
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    ran=1
    printf '  $ %s\n' "$cmd" >&2
    if ! (cd "$dir" && bash -c "$cmd"); then
      err "verification command failed in $dir: $cmd"
      return 1
    fi
  done < <(yaml_query field "$task_id" verification)
  if [[ "$ran" -eq 0 ]]; then
    printf '  (task %s has no verification commands)\n' "$task_id" >&2
  fi
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

  printf 'Running verification in %s\n' "$main_wt" >&2
  if ! run_verification_commands "$main_wt" "$task_id"; then
    err "verification failed; not marking $task_id done"
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
  local task_id="" dry_run=0 continue_mode=0 clean_shadow=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --continue) continue_mode=1; shift ;;
      --clean-shadow-files) clean_shadow=1; shift ;;
      -*) die "usage: agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files]
       agentctl.sh complete --continue <task-id>" ;;
      *)
        [[ -z "$task_id" ]] || die "complete: only one task id may be given"
        task_id="$1"; shift ;;
    esac
  done
  [[ -n "$task_id" ]] || die "usage: agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files]
       agentctl.sh complete --continue <task-id>"

  if [[ "$continue_mode" -eq 1 && "$dry_run" -eq 1 ]]; then
    die "complete: --continue and --dry-run are mutually exclusive"
  fi
  if [[ "$continue_mode" -eq 1 && "$clean_shadow" -eq 1 ]]; then
    die "complete: --continue and --clean-shadow-files are mutually exclusive"
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

  if [[ -n "$(git -C "$main_wt" status --porcelain)" ]]; then
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
    printf 'Running verification in %s\n' "$task_wt" >&2
    if ! run_verification_commands "$task_wt" "$task_id"; then
      err "verification failed; not marking $task_id done"
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

cmd_help() {
  cat <<'EOF'
agentctl.sh - agent task orchestration harness

Usage:
  scripts/agentctl.sh run <task-id>
  scripts/agentctl.sh run-interactive <task-id>
  scripts/agentctl.sh review <task-id>
  scripts/agentctl.sh sync <task-id>
  scripts/agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files]
  scripts/agentctl.sh complete --continue <task-id>
  scripts/agentctl.sh status
  scripts/agentctl.sh list
  scripts/agentctl.sh ready
  scripts/agentctl.sh plan "<high-level goal>"
  scripts/agentctl.sh plan --ultraplan "<high-level goal>"
  scripts/agentctl.sh plan --help

See docs/contracts/agent_orchestration.md for the full contract.
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
    sync)   cmd_sync "$@" ;;
    complete) cmd_complete "$@" ;;
    status) cmd_status "$@" ;;
    list)   cmd_list "$@" ;;
    ready)  cmd_ready "$@" ;;
    plan)   cmd_plan "$@" ;;
    ""|help|-h|--help) cmd_help ;;
    *) err "unknown command: $cmd"; cmd_help; exit 2 ;;
  esac
}

main "$@"
