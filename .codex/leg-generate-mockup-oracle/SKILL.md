---
name: leg-generate-mockup-oracle
description: Generate high-fidelity, functional Next.js mockup screens for Oracle Forms modernization from one or more module evidence folders and linked screenshots. Use when asked to preserve legacy fields, tabs, grids, section organization, and business behavior while applying minimal web modernization; combine separate Maintain/Retrieve-style forms into a unified search, filter, add, edit, and delete experience; or extend a target Next.js application while matching its existing Reference / Products / Maintain Products visual and interaction conventions.
---

# Generate Oracle Modernization Mockups

Create functional target-state mockup screens in an existing Next.js project. Default to high-fidelity, minimal modernization: preserve evidence-backed business content and form organization while adapting the workflow and controls for the web. Use architecture artifacts to constrain the target design and the target application's Maintain Products screen as the reference for shared visual and interaction conventions.

## Inputs

Accept these inputs:

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `module_names` | Yes | None | One or more evidence module folder names, separated by commas. Example: `standard-contract-maintain, standard-contract-retrieve`. |
| `project_directory` | No | `C:\workspace\replatform\GALA\galanext` | Existing Next.js project where mockup code is generated. |
| `Tenant` | No | `default` | Agentic SDLC tenant key. |
| `Project` | No | `consumer-care-ai` | Agentic SDLC project key. |
| `Project repo` | No | `auto` | Optional explicit Agentic SDLC project repository path. |
| `Notes` | No | None | Optional route, scope, naming, or rationalization guidance. |
| `overwrite` | No | `false` | When `true`, rebuild only the requested feature's mockup-owned code as a first-run generation. When omitted or `false`, improve an existing mockup incrementally. |

Stop and request `module_names` when it is missing or empty. Split comma-separated values, trim whitespace, remove empty values, and de-duplicate names while preserving their input order.

Parse `overwrite` as a Boolean. Accept only `true` or `false` case-insensitively; ask for correction when another value is supplied. The explicit `overwrite` input controls run mode. If `Notes` contradict it, ask before changing code.

## Resolve Project Scope

Resolve exactly one Agentic SDLC project repository:

```text
agentic-sdlc-data/tenants/<tenant>/projects/<project>/repo
```

Use the default tenant and project when omitted, state those defaults, and verify the repository and `project.yaml` exist. Require `objective_type: legacy_modernization`; report a mismatch before making changes.

Resolve `project_directory` to an absolute path and verify it is an existing Next.js project from its package manifest and project structure. The Agentic SDLC project repository is controlled evidence and architecture input. Write generated application code only under `project_directory`.

## Resolve Module Evidence

For every requested module, search immediate directories under:

```text
<project-repo>/evidence/features/<module-name>/
```

Resolve folders as follows:

1. Prefer an exact folder-name match.
2. If no exact match exists, compare normalized names case-insensitively, treating spaces, underscores, and hyphens as equivalent.
3. If still unresolved, rank folder names by similarity using token overlap and edit similarity.
4. Automatically select one clearly best match and report the requested-to-resolved mapping.
5. If leading candidates are materially ambiguous, stop before code changes and ask the user to select a folder.
6. If no credible match exists, report the unmatched input and available feature folders.

Do not silently omit an unresolved module.

Read all relevant evidence files in each resolved module folder. Follow relative links from the evidence files and inspect every available linked screenshot or image. Resolve image paths relative to the evidence file first, then the project repository. Record missing or unreadable linked images as evidence gaps.

Extract only evidence-supported information, including:

- module purpose and business nouns;
- fields, labels, required indicators, default values, LOVs, filters, and validation messages;
- tabs, blocks, grids, buttons, query behavior, navigation, and record state;
- add, edit, delete, retrieve, select, confirm, cancel, and error flows;
- relationships between separate Maintain, Retrieve, View, or Query forms;
- visible status, paging, and record-navigation behavior.

Treat screenshots as authoritative evidence for visible field grouping, section boundaries, tab organization, grid structure, relative placement, information density, control type, and prominent actions. Do not reproduce Oracle Forms chrome pixel-for-pixel, but do not substantially reorganize or summarize this evidence without an explicit user instruction or architecture decision.

