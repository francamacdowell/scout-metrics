# Workers carry their SourceFile through the pipeline

The per-file worker returns `(SourceFile, ParsedFile, list[MetricValue])` instead of `(ParsedFile, list[MetricValue])`. The aggregator iterates these triples directly — it does not zip a separate `source_files` list with `worker_results` by index.

Previously, `aggregator.aggregate` paired `source_files[i]` with `worker_results[i]` via `zip(..., strict=False)`. Any future change that returned results out of submission order would silently mis-attach `rel_path` to the wrong `FileReport`, and `strict=False` meant a length mismatch would fail silently.

Considered keeping submission order (`executor.map`, or `submit` with an index re-sort). Both work but leave the footgun in place. Carrying the `SourceFile` makes order irrelevant to correctness, which unlocked the per-file progress UI as a side benefit.

`ParsedFile.path` is `SourceFile.abs_path` — the redundancy is intentional. It is the explicit identity that prevents implicit positional coupling.
