# Two-minute demo walkthrough

This walkthrough uses synthetic questions and the free keyword search. It does not need a model API key or generate a new model response. Start the app as described in [SETUP.md](SETUP.md).

1. Open `http://127.0.0.1:8767/`. Explain the goal: help a reviewer find documentation and prepare a response without automatically sending anything.
2. Enter `Can I put my secret key in frontend environment variables?`, keep **Keyword baseline (free)**, and select **Search and save**.
3. Show the source cards, their line numbers and official links. Explain why the user-token qualification matters when describing secret-key RLS behavior.
4. Select **Preview model input (free)**. Show that the question, evidence IDs, and context are prepared without sending a model request.
5. In **Reply text**, enter an explicitly manual draft, select **Save as draft**, and save. Reopen the ticket and show that the edit remains. The original run remains separate from human edits.
6. Open `http://127.0.0.1:8767/demo`. Show the current release's real English response and its sources. The page also labels a translated historical response and a separate historical English response. Explain the successful and failed attempts recorded in [EVALUATION.md](EVALUATION.md).

The local demo is not a deployed customer support system. The recorded 13/19 development retrieval diagnostic is a narrow reference-hit measure, not answer accuracy or a production success rate. Explain the human-review and source-coverage limits.