When screenshots show only the active tab, use the evidence file's field and control inventory to implement the non-visible tabs. Record the lack of tab-specific screenshots as a visual evidence gap; it is not a reason to omit those fields.

Do not invent business rules, authorization, production values, integrations, or persistence behavior. Clearly keep sample data deterministic and mock-only.

## Apply Target Guidance

Read relevant artifacts under:

```text
<project-repo>/architecture/decisions/
<project-repo>/architecture/target-to-be/
```

Apply guidance according to responsibility, rather than allowing one source to replace another:

1. explicit user instructions and `Notes`;
2. accepted architecture decisions and target-to-be artifacts for target workflow, technical, and cross-application constraints;
3. module evidence and screenshots for the business field set, labels, controls, tabs, grids, actions, validation behavior, and module-specific section organization;
4. established target application behavior and components for theme, typography, spacing, control styling, dialogs, tables, navigation, responsiveness, accessibility, and feedback.

Architecture may replace or consolidate a legacy workflow, but it does not erase evidence-backed fields, actions, or business sections unless the decision explicitly says so. Report unresolved material conflicts instead of guessing.

Before designing or editing, inspect `project_directory` for:

- `package.json`, routes, layouts, navigation, and data conventions;
- shared components, theme tokens, fonts, spacing, colors, CSS or Tailwind setup;
- existing forms, LOV/dropdown controls, text inputs, tables, pagination, and record navigators;
- modal/dialog conventions for add, edit, delete, confirmation, validation, and messages.

Always locate the implementation reached through:

```text
Reference -> Products -> Maintain Products
```

Search route labels, navigation definitions, page titles, and component names until the route and its supporting components are identified. Use this screen as the UX oracle for theme, typography, spacing, control dimensions and styling, search behavior, results presentation, pagination or record navigation, action treatment, dialogs, validation, and feedback. Reuse its components and patterns wherever practical. Do not use it as authority to collapse, rename, or reorganize module-specific business sections or omit evidence-backed fields. Do not approximate the reference from its name alone.

Also search the target project for an existing screen, route, or component for the requested module, including variants labeled `Old`, `Legacy`, or similar. Existing code and a running mockup are implementation baselines and field-coverage cross-checks, never evidence authority. Preserve separate `Old` or `Legacy` screens unless the user explicitly includes them in replacement scope. Prefer extending the most evidence-faithful structure over creating a substantially reimagined form.

## Resolve Existing Mockup And Run Mode

Before editing, identify the requested target mockup from resolved modules, `Notes`, routes, navigation labels, imports, feature-specific components, tests, styles, and mock data. Do not equate a separate `Old` or `Legacy` route with the target mockup.

Use a feature ownership manifest when available:

```text
<project_directory>/.agentic-sdlc/mockups/<feature-key>.json
```

The manifest should record `schema_version`, tenant, project, resolved modules, target routes, navigation identity, fully mockup-owned files, shared files patched only at identified integration points, and the last successful run mode. Create or update it after successful generation. Never treat the manifest as business evidence.

For a pre-existing mockup without a manifest, infer ownership conservatively from its route import graph, feature-specific filenames, and navigation target. Do not classify shared layouts, design-system components, or broad data modules as mockup-owned merely because the screen imports them. Ask before destructive replacement when ownership remains ambiguous.

Select exactly one run mode:

- `first-run`: no target mockup exists. Generate it from freshly analyzed evidence, architecture, `Notes`, and target application conventions.
- `incremental`: a target mockup exists and `overwrite` is omitted or `false`. Audit the complete existing implementation against fresh evidence and `Notes`, then patch only verified gaps, conflicts, stale behavior, and unsupported invention.
- `overwrite`: a target mockup exists and `overwrite: true`. Reanalyze evidence as a first run and reconstruct only mockup-owned files. Existing mockup design choices are not generation authority.

If `overwrite: true` is supplied and no mockup exists, use `first-run`. In overwrite mode, shared navigation, layouts, and components may only receive narrow integration edits; do not replace whole shared files. Preserve unrelated screens and separate legacy variants. Remove obsolete files only when the ownership manifest or import analysis proves they are exclusively owned by this mockup.

