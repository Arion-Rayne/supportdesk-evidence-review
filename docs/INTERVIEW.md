# Interview notes

## The problem

A support agent may need to search documentation, identify the part relevant to a customer question, and draft a careful response. A plausible model response can omit a condition or invent a source. This demo makes evidence visible and keeps a reviewer in control.

## A concise explanation

> I built a local support-drafting demo around fixed Supabase documentation. A reviewer submits a synthetic question; the app retrieves source excerpts with URLs and line numbers, optionally generates a response, and saves human edits separately from the original model output. I compared keyword and vector retrieval and retained the simpler keyword method as the default because it performed better on the small development diagnostic. The model may still miss conditions, so all output requires human review.

Adapt the ownership wording to accurately describe your own contribution and your use of AI assistance. This is a portfolio demo, not a claim of production deployment or measured customer impact.

## Useful technical questions

**Why use a database instead of only files?** The original files provide a fixed, auditable knowledge source. PostgreSQL stores imported segments, tickets, model runs, reviews, and optional embeddings, allowing saved work to be reopened and compared.

**What is retrieval-augmented generation?** The program retrieves relevant passages first, then supplies them with the question to the model. The model drafts a reply from that input. It can still make mistakes, so the app checks citation IDs and requires human review.

**What did you change after a failure?** A broad secret-key statement omitted a user-token condition elsewhere in the docs. A targeted retrieval rule adds that source, and the generation prompt and output checks require the condition and its citation. The final response met the criterion once; this is not proof of stable accuracy.

**What does `database.current_segments()` mean?** In Python, `.` accesses an attribute on an object or module. `database` is the imported module; `current_segments` is a function in it; `()` calls that function. The returned segments are then passed to the retrieval function.

**What would you improve next?** Obtain independent labels and unseen cases, evaluate retrieval and reply quality separately, test a clean installation on another machine, and add authentication and tenant isolation before any public deployment.
