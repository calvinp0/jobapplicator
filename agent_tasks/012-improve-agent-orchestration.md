1. Look up task in queue.yaml.
2. Check dependencies are done.
3. Check main is clean.
4. Ensure task worktree exists.
5. If worktree branch is behind main, merge main automatically.
6. Run Claude on the task.
7. Print exact next command




.## Critical Completion Criteria

This task is incomplete unless all of these commands work from the main repo:

```bash
scripts/agentctl.sh sync 007-claude-code-worker
scripts/agentctl.sh complete 007-claude-code-worker --dry-run
scripts/agentctl.sh ready
```
The usage output must include:

scripts/agentctl.sh sync <task-id>
scripts/agentctl.sh complete <task-id>

Do not claim this task is complete if sync or complete are missing.


Commit that task clarification:

```bash
git add agent_tasks/012-improve-agent-orchestration.md
git commit -m "Clarify orchestration automation completion criteria"
```
