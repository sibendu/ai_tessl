# Oracle Analysis Rules

## Source Precedence

Use the strongest source for each fact:

1. Supplied runtime observation for observable legacy behavior.
2. Forms XML/FMT for structure, properties, trigger text, and program units.
3. PLD for module/shared library source and runtime property overrides.
4. SQL DDL for physical database datatypes, defaults, constraints, indexes, comments, grants, and triggers.
5. ERR compile logs for object existence and compilation evidence.
6. FMB/FMX/PLL binary strings only as corroboration.
7. Screenshot for visible labels, grouping, and approximate layout.

Resolve conflicts by domain. For example, DDL wins for a physical datatype, XML wins for an item prompt, and a PLD `SET_BLOCK_PROPERTY` call wins over a design-time CRUD property at runtime.

## Module Grouping

- Establish module roots from FMB/FMX/FMT/ERR and parseable Forms XML.
- Normalize `_fmb.xml`, `-fmb.xml`, `_form.xml`, and similar export suffixes to the module root.
- Associate `<module>l.pld` and `<module>l.pll` with `<module>`.
- Parse `.ATTACH LIBRARY`, attached-library XML elements, and direct routine calls before associating shared libraries.
- Do not create specifications for shared libraries, object libraries, menus, or DDL-only files unless they are independently runnable screens.
- When multiple forms implement one business screen, keep separate module specs unless explicit runtime evidence proves they are one deployable interaction.

## Forms XML

Oracle Forms XML varies by Forms release and export flags.

- Compare element and attribute local names, ignoring namespace prefixes.
- Accept `Module`, `FormModule`, `ModuleParameter`, `FormParameter`, `Block`, `Item`, `Trigger`, `ProgramUnit`, `RecordGroup`, `LOV`, `Canvas`, and `Window` variants.
- Decode XML entities in trigger and program-unit text, including text encoded more than once.
- Preserve inherited/overridden/default property provenance where available.
- Treat `DatabaseItem=FALSE` as non-database even when the name resembles a column.
- Treat an explicit `ColumnName` as the primary item-to-column mapping.
- Treat block `QueryDataSourceName` and DML target properties as authoritative candidates, then corroborate against SQL and DDL.

Forms2XML `DUMP=ALL` may report missing object-group children. Record the warning. It is normally a framework-parity gap, not proof that the business module failed to export.

## Effective Runtime Behavior

Calculate effective behavior in this order:

1. Design-time module/block/item properties.
2. Inherited object and property overrides.
3. `WHEN-NEW-FORM-INSTANCE`, `PRE-FORM`, and startup library property changes.
4. State-dependent property changes in reachable triggers/routines.
5. Supplied runtime observation.

Report both legacy design-time and effective runtime CRUD when they differ. Do not decide target editability in this extraction stage.

## Reachable Logic

Build a shallow call graph from form triggers and program units:

1. Start with form, block, item, button, timer, and menu-trigger entry points.
2. Follow module program units.
3. Follow module-specific PLD routines.
4. Follow called shared-library routines only as needed to establish their outcome.
5. Stop at generic framework routines after classifying the observable effect.

Do not include every routine in a large shared PLD. Record unresolved custom calls that can change data, validation, reports, files, integrations, or navigation.

## Data And SQL