In incremental mode, inspect the current rendered screen and exercise its material interactions before editing when it is already running. Use a URL supplied in `Notes` when present; otherwise derive the route and use an identifiable running project server. If it is not running, inspect the code and start the project when practical. Record inability to inspect the pre-edit runtime, but do not use that absence to guess.

Classify every evidence-to-existing-code comparison as `correct`, `missing`, `incorrect`, `unsupported`, `stale`, or `explicitly-changed`. Preserve correct behavior, add missing behavior, correct conflicts, remove unsupported invention within owned code, and retain an explicit change only when its user or architecture authority is identifiable. A prior generated field, table, workflow, or mock record does not become valid because it already exists.

## Build The Legacy UI Inventory

Before designing or editing application code, build a compact evidence-to-UI inventory for every resolved module. This is an internal agent working check, not a new user-maintained artifact or required deliverable. Include:

- every visible header and primary form field, including label, control type, required/read-only state, and LOV evidence;
- every selection, lookup, validation, and defaulting interaction, including trigger, available-value source, derived/cleared fields, and validation/error outcome;
- every tab or page and all fields assigned to it in the evidence, with a field count;
- every child grid or repeating block and its columns;
- every related-detail button, footer action, query action, navigator, and record-level command, including its trigger operation, destination form/window/block, passed parameters, and resulting surface type when known;
- every screenshot inspected and the form state or active tab it shows;
- missing screenshots, ambiguous controls, conflicting labels, and other evidence gaps.

Create a target disposition for each field and section: `preserved`, `moved`, `combined`, `replaced`, or `omitted`. For actions use: `preserved-launcher`, `target-modal`, `target-route`, `target-drawer`, `inline-evidenced`, `placeholder-blocked`, `replaced-by-explicit-decision`, or `omitted-by-explicit-decision`. Every non-preserved disposition requires an evidence-backed, architecture-backed, or explicit user rationale. Do not start implementation while evidence-supported items have no disposition.

Maintain field-level provenance for every rendered form field and table column. A button label, related database table, TypeScript type, mock dataset, or plausible business convention is not evidence that a table or field is visible in the legacy UI.

Treat each evidence-backed LOV, dropdown, lookup, or selection-triggered derivation as a material interaction. The inventory must identify the rendered control type and every visible output field it updates, clears, locks, enables, disables, or derives. A field may not be implemented as a generic text input when its control type is evidenced as a LOV, dropdown, or lookup unless an explicit user or accepted architecture decision authorizes the replacement.

If the evidence is insufficient to decide a material field, section, or workflow behavior, ask the user before making the affected design choice. Continue with unaffected work when practical.

## Rationalize Multiple Modules

When multiple module names represent related Oracle Forms screens, synthesize one coherent target module unless the user explicitly requests separate screens.

The rationalization boundary is the set of modules explicitly resolved from `module_names`. A child form discovered through a trigger is a dependency, not automatically part of the parent module or permission to absorb its UI. Consolidate a child form only when its module evidence was also requested, an accepted architecture decision requires it, or the user explicitly expands scope.

Use this target interaction model where supported by the evidence:

```text
search/filter -> results -> select record -> view/edit or delete
                                    -> add new record
```

Rationalize the workflow, not the domain layout. Combine requested Maintain, Retrieve, Query, and View screens that operate on the same business entity, but preserve the maintain form's evidence-backed field grouping, tabs, related grids, and actions by default. Consolidate only genuinely duplicated fields and actions. Use tabs or panels only for legacy sections evidenced as tabs, pages, or inline sections. Use the existing target modal pattern for add, edit, delete confirmation, and related messages.

The default target shape is:

1. a web search/filter area with 4 to 8 evidence-supported primary search fields unless the user specifies otherwise;
2. a searchable and pageable result set using the target application's conventions;
3. add, view, and edit experiences that retain the legacy maintain form's section hierarchy and field coverage;
4. delete confirmation and related feedback using the target application's modal conventions.

Do not replace a detailed maintain form with summary cards, dashboard metrics, a generic `Overview` tab, or a substantially new information architecture unless the evidence, architecture, or user explicitly calls for that change.

Create separate target routes only when evidence or architecture shows genuinely independent business responsibilities. Document the rationalization, including which legacy modules became each target route and which legacy navigation-only behavior was intentionally replaced.

