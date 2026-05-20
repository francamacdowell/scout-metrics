# scout

A static code-quality analyzer for Python, JavaScript, and TypeScript. Walks a project, computes metrics per file (and one cross-file metric), emits a report, exits with a status code suitable for CI gating.

## Language

**SourceFile**:
A path discovered during the file walk, tagged with its detected language. Pre-parse.
_Avoid_: file, candidate, source path

**ParsedFile**:
The structured output of parsing one SourceFile — tokens, functions, classes, imports, errors. Language-agnostic shape; metric modules consume it without knowing which parser produced it.
_Avoid_: AST, parsed source, file model

**ParseError**:
A recoverable per-file failure (e.g., SyntaxError) captured inside `ParsedFile.errors`. Never aborts the run; the file is reported with errors and no metrics.
_Avoid_: parse failure, syntax error (those are the *cause*; ParseError is the *record*)

**MetricValue**:
One measurement emitted by a metric, scoped to a function/class/file/repo, carrying a numeric value and a derived `Severity`.
_Avoid_: result, score, reading

**Scope**:
Where a MetricValue applies: `function`, `class`, `file`, or `repo`. The metric module decides the scope; the aggregator preserves it.

**Severity** / **severity band**:
The *advisory* classification of a MetricValue — `ok` / `warn` / `error` — derived by mapping the value through the metric's built-in bands (e.g. CC bands `[10, 20, 50]`). Drives report colors only. **Does not affect exit code.**
_Avoid_: level, status, grade

**Threshold**:
A *policy* gate set via CLI (`--threshold cc=15`) or config. A MetricValue whose value crosses its threshold produces a **Violation**. **Drives exit code 1.** Independent of Severity.
_Avoid_: limit, max, ceiling (in code, reserve "threshold" for the CLI-overridable gate)

**Violation**:
A threshold breach. Emitted by the aggregator, listed in `RunReport.violations`, surfaces in both text and JSON output.

**FileMetric** / **RepoMetric**:
Two protocols defined by *what they consume*. A `FileMetric` consumes one `ParsedFile` and emits per-file/function/class MetricValues; a `RepoMetric` consumes the set of all ParsedFiles and emits repo-scoped MetricValues (Duplication is the only one in v0.1).

**FileReport** / **RunReport**:
A `FileReport` is the per-file aggregation (ParsedFile + all MetricValues for that file). A `RunReport` is the whole-run aggregation (all FileReports + repo metrics + violations + summary).

## Relationships

- A **SourceFile** is parsed into one **ParsedFile** (which may carry **ParseErrors**).
- A **ParsedFile** is consumed by one or more **FileMetrics**, each yielding one or more **MetricValues**.
- The set of **ParsedFiles** is consumed by zero or more **RepoMetrics**, each yielding repo-scoped **MetricValues**.
- A **MetricValue** carries a **Severity** (band-derived, advisory).
- The aggregator compares each **MetricValue.value** to its **Threshold** (if set) and emits a **Violation** on breach. **Severity** and **Violation** are computed independently — a value can be red but non-violating, or green but violating, depending on user thresholds.

## Example dialogue

> **Dev:** "If a function has CC = 12 and the user passed `--threshold cc=20`, what shows up in the report?"
> **Reviewer:** "The MetricValue is `severity=warn` (because the default band breaks at 10) and there's *no* Violation. Text output colors the row yellow; exit code is 0."
> **Dev:** "And if no `--threshold` is passed?"
> **Reviewer:** "Then no Violations can be emitted for CC — the bands still classify the row as yellow, but exit code is 0. Bands are advisory; only thresholds gate exit code."

## Flagged ambiguities

- **"threshold" was used for both the CLI gate and the band edges** — resolved: "threshold" is reserved for the user-settable CLI policy gate; band edges are "bands" or "severity bands". Different things.
