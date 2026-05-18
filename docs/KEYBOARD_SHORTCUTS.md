# Keyboard shortcuts

Every shortcut is also visible in-app via the **`?`** cheatsheet
(press `?` anywhere outside a text input).

## Global navigation

| Keys             | Action                                |
| ---------------- | ------------------------------------- |
| `⌘K` / `Ctrl+K`  | Open the command palette              |
| `/`              | Open the palette pre-focused on search |
| `?`              | Show the keyboard cheatsheet          |
| `Esc`            | Close any overlay                     |
| `g h`            | Jump to Home                          |
| `g p`            | Jump to Pipelines                     |
| `g d`            | Jump to Datasets                      |
| `g r`            | Jump to Run history                   |
| `g c`            | Jump to Catalog                       |
| `g s`            | Jump to Settings                      |
| `⌘⇧E`           | Cycle expertise mode (beginner → builder → engineer) |

### G-chord notes

- Press `g` first, then the second letter within 1 second.
- The chord is dropped silently if the second key isn't mapped.
- Disabled while a text input or contenteditable element is focused.

## Pipeline editor

| Keys             | Action                                       |
| ---------------- | -------------------------------------------- |
| `⌘Z`             | Undo last edit                               |
| `⌘⇧Z` / `⌘Y`    | Redo                                         |
| `⌘S`             | Save (open labelled-checkpoint dialog)       |
| `⌘⇧S`           | Save As (clone)                              |
| `⌫` / `Delete`   | Delete selected step / edge                  |
| Double-click sub-pipeline node | Open the source pipeline in a new tab |

## Live grid

| Keys                       | Action                                              |
| -------------------------- | --------------------------------------------------- |
| Click column name          | Open the column profile drawer                      |
| Click `⋯` on header        | Open the column menu (filter / sort / cast / drop / …) |
| Right-click header         | Same as `⋯`                                         |
| `⌘`+click cell             | Filter to this value                                |
| `⌘+Alt`+click cell         | Exclude this value                                  |
| `Alt+←` / `Alt+→`          | Reorder a focused header column                     |

## Command palette

Once the palette is open, every action is searchable by label or alias.
Highlights:

- **Recent** group at the top — your last 10 pipelines + last 10
  datasets, populated automatically.
- **Per-pipeline actions** — typing a pipeline name reveals `▶ Run`,
  `📑 Duplicate`, `⏰ Schedule`, `🔗 Copy link`, `⬇ Export as JSON`.
- **Step search** — when you're already in a pipeline editor, picking
  a step result inserts it at the focused position. Outside the editor
  it surfaces a hint.
- **Create flow** — "New blank pipeline" / "Browse templates" / "Upload
  a dataset" verbs ship with the palette.

## Multi-tab safety

If you open the same pipeline editor in two browser tabs, DIG broadcasts
a soft heartbeat over `BroadcastChannel`. The second tab surfaces a
non-blocking toast — edits there will conflict with the first tab.

## Run loop

| Surface          | Action                                       |
| ---------------- | -------------------------------------------- |
| ▶ Run pipeline   | Runs the full pipeline against the whole dataset |
| Sample picker (split-button on Run) | One-off run on 1k / 10k / 100k / 1M rows without dirtying the pipeline doc |
| 🛑 Stop          | Replaces ▶ Run while a run is in flight; cancels the task |
| Click a run row  | Opens the run-detail view                    |

When a run fails on a specific node, the run-detail page builds an
`?focus=<nodeId>` link to the editor. Opening it scrolls to the failing
node and clears the URL parameter.