- Parse explicit `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, cursors, dynamic SQL, package calls, and Forms base-table DML.
- Parse sequence usage such as `NEXTVAL` and `CURRVAL`, and include sequence DDL when supplied.
- Preserve joins, optional joins, predicates, order, defaults, derived expressions, and exception paths.
- Map table aliases to physical objects.
- Use DDL as authority for datatype, nullability, default, and constraints.
- Search all `.sql` files recursively below `ddl/`; nested folders such as `views/`, `view/`, `sequences/`, `sequence/`, `tables/`, `indexes/`, and `triggers/` are part of the DDL set.
- Recognize table, view, materialized view, sequence, synonym, index, trigger, package, procedure, and function definitions when inventorying DDL evidence.
- Do not assume a supporting index is a foreign-key constraint.
- Distinguish public synonyms from physical owner objects when known.
- State when no database triggers were supplied or confirmed.
- For audit fields, identify the population mechanism or record it as unknown; do not assume Forms or database ownership.

## Delete, Save, And Validation Behavior

Oracle Forms applications often hide material business behavior inside generated or conventional program units. Treat these as source-derived behavior when reachable from the module.

- Trace from destructive and persistence entry points: `PRE-DELETE`, `ON-DELETE`, `KEY-DELREC`, `PRE-INSERT`, `PRE-UPDATE`, `PRE-COMMIT`, `WHEN-VALIDATE-RECORD`, `WHEN-VALIDATE-ITEM`, action buttons, toolbar triggers, and menu triggers.
- Follow module program units and companion PLD routines before declaring behavior unresolved. Generated-looking routines such as `CGRI$CHK_*` and `CGRI$WRN_*` may still contain module-specific dependency checks.
- Classify each dependency check by observable effect:
  - hard blocker: the legacy form prevents the operation;
  - warning/confirmation: the legacy form allows continuation after a warning or second confirmation;
  - cascade: the database or Forms logic removes dependent rows automatically;
  - validation/default/derivation: the dependency affects save/query results without blocking deletion;
  - unresolved: source is missing or dynamic behavior cannot be resolved.
- Map each checked object to supplied DDL after recursive `ddl/` search. If object DDL is missing, name the exact table, view, sequence, synonym, or package instead of leaving a broad "delete behavior unknown" question.
- Compare Forms checks with DDL constraints. If a Forms warning checks a child table but the database has `ON DELETE CASCADE`, record both; do not collapse them into one generic referential-integrity statement.
- Include the user-facing message code or message text when the routine raises, warns, confirms, or suppresses an operation.

## UI Interpretation

- Use screenshots and geometry to identify grids, details, tabs, action areas, hierarchy panels, and modal windows.
- Keep hidden/control/system blocks in a separate technical inventory while recording any business effect.
- Treat `DSP_` and `DRV_` as hints for display/derived fields, not proof.
- Record legacy widget type, visible label, grouping, geometry, canvas/tab placement, and runtime property changes.
- Do not replace widgets, propose target filters, or author target UI copy in this stage.

## Screenshot Matching

Rank screenshot candidates using:

1. exact normalized module ID in filename;
2. exact or near-exact screen title;
3. overlap of significant title tokens;
4. visual confirmation of the title, labels, and business subject;
5. exclusion of Forms Designer, source trees, unrelated dialogs, and duplicate captures.

Attach every plausible candidate rather than silently choosing one. If two modules share similar titles, use visual content and module-specific labels to lower or raise confidence. Record each candidate, score/rationale, and ambiguity in the appendix.

## Evidence Boundary

- Preserve legacy facts without implying they are approved target requirements.
- Do not write a Behavior Change Register, target treatment, implementation proposal, or migration disposition.
- Record application-wide authentication, authorization, shell, or framework behavior only when supplied source makes it relevant to the selected module.
- Preserve target decisions found in older specifications as historical content outside this extraction; do not import them as evidence.

## Errors

- Inventory explicit application codes, Oracle errors, Forms errors, constraint names, and exception outcomes.
- If message text is unavailable, use the code as placeholder text and mark `Message text TBD`.
- Preserve SQL/error/stack evidence in technical sections with appropriate source locators.
- Keep decoded but unreachable DML error mappings in the legacy catalogue and label reachability accurately.

## Behavior Coverage Scenarios

- Use synthetic placeholders, never production rows or sensitive values.
- Represent each extracted entry-condition-action-outcome slice so reviewers can see which behavior families were covered.
- These rows validate extraction coverage; they are not target application test cases.
- Group scenarios by the operation local key and identify the individual path by its natural trigger or routine name.