## Preserve Action And Child-Screen Semantics

Treat legacy navigation and launch behavior as part of the evidence-backed user experience:

- Preserve an `OPEN_FORM` or `GO_FORM` action as a launcher to a separate target surface unless the user or an accepted architecture decision explicitly authorizes consolidation.
- Treat `GO_ITEM` into a separately named window or maintenance block as a separate maintenance surface by default, such as the target application's established modal, drawer, or route pattern. Do not silently flatten it into an inline summary.
- Preserve the source record context and evidenced parameters passed to a child experience.
- Do not convert a launcher into an inline table, tab, accordion, or embedded panel merely to make the mockup appear complete.
- Require evidence for every field, column, LOV, action, and record shape rendered inside a child experience.

When a launched child form lacks screenshots or sufficient field inventory, preserve the launcher and record the child screen as blocked by missing evidence. Continue unaffected parent-screen work. Ask for the missing evidence or an explicit target-design decision before implementing the child content. If the user explicitly authorizes a placeholder, create only a separate empty shell carrying evidenced context and clearly mark the evidence gap in the completion report; do not invent business fields, columns, LOVs, or records.

## Implement The Mockup

Inspect existing code before editing and follow its framework, language, routing, component, styling, state, linting, and testing conventions.

- Reuse existing layout, navigation, components, icons, tokens, utilities, and mock-data patterns.
- Keep changes scoped to the new mockup and the minimum navigation or routing integration needed to reach it.
- Avoid new dependencies unless the existing stack cannot support required behavior.
- Preserve unrelated work and do not overwrite an existing screen without explicit instruction.
- When an existing module screen provides better evidence coverage, preserve it and reuse its form structure; add the new route or menu label without removing the old route or entry unless explicitly requested.
- Make search/filter, result selection, pagination or record navigation, add, edit, delete, cancel, validation, empty, and no-results states functional in the browser.
- Use deterministic in-memory mock data unless the project already provides a mock API convention.
- For every evidence-backed LOV or selection interaction, provide deterministic representative options and implement the evidenced visible outcomes locally. Selecting an option must update, clear, enable, disable, or derive the corresponding fields exactly as the internal inventory records. Do not defer an evidence-backed visible derivation to a future backend implementation.
- Populate evidence-supported tabs, grids, LOVs, and add/edit fields with representative deterministic mock values. Do not add fields, columns, statuses, codes, roles, relationships, or workflows solely to make the mockup look complete.
- Match the reference screen's responsive behavior and accessibility conventions, including labels, focus, keyboard operation, dialog semantics, and readable error feedback.
- Give field labels and control wrappers distinct semantic classes or elements. Avoid broad positional selectors such as `.field > span` when labels and control wrappers can use the same element type, and verify that control wrappers do not inherit label alignment rules.
- Keep screenshots out of the rendered product UI unless the user explicitly asks to display them.

Add a short source note in code only when the project convention permits comments, for example:

```ts
// Mockup derived from Agentic SDLC evidence/features/standard-contract.
```

## Workflow

1. Resolve tenant, project, project repository, `module_names`, `project_directory`, and `overwrite`.
2. Match every requested module to one evidence feature folder and report fuzzy matches.
3. Read evidence files and inspect linked screenshots.
4. Read relevant architecture decisions and target-to-be artifacts.
5. Locate and inspect `Reference -> Products -> Maintain Products` and its shared components.
6. Discover the existing target mockup, resolve ownership, select the run mode, and inspect its current runtime when available.
7. Build the complete internal legacy UI and action inventory, including selection and derivation contracts, and assign a target disposition to every item.
8. In incremental mode, compare the full existing implementation against the fresh inventory and classify every difference. In overwrite mode, use existing code only to establish ownership and safe integration boundaries.
9. Rationalize only the requested legacy modules into target routes and interaction flows while preserving the maintain form's organization and child-launch semantics.
10. Implement or patch the functional Next.js mockup using established application conventions.
11. Integrate navigation only as needed to make the screen reachable, preserving existing routes and menu entries unless replacement was explicitly authorized.
12. Validate code, evidence coverage, selection and derivation outcomes, action surface types, and the screen in a browser at desktop and mobile widths.
13. When a check exposes a discrepancy, return to the inventory and implementation steps, repair the mockup, and rerun the affected checks. Continue this internal refinement loop until all completion gates pass or a genuine evidence gap, architecture conflict, or external runtime blocker prevents completion.
14. Create or update the feature ownership manifest after successful validation.
15. Summarize run mode, mappings, rationalization, implementation delta, validation, and evidence gaps.

