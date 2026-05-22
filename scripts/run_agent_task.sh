#!/usr/bin/env bash
set -euo pipefail

TASK_FILE="${1:-}"

if [[ -z "$TASK_FILE" ]]; then
  echo "Usage: $0 agent_tasks/<task-file>.md"
  exit 1
fi

if [[ ! -f "$TASK_FILE" ]]; then
  echo "Task file not found: $TASK_FILE"
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Git tree is not clean. Commit or stash changes first."
  git status --short
  exit 1
fi

echo "Running agent task: $TASK_FILE"
echo "Current branch: $(git branch --show-current)"
echo

claude < "$TASK_FILE"

echo
echo "Agent finished."
echo "Recent commits:"
git log --oneline -5

echo
echo "Current status:"
git status --short
