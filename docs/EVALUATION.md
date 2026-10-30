# Evaluation and limitations

## Engineering checks

On October 30, 2026, the English release passed **64 Python tests**, including isolated PostgreSQL integration. A separate JavaScript DOM-fixture test checked English defaults and Chinese/English switching; it is not a visual browser test. The tests cover source integrity, citation validation, paid-call controls, HTTP fixtures, review persistence, and preview behavior. Mock provider responses are explicitly fixtures and are not real model performance evidence.

## English retrieval diagnostic

`evaluation/development.json` contains 20 assistant-translated versions of previously seen Chinese development questions, with reference segment IDs inherited from the original project. The references are not independently human-validated. Run `python scripts/evaluate_retrieval.py` without a model key to repeat the diagnostic.

The recorded run found at least one selected reference in the top three for **13/19 scored cases**. One case has no selected reference and is excluded from that denominator. The full per-case report is `evaluation/english-retrieval-results-2026-10-30.json`. This metric does not measure whether all necessary evidence was retrieved, whether the answer was correct, or how the system performs on unseen customers. Translation changes the questions, so this result should not be treated as directly comparable to the historical Chinese score.

## Real model case

The original project ran GPT-6 Luna three times on a previously seen Chinese question about a frontend secret key. The first response omitted a user-token qualification; the second avoided the broad RLS claim but omitted the condition; after the generation requirements and citation checks changed, the third response described both token cases and cited the relevant source. The responses were saved in the original database.

The prompt changed between those calls. The third result is one example under the final original-language prompt, not three identical-condition trials or an independent holdout evaluation. The English demo displays an explicitly labelled assistant translation of that real Chinese response. It also contains a separate, unmodified English model response from the earlier project's keyword run on an empty-array question; that historical English response predates the current English-release prompt and does not validate it.

One initial real GPT-6 Luna call using the English release prompt failed output or citation validation; the raw invalid response was not retained, so its exact failure is unknown. Its result is recorded in `evaluation/english-model-example-2026-10-30.json`.

Six subsequent attempts on the same previously seen English question produced five validated drafts and one schema-validation failure. The successful drafts describe both user-token conditions and cite the secret-key and RLS sources. Each result, including the failure, is recorded in `evaluation/english-model-followup-01-2026-10-30.json` through `evaluation/english-model-followup-06-2026-10-30.json`. The failure's raw response was not retained, so its exact schema error is unknown. The gateway was updated during these attempts to report validation categories more clearly; the generation requirements did not change. The demo displays the exact sixth response. These seven English attempts, with two failures, concern one known question and do not establish general model reliability. The source and the answer still require human review.

The original project also retains historical results for 20 development cases and 10 holdout cases; some cases with no retrieved evidence skipped model generation. English question translations, actual status/usage metadata, cited IDs, and hashes of original response text are preserved in `evaluation/historical-model-metadata.json`. They do not replace the original model output files, which remain in the original project. Those questions were later seen during development, so subsequent changes cannot be presented as a fresh independent holdout result. No independent expert has reviewed all cases.

## Remaining limits

- The seven snapshots are a limited, fixed version of the Supabase docs; they are not the entire documentation site and may differ from current pages.
- The cross-section qualification rule covers a known secret-key condition, not every exception in the corpus. The English vector example in the original project missed a grant-versus-empty-result source.
- The secret-key output guard checks for a token-related term and an appropriate citation; it cannot fully determine whether the wording is semantically correct. One of six follow-up English attempts failed schema validation, and the earlier attempt also failed validation.
- English and Chinese UI switching is supported, but this release does not claim comprehensive bilingual answer quality.
- A fresh virtual environment and disposable database were tested on the same machine. A complete installation on another clean computer has not been independently tested.
- Authentication, tenant isolation, automatic sending, account billing controls, and public deployment are outside the local demo.
