# Parallel Claude Tasks workflow (diagram)

GitHub renders Mermaid diagrams automatically in Markdown files. This diagram shows the **job-level** flow of `workflows/parallel-tasks.yml`.

```mermaid
flowchart LR
  subgraph Triggers
    WD["workflow_dispatch<br/>inputs: task_description, num_workers, auto_merge, notify_on_complete"]
    IC["issue_comment<br/>(created)"]
  end

  WD --> A
  IC --> A

  subgraph Jobs
    A["analyze<br/>Split task into N subtasks<br/>(outputs: subtasks, task_count)"]
    E["execute<br/>Matrix over subtasks<br/>Create branch → run Claude Code → commit → push → PR"]
    N["notify<br/>(always) if notify_on_complete<br/>Log results → optional Pushover → optional summary issue"]
    M["auto-merge<br/>if execute success && auto_merge<br/>List PRs → write summary"]
  end

  A --> E
  A --> N
  E --> N
  A --> M
  E --> M
```

## Notes

- The `execute` job runs **in parallel** via a matrix over `needs.analyze.outputs.subtasks`.
- `notify` runs even if some matrix jobs fail (`if: always()`), but only when `notify_on_complete` is true.
- `auto-merge` is a summary/reporting job in this workflow (it does not actually merge PRs as written).
