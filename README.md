# ComfyUI-FallingTS

ComfyUI custom node plugin: a set of **general-purpose utility nodes** + **frontend enhancements**. Zero external dependencies, built on the ComfyUI V3 extension API (`comfy_api.latest`).

## Feature overview

### Utility nodes

| Node | Node ID | Category | Function |
|------|---------|------|------|
| Continue | `FallingTSContinue` | `FallingTS/Control` | Workflow **segmented execution**: by default blocks downstream; "Continue" releases one segment, running to the end segment by segment (relies on the execution cache, upstream is not recomputed) |
| Route | `FallingTSRoute` | `FallingTS/Control` | total-group routing (reference: grouped switch): one `switch` routes `total` groups at once; each group = when-false/when-true/output (ANY); `total` ≥ 1 |
| Table | `FallingTSTable` | `FallingTS/Table` | Excel-style table (data embedded in the workflow): a "select" dropdown at the top picks a row and outputs that row's A/B/C... column strings; row/column counts are adjustable, and output ports grow/shrink with the column count |
| Markdown data table | `FallingTSMarkDownTable` | `FallingTS/Table` | **Parse data tables from md files**: pick a file with the system picker → a popup searches by field + paginates for a single row → render an editable form inside the node by "title (type)" (IMAGE/VIDEO/AUDIO/MASK/STRING/INT/FLOAT/BOOLEAN/TEXT); refresh re-queries the md by ID; outputs the selected row's fields (by type) + the whole row as JSON |
| Many-to-one selector | `FallingTSSelector` | `FallingTS/Utility` | General ANY node: `items` comma-separated group names, `total` group count (≥ 1), left inputs = group count × number of group names (group 1 first, group 2 after, labels are the group names); the dropdown picks one group name, and each group's **selected value** on the right outputs that group's input for that name (unselected → None, lazy, not executed); fixed outputs at the top: selected item (group-name text) + index (0-based) |
| Fan-out selector | `FallingTSFanout` | `FallingTS/Utility` | The mirror of many-to-one selection: `items` comma-separated group names (same source as many-to-one), `total` group count (≥ 1, ≤ 50) = number of left input ports (one `input_i` per group); right outputs = group count × number of group names (one per group per group name, label = group name); `selection` **selected item** (dropdown, options = group names, can be wired directly to many-to-one's selected item) — selecting the k-th group name → each group's `input_i` routes to that group's output for that name, the rest None; when unwired, each group is None; on a partial submit, the output nodes downstream of each group's selected group name are actually executed (frontend enhancement) |
| Grouped switch | `FallingTSSwitch` | `FallingTS/Utility` | One `switch` boolean toggles `total` groups at once (each group when-false/when-true → output, ANY); `total` ≥ 1 |
| Video preview | `PreviewVideo` | `video` | Preview into the temp directory; clicking "Save" writes to output per `filename_prefix`+`filename_suffix` (`.mp4`, same name overwritten, no sequence number) |
| Image preview save | `PreviewImageSave` | `FallingTS/Utility` | Always previews (temp, does not write to output); clicking **Save** writes to output per filename prefix/suffix/format/bit depth/color space, **same name overwritten, no sequence number** |
| Audio preview save | `PreviewAudioSave` | `audio` | Preview into the temp directory; clicking **Save** writes to output per `filename_prefix`+`filename_suffix` + format (flac/mp3/opus, **same name overwritten, no sequence number**) |

### Web frontend enhancements (14, ready to use on install, no configuration)

| File | Function |
|------|------|
| `web/js/task_notify.js` | Browser task-complete/fail notification tones (Web Audio, no system sound): success on `execution_success`, fail on `execution_error`/`execution_interrupted`; per-status volume/frequency/decay settings + a Win11-style toast; configured under **Settings → FallingTS → 任务提示音** |
| `web/js/proceed.js` | Continue node button + segmented execution logic |
| `web/js/route.js` | Route node: dynamically add/remove each group's ports by `total` + actually execute the false branch: on a partial submit, merge the output nodes downstream of each switch=false group's output into targets, save this segment and stop |
| `web/js/preview-image.js` | Preview-save node "Save" button + format-linked bit depth/color space |
| `web/js/preview-video.js` | Video preview node "Save" button |
| `web/js/preview-audio.js` | Audio preview node "Save" button |
| `web/js/table_lookup.js` | Table DOM controls (Excel grid + selection dropdown + first-column ID) |
| `web/js/md_table.js` | Markdown data table DOM controls: system picker for file + data popup (search/pagination/single-select) + type-rendered form + refresh |
| `web/js/selector.js` | Many-to-one selection: `total` group count × `items` group-name count adds/removes input ports (labels are group names) + show/hide each group's selected-value outputs + dropdown option linkage |
| `web/js/fanout.js` | Fan-out selector (mirror of many-to-one): dynamically add/remove group input ports by `total` (one `input_i` per group) + outputs = group count × group-name count (label = group name) + `selection` selected-item dropdown option linkage (directly wired to many-to-one's selected item) + actually execute the selected group's branch: on a partial submit, merge the output nodes downstream of each group's selected group name into targets |
| `web/js/switch.js` | Grouped switch dynamically adds/removes input/output ports by `total` |
| `web/js/node_image_middleclick.js` | Node image **mouse middle-click** fullscreen preview (single image centered, multiple images cycle left/right, same layout as the generated-image preview) |
| `web/js/media_lightbox_zoom.js` | Image lightbox zoom: wheel/drag/double-click/`+/−/0` shortcuts |
| `web/js/assets_tab_rename.js` | Rename the media assets panel "Imported" tab to "Saved" |
| `web/js/workflow_reload_button.js` | A "reload workflow" button on the run panel; reloads the current workflow from disk |

---

## Node details

### 1. Continue node `FallingTSContinue` (segmented execution)

**Purpose**: cut the workflow into segments, execute and inspect segment by segment, without recomputing completed segments.

**Principle (rebuilt 2026-08, cache-based)**:
- The node's backend returns **`ExecutionBlocker` by default, blocking downstream**; the `any` input is declared **lazy**, and `check_lazy_status` decides whether to pull upstream;
- **Run** (default): the frontend `POST /proceed/reset` resets all continue nodes to blocking and clears the cache, then **fully submits** the workflow → the generation segment runs, caches at the first continue node and stops;
- Clicking **Continue**: the frontend `POST /proceed/continue/{id}` releases that node, then submits `partial_execution_targets` (the output nodes after the next continue) → this continue is already released, `check_lazy_status` returns `[]` and does not pull upstream (**the connections are preserved, upstream does not re-run**), so only the newly released segment runs from this node, stopping at the next continue node;
- Repeatedly clicking "Continue" runs segment by segment to the end;
- Key: "Continue" **does not rely on ComfyUI's global node cache** to decide where to run from — it relies on **lazy gating** `check_lazy_status` (cache-independent; on backtracking, lazy edges are simply not traversed) + the node's own `_data_cache`.

**Workflow requirement**: data between segments is passed **only via continue nodes**. If some segment has a **direct edge** that bypasses the continue node to take an earlier upstream node's output directly (e.g. segment 1 uses segment 0's base image directly for ColorMatch/comparison), that part of upstream is still pulled back and re-run by the execution list's backtracking. Fix: rewire such direct edges' source to **downstream of a continue node** (e.g. #43's output) so it also passes through the lazy gate.

**Key difference from the old version**: no longer depends on "every segment must have an output node" (the old version collected in-segment output nodes via `partial_execution_targets` and would get stuck if a segment had no preview/save node). Now it purely relies on **`ExecutionBlocker` gating + the execution cache**, so any structure can be segmented.

**Behavior**:
1. Run → executes to the first continue node and pauses (the node shows a "▶ Continue" button);
2. Click "Continue" → release this segment, run to the next continue node and stop;
3. To restart from the beginning → press Run again (resets all continues to blocking).

**Data pass-through**: the `any` input is output as-is to `any`.

**HTTP routes** (auto-registered by the backend):
- `POST /proceed/continue/{node_id}` — release this node
- `POST /proceed/reset` — reset all continue nodes to blocking
- `POST /proceed/restart/{node_id}` — increment the re-run token to break downstream cache, and return to blocking

### 1.1 Route node `FallingTSRoute` (total-group routing, reference: grouped switch)

**Purpose**: one `switch` boolean routes `total` groups at once — each group = two inputs `when-false_i`/`when-true_i` + one output `output_i` (ANY); `total` is the group count (≥ 1, ≤ 50), and the frontend dynamically adds/removes ports by `total`. Suited to multi-group branching scenarios like "false = save this segment and stop, true = continue to the next segment".

**Inputs**:
- `switch` (BOOLEAN, default true)
- `total` (INT, default 2, ≥ 1, ≤ 50)
- Per group `false_i` (when-false, ANY) / `true_i` (when-true, ANY), `total` groups in total

**Outputs**:
- `output_i` — group i's output: takes `true_i` when switch=true, `false_i` when false (unwired → None)

**Behavior**:
| switch | Each group's output_i |
|---|---|
| true | true_i |
| false | false_i |

**Actually execute the false branch (frontend route.js)**: segmented execution (clicking "Continue") only runs targets + the targets' upstream ancestors, and the false branch's terminal output nodes (save, etc.) are not among them — the engine will not schedule them. `web/js/route.js`, on a partial submit, **merges the output nodes downstream of each route group's output into targets for the switch=false ones** — save/preview/comparison nodes after the false output can actually execute and get data; the true output branch is upstream of the next continue by definition and is already covered by the continue node's targets.

**Typical usage**: route after a continue node, implementing "false = save this segment and stop, true = continue to the next segment":
```
dataA → when-false_1 → FallingTSRoute ─output_1→ save/preview (false branch)
dataB → when-true_1 →   (total groups)    └output_1→ original downstream (continue to next segment)
```

### 2. Table `FallingTSTable`

**Purpose**: Excel-style table; data is **embedded in the workflow JSON** (no external files), outputting each column's string per row.

**Input**: only `rows` (the `FALLINGTS_TABLE` DOM control). **No separate row-index input** — row selection is driven by the "select" dropdown at the top of the node.

**Controls** (one row at the top of the node):
- **Select** ▾: lists each row's option — with "first-column ID" enabled, shows the first column's content (e.g. `人物-陈落`); otherwise "row N"; selecting writes `selected_index`, and the next Run outputs that row;
- **Row count / column count**: ≥ 1; changing the column count adds/removes the right-side output ports accordingly;
- **First-column ID** ☑: when enabled, the **column-0 header and output ports are named `ID`** (then A/B/C...); the selection dropdown uses the first column's content as labels.

**Outputs**: dynamically generated **ID/A/B/C...AZ (up to 52)** STRING ports by column count; each port outputs the selected row's corresponding cell string.

**Features**:
- Data is fully preserved on workflow save/load;
- Cell textareas auto-grow to fit content, and the node grows accordingly (only grows, never shrinks; respects manually adjusted sizes);
- Backward compatible with the old "row-object array" data (auto-migrated to an A..E five-column grid);
- Type conversion is done by the downstream node itself (e.g. `ComfyNumberConvert` string→numeric).

### 2.1 Markdown data table `FallingTSMarkDownTable`

**Purpose**: treat a data table in an md file as a "database": pick a row in a popup → the node renders an **editable form** by field type, outputting the selected row's field values (by type).

**Data format** (the md file is the only data source; it is not saved with the workflow):
- Contains one GFM table (header + `---` separator row); the first one is taken; **the first column is always the ID column**, a str Chinese string, commonly joining multiple pieces of info with `-` (e.g. `龙傲天-主角`);
- Header format **`title(type)`** (the type goes inside the parentheses; `[]` is special syntax in md, so no square brackets); unmarked types default to `STRING`; supported types: `IMAGE` / `VIDEO` / `AUDIO` / `MASK` / `STRING` / `INT` / `FLOAT` / `BOOLEAN` / `TEXT` (case-insensitive, common aliases normalized; `TEXT` renders as a **multi-line textbox** and outputs STRING likewise).

**Operation flow**:
1. **📁 Select md file** — the backend `tkinter` pops a **native system file picker**; the node records the absolute path (the path box can also be pasted manually, as a headless fallback);
2. **🗂 Open data** — an embedded HTML popup: **fuzzy search per field** at the top, **pagination** at the bottom (10/20/30/50/100 per page + first/prev/next/last), the table has **no sequence-number column, single-select radio in the first column**;
3. After selecting a row, the bottom **OK** button changes from gray to **blue** and lights up; clicking closes the popup and the node loads that row's data into the form; cancel closes without effect;
4. The form arranges each field **vertically**, rendering controls by type (INT/FLOAT numeric input, BOOLEAN checkbox, TEXT multi-line textbox **auto-growing to fit content**, STRING single-line input, IMAGE/VIDEO/AUDIO/MASK path input + embedded preview), editable;
5. **🔄 Refresh** (bottom of the node) — re-queries the md file by ID and updates the form with the latest disk values (syncs after the md file is changed externally).

**Outputs** (dynamic ports, following the table node pattern; unused slots are hidden):
- `[0] ID` (STRING);
- `[1..]` each non-ID field — by type: `INT`/`FLOAT`/`BOOLEAN` output native numeric/boolean, `STRING`/`TEXT`/`IMAGE`/`VIDEO`/`AUDIO`/`MASK` output strings (TEXT may contain newlines; media is a file path);
- Last `whole row data` (STRING) — the whole row's `{id, values}` JSON string.

**Example md**:
```markdown
| ID | Name(STRING) | Avatar(IMAGE) | Height(FLOAT) | Enabled(BOOLEAN) | Description(TEXT) |
|----|-------------|-------------|-------------|--------------|-----------|
| 龙傲天-主角 | 龙傲天 | assets/avatar/lt.png | 180.5 | Yes | protagonist, three-view |
| 陈落-配角 | 陈落 | assets/avatar/cl.png | 165 | No | supporting, three-view |
```

**HTTP routes** (auto-registered by the backend):
- `POST /fallingts_mdtable/select_file` — pop the system file picker, return the absolute path
- `GET /fallingts_mdtable/read?path=` — parse the md, return the field definitions + all data rows
- `GET /fallingts_mdtable/preview?path=` — serve local image/video/audio preview by absolute path (Range supported)

### 3. Many-to-one selection `FallingTSSelector`

- The `items` textbox (comma-separated group names) provides the input port labels and the dropdown options;
- `total` group count (≥ 1, ≤ 50): left input ports = group count × number of group names, group 1's group-name inputs first, group 2 after (port labels cycle through the group names, slots stable);
- The dropdown picks one group name → each group's **selected value i** (ANY) on the right outputs that group's input value for that group name, unwired is None, and unselected branches are lazy and not executed;
- Fixed at the top-right: **selected item** (STRING, the selected group-name text) + **index** (INT, the selected group name's index, 0-based), followed by each group's **selected value** stacked in order;
- On a selection mismatch, fall back to the first group name.

### 3.1 Fan-out selection `FallingTSFanout` (mirror of many-to-one selection)

The mirror of many-to-one selection: many-to-one is "multi-group multi-input → pick one group name → each group outputs that group name's value"; fan-out is "one input per group → pick one group name → each group's output for that group name = that group's input value":

- `items` comma-separated group-name list (same source as many-to-one selection's `items`, e.g. `右面,后面,左面`, M group names): provides each output port's label and the `selection` dropdown options;
- `total` group count (≥ 1, ≤ 50) = **number of left input ports**: one `input_i` per group (ANY, `input_1` first, `input_2` after), dynamically added/removed by `total`, only the tail moves, existing wired slots never drift;
- **Right output ports = group count × group-name count** (≤ 50): group i = one output per group name (ANY), port labels cycle through the group names (e.g. `右面,后面,左面`), only the tail moves, existing wired slots never drift;
- `selection` **selected item** (dropdown, options = all group names, can be wired directly to many-to-one's **selected item**, wired value takes priority): selecting the k-th group name → group i's `input_i` routes to group i's output for that group name, group i's other outputs are **None**; when unwired and mismatched, default to the first group name;
- When unwired, each group's input is None and all groups' outputs are None;
- When `total`/`items` change: input ports add/remove + output ports (group count × group-name count) add/remove + port labels (group names) sync + node height reclaims (only shrinks, never grows);
- **Key (preload)**: segmented execution (clicking "Continue") only runs targets + targets' upstream ancestors, and each group's selected-group-name terminal output nodes (save/preview) may not be among them. `web/js/fanout.js`, on a partial submit, **merges the output nodes downstream of each group's selected group name into targets** — each group's selected-branch downstream can actually execute and get data (same mechanism as `route.js`'s false-branch completion);
- Unused ports don't enter the prompt; `IS_CHANGED` signature = `(items, total, selection)`.

### 4. Grouped switch `FallingTSSwitch`

- One `switch` (BOOLEAN) toggles **total groups** at once (up to 50 groups);
- Each group = two inputs `false_i` / `true_i` (ANY) + one output `output_i` (ANY);
- `switch` true → each group outputs `true_i`, false → outputs `false_i`;
- The frontend dynamically adds/removes ports by `total`; unused ports don't enter the prompt.

### 5. Video preview `PreviewVideo` (V3, with save)

- Follows the `IO.ComfyNode` V3 spec;
- Input `video` → encoded to mp4 and written to the **temp directory** (not output) → played in the frontend;
- Input `filename_prefix` (default `video`) + `filename_suffix` (default empty, appended after the prefix) → clicking the "Save" button, the backend writes directly to output from the video cached by execute (`{filename_prefix}{filename_suffix}.mp4`, same name overwritten, no `_sequence` suffix), **without re-running the workflow**;
- HTTP route: `POST /preview-video/save/{node_id}` (body: `filename_prefix`/`filename_suffix` + `filename_prefix_linked`/`filename_suffix_linked`);
- The frontend `web/js/preview-video.js` appends a "Save" button; `filename_prefix`/`filename_suffix` can be wired from upstream (e.g. MDTable's ID column), and save uses the value execute actually received.

### 6. Audio preview `PreviewAudioSave` (V3, with save)

- Follows the `IO.ComfyNode` V3 spec;
- Input `audio` → native `UI.PreviewAudio` writes a **flac to the temp directory** for the frontend to play;
- Inputs `filename_prefix` (default `audio`) + `filename_suffix` (default empty, appended after the prefix) + `format` (flac/mp3/opus, with quality) → clicking the "Save" button, the backend writes directly to output from the audio cached by execute (`{filename_prefix}{filename_suffix}.{format}`, same name overwritten, no `_sequence` suffix), **without re-running the workflow**;
- For multi-segment waveforms, `{prefix}{suffix}_{i}` (still no 5-digit zero-padded sequence number); `%batch_num%` can be substituted;
- HTTP route: `POST /preview-audio/save/{node_id}` (body: `filename_prefix`/`filename_suffix`/`filename_prefix_linked`/`filename_suffix_linked`/`format`/`quality`);
- The frontend `web/js/preview-audio.js` appends a "Save" button.

---

## Installation

### Option A: git clone into custom_nodes (recommended)

```bash
git clone https://github.com/falling-ts/ComfyUI-FallingTS.git ComfyUI/custom_nodes/ComfyUI-FallingTS
```

### Option B: place the repo in the project root + relative symlink

```powershell
cd ComfyUI\custom_nodes
mklink /D ComfyUI-FallingTS ..\..\ComfyUI-FallingTS
```

After installing, **restart ComfyUI** (same after code changes; after changing frontend web/js, a hard browser refresh is enough).

## Prerequisites

- ComfyUI (dev branch / v0.29+, depends on the V3 extension API `comfy_api.latest`)
- **No extra Python dependencies** (reuses ComfyUI's built-in `comfy_api_nodes.util`)

## Architecture

```
ComfyUI-FallingTS/
├── __init__.py       # entry: WEB_DIRECTORY + NODE_CLASS_MAPPINGS + sys.path
├── plugin.py         # node registration (V1 NODE_CLASS_MAPPINGS + V3 ComfyExtension, dual-track)
├── proceed/          # segmented execution control node (block/continue, cache-based)
│   ├── nodes.py      #   FallingTSContinue + HTTP routes (continue/reset/restart)
│   └── __init__.py
├── route/            # route node (total-group routing)
│   ├── nodes.py      #   FallingTSRoute
│   └── __init__.py
├── fanout/          # fan-out selector node (mirror of many-to-one: total=group count=number of inputs, outputs=group count × group-name count, selected-item dropdown)
│   ├── nodes.py      #   FallingTSFanout (each group's input_i routes to that group's selected group name's output, the rest None)
│   └── __init__.py
├── table/            # general table node (Excel-style)
│   ├── nodes.py      #   FallingTSTable (ID first column + selection dropdown, STRING outputs)
│   └── __init__.py
├── selector/         # dropdown selector node
│   └── nodes.py
├── mdtable/          # Markdown data table super-node
│   ├── nodes.py      #   FallingTSMarkDownTable + HTTP routes (select_file/read/preview)
│   ├── parser.py     #   md table parsing + value type conversion (pure functions, unit-testable)
│   └── __init__.py
├── switch/           # grouped switch node
│   ├── nodes.py
│   └── __init__.py
├── preview-video/    # video preview node (preview+save, V3; directory name contains a hyphen, loaded via importlib)
├── preview-audio/    # audio preview node (preview+save, V3; directory name contains a hyphen, loaded via importlib)
│   ├── nodes.py
│   └── __init__.py
├── preview-image/    # image preview-save node (always preview temp + click "Save" to write output, same name overwritten)
│   ├── nodes.py      #   PreviewImageSave + HTTP route (/preview-image/save)
│   └── __init__.py
├── web/js/           # frontend extensions (loaded at runtime by ComfyUI via /extensions, not part of the frontend build)
├── locales/          # i18n translations (zh/nodeDefs.json, node and control display names)
└── README.md
```

**Notes**:
- The plugin's `web/js/*.js` are loaded at runtime by ComfyUI's `GET /extensions` endpoint and **do not participate in the frontend build**; upgrading/rebuilding the frontend package directory does not affect this plugin;
- Node registration is dual-track: V1 via `NODE_CLASS_MAPPINGS` (4 nodes), V3 via `DesktopPluginsExtension.get_node_list()` (`PreviewVideo`);
- Subpackage `__init__.py` files use relative imports and don't depend on sys.path order.

## License

[MIT](LICENSE)