## Validation

Run the target project's available checks in the order supported by its scripts, normally:

```text
lint -> typecheck -> test -> build
```

Run `git diff --check` for changed files. Start the development server when needed and inspect the generated route in a browser. Verify that the screen renders, interactions work, dialogs follow the reference convention, text fits, controls do not overlap, and desktop and mobile layouts remain usable. Distinguish failures caused by the change from unrelated pre-existing failures.

When linked screenshots show tabs or other selectable form states, open and compare every screenshot-backed state in the rendered mockup before reporting success; do not validate only a sample. Correct material differences in field alignment, grouping, and label-to-control proximity unless an explicit user or architecture decision authorizes them.

Complete an evidence coverage check before reporting success:

- all legacy header and primary fields are represented or have a documented disposition and rationale;
- all evidence-listed tabs and their fields are represented;
- all child grids and evidence-listed columns are represented;
- all LOVs and material control types are represented appropriately;
- all related-detail buttons and material actions retain their evidenced launch operation and surface type or have an explicit decision authorizing the change;
- every rendered field and table column has evidence, architecture, or explicit user provenance;
- every external child target without sufficient evidence remains a launcher or an explicitly authorized empty placeholder;
- no child form outside the resolved `module_names` was silently absorbed into the parent mockup;
- search, add, view/edit, delete, validation, cancel, empty, no-results, and navigation states work;
- the result preserves the recognizable legacy section organization while using target application styling;
- existing screens and navigation remain present unless the user explicitly approved replacement.

Require these completion gates:

```text
unsupported_surface_count = 0
unverified_rendered_field_count = 0
unapproved_interaction_change_count = 0
unverified_material_interaction_count = 0
unverified_selection_derivation_count = 0
```

Browser-test every material action and confirm its resulting surface type: route, modal, drawer, inline evidenced content, or blocked launcher. An evidenced launcher must not unexpectedly reveal an inline table. In incremental mode, verify that the patch did not regress previously correct behavior. In overwrite mode, verify that only mockup-owned files were reconstructed and shared integrations received narrow edits.

For every evidence-backed LOV, dropdown, lookup, or selection-triggered derivation, browser-test at least one representative selection and verify all evidenced visible outputs. This includes populated, cleared, enabled, disabled, read-only, derived, and error states. If a dynamic source is unavailable for a mockup, use deterministic mock options only when the evidence establishes the option shape and visible outcomes; otherwise stop for missing evidence rather than inventing behavior.

Perform these checks as an internal self-review loop. Do not ask the user to prepare, maintain, approve, or manually reconcile an inventory, derivation matrix, test checklist, or similar process artifact. Ask only for a genuine material ambiguity, missing source, unresolved authority conflict, or required scope decision.

If any check fails, continue implementation or report the specific blocker. Do not describe a mockup as complete when evidence coverage is materially incomplete.

## Completion Report

Report:

- selected tenant, project, project repository, and target project directory;
- requested module names and resolved evidence folders, including similarity matches;
- selected run mode, whether an existing mockup was detected, whether its pre-edit runtime was inspected, and the URL when used;
- target route or routes and navigation entry;
- legacy-to-target rationalization decisions;
- concise evidence coverage totals by form area, tab, grid, action, and selection/derivation interaction; include detailed provenance and non-preserved dispositions only when requested or when a gap, conflict, or deviation needs a user decision;
- child-form launch targets, evidence availability, and child experiences intentionally not generated;
- files reused, created, patched, reconstructed, or removed, distinguishing mockup-owned files from shared integration files;
- unsupported prior UI removed or retained by explicit decision;
- checks and browser scenarios run with results;
- missing screenshots, ambiguous evidence, architecture conflicts, or other gaps.

Do not create commits, tags, pushes, releases, baselines, approvals, or deployments unless explicitly requested.
