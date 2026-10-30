# Development retrieval diagnostic

`development.json` contains assistant-translated versions of 20 previously seen synthetic questions. The candidate reference segment IDs were inherited from the original project's frozen development references; they have not all been independently human-validated. The translation does not preserve the exact wording of the historical evaluation.

Run `python scripts/evaluate_retrieval.py`. A reference hit means at least one preselected segment appears in the first three results. A case without any selected reference is excluded from the scored denominator. This is a development diagnostic, not an answer-accuracy score or an independent evaluation.

The stored English diagnostic results are in `english-retrieval-results-2026-10-30.json`. `historical-model-metadata.json` records English question translations, original result-file hashes, actual model-call status, usage, latency, cited IDs, and original draft hashes for the 30 historical cases. Historical model outputs and the original Chinese evaluation records remain in the original project; they were not rewritten as English model outputs.

`english-model-example-2026-10-30.json` records an initial real English model call that failed output or citation validation. Its invalid raw output was not retained, so the precise cause is unknown. Six subsequent attempts are recorded in `english-model-followup-01-2026-10-30.json` through `english-model-followup-06-2026-10-30.json`: five passed validation and one failed schema validation. These are repeated trials on a single known question, not an accuracy score.
