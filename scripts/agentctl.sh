#!/usr/bin/env bash
#
# agentctl.sh - lightweight orchestration harness for agent_tasks.
#
# Subcommands:
#   run <task-id>     Start Claude Code on a task in an isolated worktree.
#   review <task-id>  Start a review-only Claude session for a task.
#   status            Print task ids grouped by status.
#   list              Print every task with its status and title.
#
# Configuration via environment variables:
#   CLAUDE_BIN                       Claude Code executable. Default: claude
#   CLAUDE_PERMISSION_MODE           Permission mode for run. Default: acceptEdits
#   CLAUDE_REVIEW_PERMISSION_MODE    Permission mode for review. Default: plan
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
CLAUDE_PYTHON="${CLAUDE_PYTHON:-python3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
QUEUE_FILE="$REPO_ROOT/agent_tasks/queue.yaml"

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
else:
    sys.stderr.write(f"error: unknown yaml_query mode: {mode}\n")
    sys.exit(2)
PYEOF
}

cmd_list() {
  printf '%-30s %-10s %s\n' "ID" "STATUS" "TITLE"
  printf '%-30s %-10s %s\n' "------------------------------" "----------" "-----"
  while IFS=$'\t' read -r id status title; do
    [[ -z "$id" ]] && continue
    printf '%-30s %-10s %s\n' "$id" "$status" "$title"
  done < <(yaml_query list)
}


cmd_run_interactive() {
  local task_id="$1"

  load_task "$task_id"

  ensure_clean_git_tree
  ensure_dependencies_done "$task_id"

  local prompt_file
  prompt_file="$(mktemp "/tmp/jobapply-agent-${task_id}.XXXXXX.md")"

  cat > "$prompt_file" <<EOF
# Agent Task: $TASK_ID

Read and execute the task file exactly:

\`\`\`text
$TASK_FILE
\`\`\`

Before editing:
- read the task file
- read all background docs it references
- state the intended scope briefly

During implementation:
- stay within scope
- respect allowed/forbidden files if listed
- do not make unrelated changes

After implementation:
- run the verification commands listed in the task
- stage changes
- commit with the exact commit message required by the task
- do not push

Task file contents:

$(cat "$TASK_FILE")
EOF

  echo "Starting interactive Claude Code for task $TASK_ID"
  echo "  task file: $TASK_FILE"
  echo "  worktree:  $WORKTREE"
  echo "  prompt:    $prompt_file"
  echo
  echo "Claude Code will open interactively so you can approve tool prompts."
  echo "If Claude does not automatically read the prompt, paste this:"
  echo
  echo "Read and execute: $prompt_file"
  echo

  "$CLAUDE_BIN" \
    --worktree "$WORKTREE" \
    --permission-mode "${CLAUDE_PERMISSION_MODE:-acceptEdits}" \
    "$prompt_file"
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

build_run_prompt() {
  local task_id="$1" task_file="$2"
  cat <<EOF
You are executing agent task ${task_id}.

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

build_review_prompt() {
  local task_id="$1" task_file="$2"
  cat <<EOF
You are reviewing agent task ${task_id}. Do not modify files.

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

  local prompt
  prompt="$(build_run_prompt "$task_id" "$abs_task_file")"

  printf 'Starting Claude Code for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  printf '  permission-mode: %s\n' "$CLAUDE_PERMISSION_MODE"

  # If the local Claude build does not support --worktree, run this instead:
  #   git worktree add "../$worktree" -b "agent/$task_id"
  #   (cd "../$worktree" && "$CLAUDE_BIN" --permission-mode "$CLAUDE_PERMISSION_MODE" -p "$prompt")
  if ! "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_PERMISSION_MODE" \
      -p "$prompt"; then
    die "Claude Code exited with a non-zero status"
  fi

  printf '\nAgent finished. Recent commits:\n'
  git -C "$REPO_ROOT" log --oneline -5
  printf '\nGit status:\n'
  git -C "$REPO_ROOT" status --short
}

cmd_review() {
  local task_id="${1:-}"
  [[ -n "$task_id" ]] || die "usage: agentctl.sh review <task-id>"
  require_queue
  require_python_yaml

  local task_file worktree
  task_file="$(yaml_query field "$task_id" file)"
  worktree="$(yaml_query field "$task_id" worktree)"

  [[ -n "$task_file" ]] || die "task '$task_id' has no 'file' field"
  [[ -n "$worktree" ]] || die "task '$task_id' has no 'worktree' field"

  local abs_task_file="$REPO_ROOT/$task_file"
  [[ -f "$abs_task_file" ]] || die "task file not found: $abs_task_file"

  local prompt
  prompt="$(build_review_prompt "$task_id" "$abs_task_file")"

  printf 'Starting Claude Code review for task %s\n' "$task_id"
  printf '  task file: %s\n' "$task_file"
  printf '  worktree:  %s\n' "$worktree"
  printf '  permission-mode: %s\n' "$CLAUDE_REVIEW_PERMISSION_MODE"

  if ! "$CLAUDE_BIN" \
      --worktree "$worktree" \
      --permission-mode "$CLAUDE_REVIEW_PERMISSION_MODE" \
      -p "$prompt"; then
    die "Claude Code exited with a non-zero status"
  fi
}

cmd_help() {
  cat <<'EOF'
agentctl.sh - agent task orchestration harness

Usage:
  scripts/agentctl.sh run <task-id>
  scripts/agentctl.sh run-interactive <task-id>
  scripts/agentctl.sh review <task-id>
  scripts/agentctl.sh status
  scripts/agentctl.sh list

See docs/contracts/agent_orchestration.md for the full contract.
EOF
}

main() {
  local cmd="${1:-}"
  if [[ "$#" -gt 0 ]]; then shift; fi
  case "$cmd" in
    run)    cmd_run "$@" ;;
    run-interactive) require_task_id
	    cmd_run_interactive "$TASK_ID";;
    review) cmd_review "$@" ;;
    status) cmd_status "$@" ;;
    list)   cmd_list "$@" ;;
    ""|help|-h|--help) cmd_help ;;
    *) err "unknown command: $cmd"; cmd_help; exit 2 ;;
  esac
}

main "$@"
