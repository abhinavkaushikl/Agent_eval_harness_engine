# SECTION G – RAG SYSTEMS
### Two components, two failure modes, one score that can't tell them apart

You are here when a retrieval-augmented system gives wrong, invented or badly cited answers, and the only number you have is end-to-end accuracy. That number mixes two different machines. The retriever might not have found the right passage, or the generator might have found it and misread it, ignored it, or added things it didn't say. The fixes for the two are completely different: a better embedding model, chunking or reranker on one side, a better prompt or model on the other. Teams without component-level evals routinely spend a month tuning the one that wasn't broken.

> **Evaluate retrieval and generation separately, because an end-to-end score can't tell you which stage to fix.**

```
  THE RAG EVAL PIPELINE
  ───────────────────────────────────────────────────────────────────────────────
  Query ─► RETRIEVER ─────────────► top-k chunks ─► GENERATOR ─────────► Answer + citations
            │                          │                │                      │
            ├ recall@k       (G1)      ├ context        ├ accuracy with        ├ faithfulness (G3)
            ├ nDCG@10        (G4)      │  precision (G7)│  gold context (G1)   ├ citation P/R (G8)
            └ MRR / Hit@k    (G5)      └ distractor     └ oracle test (G2)     └ abstention on
                                          robustness (G7)                         unanswerables (G6)
  ───────────────────────────────────────────────────────────────────────────────
```

**Rule of thumb:** *end-to-end accuracy ≈ retrieval recall@k × generator accuracy given gold context.* With recall@5 of 0.70 and generator-with-gold of 0.88, you get about 62% end to end. Whichever factor is lower is the one to fix first.

---

# G1 – COMPONENT-WISE EVAL: RETRIEVAL RECALL@k + GENERATION WITH GOLD CONTEXT

## What it is
You score the retriever on its own (did the gold passage appear in the top k?) and the generator on its own (given the gold passage, is the answer correct?). Each item needs a gold passage label as well as a gold answer.

## Why it matters
**End-to-end accuracy can't tell you whether to fix the retriever or the prompt, so teams tune the wrong stage.** An end-to-end score of 62% could mean a perfect retriever with a weak generator, or the reverse. The two component numbers settle it in an afternoon.

## How to do it properly
1. **Label gold passages** for 200–300 questions. One annotator-hour covers roughly 40 questions.
2. **Compute recall@k at the k you actually pass to the generator.** Recall@20 is irrelevant if the prompt only receives 5 chunks.
3. **Run the generator on gold context** (the gold passages plus the usual number of filler chunks) and score its accuracy.
4. **Compare the two numbers.** The lower one is where to spend the next sprint.
5. **Re-run both after every change** to the index, chunking, embedding model or prompt.

## Real scenarios

**Insurance – policy-wording bot**
- **Input:** "Is cataract surgery covered in the first year?"
- **Output:** "Yes, cataract surgery is covered under in-patient hospitalisation." In fact it has a 2-year waiting period.
- **Verdict:** End to end, the bot scored 62% on 300 questions. Recall@5 was **70%**, and with gold context the generator was right **88%** of the time. The waiting-periods table sat in an annexure chunked as one 3,000-token block, which never ranked in the top 5. The team had been rewriting prompts for three weeks. Re-chunking the tables raised recall@5 to 89% and end-to-end accuracy to 78%, with no prompt change at all.

**Banking – internal ops assistant over SOPs**
- **Input:** 250 questions from branch staff.
- **Output:** 71% end to end. A vector-database migration was proposed.
- **Verdict:** Recall@5 was **94%**, and with gold context the generator scored only **75%**. Retrieval was fine. The generator was mixing up steps from similar SOPs, for example the NEFT return and RTGS return procedures. A prompt that required quoting the SOP's step numbers raised generation-with-gold to 90%. The vector-DB migration, 6 weeks of work, was cancelled.

## The mistake people make
Iterating on the RAG system while tracking only the end-to-end score.

## The line to use in a meeting
*"Retrieval finds the right document 70% of the time. When it does, the model answers correctly 88% of the time. So the fix is retrieval, not the prompt."*

---

# G2 – ORACLE-CONTEXT TEST + PER-FAILURE STAGE ATTRIBUTION

## What it is
You replace retrieval with the gold passages (the oracle context) to find the generator's ceiling. Then you tag each end-to-end failure with its stage: **not retrieved**, **retrieved but ranked beyond k**, or **retrieved but misread**.

## Why it matters
**Without attribution, every fix is a guess.** G1 gives you two averages. Attribution tells you what share of the actual failures each stage causes, and that ranks your backlog by impact.

## How to do it properly
1. **Collect 100–200 end-to-end failures.**
2. **For each, check whether the gold passage is in the top k.** If not, check whether it's in the top 50 (ranked beyond k) or absent (not retrieved).
3. **If it was in the top k, the generator misread it.** Sub-tag why: ignored it, contradicted it, or combined it wrongly with another chunk.
4. **Count the stages.** The largest bucket is the first fix: embeddings or chunking for "not retrieved", a reranker for "ranked beyond k", the prompt or model for "misread".

## Real scenarios

**Legal – contract-QA over 5,000 master service agreements**
- **Input:** 200 end-to-end failures.
- **Output:** The team was planning to fine-tune the generator.
- **Verdict:** **58% not retrieved, 17% retrieved but ranked beyond 5, 25% misread.** Most "not retrieved" failures involved defined terms: "Confidential Information" was defined in clause 1.1, and the question used "trade secrets". Adding the definitions section to every chunk's context and query-side synonym expansion recovered 61% of that bucket. The fine-tune was deferred, since it could have fixed at most the 25% bucket.

**Healthcare – hospital-policy assistant**
- **Input:** 120 failures.
- **Output:** "The model hallucinates" was the diagnosis on the team's slides.
- **Verdict:** Attribution showed that only **14% were misreads**. **52% were "ranked beyond 5"**: the right policy was retrieved at rank 6–12 behind older, superseded versions of the same policy. Adding a recency and version filter moved most of them into the top 3. The problem was stale documents in the index, not model hallucination.

## The mistake people make
Diagnosing "hallucination" without checking whether the right passage ever reached the model.

---

# G3 – FAITHFULNESS: CLAIM DECOMPOSITION + NLI ENTAILMENT

## What it is
You split each answer into atomic claims, then check whether the retrieved context **entails** each claim, using an NLI model or a validated LLM judge. Faithfulness = entailed claims / total claims. You also track the share of answers with at least one unsupported claim.

## Why it matters
**Checking correctness against a reference answer misses unsupported extras added to an otherwise correct answer.** "The copay is 20%" matches the reference, and so does "The copay is 20%, and it's waived for senior citizens", except the waiver is invented. In regulated domains that extra sentence is the liability.

## How to do it properly
1. **Decompose with a prompt that outputs one fact per line.** Validate the decomposition on 50 answers first.
2. **Check each claim against the retrieved context only,** not the model's world knowledge.
3. **Report both** mean faithfulness and **% of answers with ≥1 unsupported claim.** The second is what users actually experience.
4. **Validate the entailment judge** against 150+ human claim labels (Section F), with extra attention to numbers and negations.

## Real scenarios

**Healthcare – hospital SOP bot for nursing staff**
- **Input:** "What's the protocol for a potassium level of 6.2?"
- **Output:** Six claims, five matching the SOP, plus "administer 10 units IV insulin with 25 g dextrose."
- **Verdict:** The answer scored "correct" against the reference answer, because the SOP steps were there. Faithfulness was 5/6 = **0.83**, and the unsupported claim was a **dosage the SOP never states**, since dosing is left to the physician's order. Across 500 answers, **14% contained at least one unsupported claim**, and 40% of those were dosages or thresholds. Launch required that figure to be below 2%. A "quote only from context" constraint and a dosage-specific check brought it to 1.6%.

**Fintech – mutual-fund FAQ bot**
- **Input:** "What's the exit load on this fund?"
- **Output:** "1% if redeemed within 1 year. There's no exit load on SIP instalments after 6 months."
- **Verdict:** The first claim was entailed by the scheme information document. The second wasn't, and it was also false. Reference-based grading had marked the answer correct. The claim-level check found invented exceptions in **9% of answers**, almost always as a second sentence tacked on after a correct first one.

## The mistake people make
Measuring correctness only against a reference answer and assuming that means the answer is faithful to the sources.

## The line to use in a meeting
*"The answer was right, and it also added a dosage that isn't in the SOP. That extra sentence is our liability, so we measure every claim."*

---

# G4 – nDCG@10 WITH GRADED RELEVANCE

## What it is
Normalised Discounted Cumulative Gain. Each result has a graded relevance (for example 0–3), gains are discounted by log₂(rank + 1), and the total is normalised against the ideal ordering. It measures whether the *best* results are at the *top*.

## Why it matters
**Recall@k ignores order, but users only read the top 3.** A reranker that moves the perfect product from rank 8 to rank 1 leaves recall@10 unchanged and changes the business outcome completely. nDCG is the metric that registers the move.

## How to do it properly
1. **Define a relevance scale** with examples, such as 3 = exact match to the need, 2 = acceptable substitute, 1 = related, 0 = irrelevant.
2. **Label the top 10–20 results per query** for 200–500 queries. Pool results from all systems you're comparing so that unlabelled results don't bias the comparison.
3. **Report nDCG@10 with a paired bootstrap CI** (Section B) between systems.
4. **Check that nDCG predicts clicks or conversions** on logged traffic before optimising for it.

## Real scenarios

**E-commerce – product search for "cotton kurta for office under ₹1,500"**
- **Input:** 400 queries, baseline vs a new cross-encoder reranker.
- **Output:** Recall@10 was flat at **0.83** for both.
- **Verdict:** nDCG@10 rose from **0.61 to 0.72**. The reranker moved exact matches (cotton, office wear, under ₹1,500) from ranks 5–9 into the top 3, ahead of silk party kurtas that matched on "kurta" alone. In the A/B test, add-to-cart from search rose **7.4%**. Had the team gone by recall, it would have rejected the reranker as "no improvement".

**Legal – case-law search for advocates**
- **Input:** 150 research queries.
- **Output:** A new embedding model raised recall@20 from 0.71 to 0.79.
- **Verdict:** nDCG@10 *fell* from 0.58 to 0.54. The new model retrieved more relevant judgments overall but ranked lower-court orders above Supreme Court precedents on the same point. Advocates want the binding precedent first. The team kept the new embeddings for recall and added a court-hierarchy boost to the ranking.

## The mistake people make
Evaluating a search or reranking change with recall@k, which can't see order.

---

# G5 – MRR AND HIT@k WHEN ONE RIGHT DOCUMENT EXISTS

## What it is
When each query has exactly one correct document, **MRR** (mean reciprocal rank) = the average of 1/rank of that document. **Hit@k** = the share of queries where it appears in the top k.

## Why it matters
With a single relevant document, what matters is **how far down it sits**. nDCG's graded machinery adds nothing, and MRR reads directly: an MRR of 0.5 means the right document is typically at rank 2.

## How to do it properly
1. **Confirm that one right document is actually the situation.** If there are several valid documents, use nDCG.
2. **Report Hit@1, Hit@3 and MRR together.** Hit@3 matches what the generator or the user will see.
3. **Break results down by query type,** because MRR averages hide query classes that systematically fail.

## Real scenarios

**Banking – finding the RBI master circular that governs a compliance query**
- **Input:** 300 compliance-team questions, each with one governing master circular.
- **Output:** **MRR 0.74, Hit@3 0.89.**
- **Verdict:** The overall numbers were good enough to launch. The per-type breakdown showed that for questions about **amended** circulars, Hit@3 was only **0.52**. The superseded version ranked above the current one because it had more text on the topic. A "superseded" metadata filter raised that slice to 0.91. That slice was the one the auditors would ask about.

**Telecom – finding the one tariff order for a customer's plan**
- **Input:** 500 agent queries such as "What's the FUP on plan ₹719 from March?"
- **Output:** Hit@1 was 0.48, which looked bad.
- **Verdict:** MRR was **0.81** and Hit@3 **0.97**. The right order was almost always at rank 2, behind a near-identical order for the same plan with a different validity period. Passing the top 3 to the generator along with the date constraint fixed it. The retriever didn't need replacing.

## The mistake people make
Using nDCG or recall when there's only one right document and the only question is its rank.

---

# G6 – UNANSWERABLE-QUESTION SET: FALSE-ANSWER RATE + ABSTENTION PRECISION

## What it is
You mix questions whose answer is **not** in the corpus into the eval set, typically 15–25% of it. You score the **false-answer rate** (confident answers to unanswerable questions) and the **abstention precision** (of all the times the system declined, how often the question really was unanswerable).

## Why it exists
**Standard eval sets are 100% answerable, so hallucination on unknowns is never measured.** In production, a large share of questions fall outside the corpus. A system that always produces some answer will invent one, and in a RAG product it will look sourced, which makes users trust it more.

## How to do it properly
1. **Write the unanswerable questions from real out-of-corpus traffic**, plus near-miss questions ("maternity leave for contract staff" when the policy only covers permanent staff).
2. **Report the false-answer rate** on unanswerables *and* the **over-abstention rate** on answerables. Refusing everything scores 0% on the first and fails on the second.
3. **Set a bar for each,** for example false answers ≤ 5% and over-abstention ≤ 8%.
4. **Include partially answerable questions.** These are where invented details tend to get added.

## Real scenarios

**HR – employee policy bot**
- **Input:** 100 unanswerable questions mixed into 400.
- **Output:** "Contract staff are entitled to 26 weeks of maternity leave as per company policy."
- **Verdict:** The policy doesn't cover contractors, and the bot had filled the gap from the Maternity Benefit Act, then attributed it to *company policy*. It answered **37 of 100** unanswerables confidently, a **37% false-answer rate**, while scoring 91% on the answerable questions. An explicit "not covered in our policy documents" instruction plus an entailment check (G3) brought it to 6%, with over-abstention rising from 2% to 5%.

**E-commerce – seller-support bot**
- **Input:** 80 unanswerable questions, such as fee changes announced after the corpus snapshot.
- **Output:** False-answer rate 4%, which looked excellent.
- **Verdict:** The team then checked over-abstention: the bot refused **22%** of *answerable* questions. It had been tuned to refuse whenever it was unsure. Sellers who get "please contact support" on an easy question open tickets anyway. Both rates became gating metrics, and the tuned balance was 7% false answers and 6% over-abstention.

## The mistake people make
Evaluating only on questions the corpus can answer.

## The line to use in a meeting
*"The bot scores 91% on questions it can answer, and it invents answers to 37% of the questions it can't. Users can't tell the two apart."*

---

# G7 – CONTEXT PRECISION + DISTRACTOR-INJECTION ROBUSTNESS

## What it is
**Context precision** is the share of retrieved chunks that are actually relevant. **Distractor injection** means deliberately inserting plausible but irrelevant chunks (old versions, adjacent topics) into the context and re-measuring accuracy.

## Why it matters
**The generator reads and uses irrelevant chunks, so junk retrieval becomes wrong answers.** High recall is only half of good retrieval. If the right chunk arrives alongside four misleading ones, the generator may combine them or pick the wrong one.

## How to do it properly
1. **Label the relevance of each retrieved chunk** for 150–200 queries, and compute precision@k.
2. **Build distractors** from real near-misses: superseded documents, a sibling product's page, the same clause from a different contract.
3. **Inject 1–3 distractors** into gold context and measure the accuracy drop. **A drop of more than 5 points means the generator can't handle noise.**
4. **Fix both sides:** filter or rerank retrieval, and have the generator cite which chunk it used.

## Real scenarios

**Telecom – tariff bot**
- **Input:** "What's the data benefit on the ₹349 plan?"
- **Output:** "2.5 GB a day." That was the 2023 benefit. The current plan gives 2 GB a day.
- **Verdict:** Precision@5 was **0.46**. Discontinued 2023 plan documents were being retrieved alongside current ones. Injecting two old-plan distractors into gold context dropped accuracy from **84% to 71%**. Removing discontinued plans from the index and adding an "effective from" date to each chunk raised accuracy to 88%.

**Insurance – multi-policy customer assistant**
- **Input:** A customer with a health policy and a top-up policy asks about room-rent limits.
- **Output:** The answer gave the top-up's limit for the base policy.
- **Verdict:** Both policy wordings were retrieved and both were relevant, but the generator mixed them up. Distractor tests using sibling-policy chunks showed a **17-point drop**. Adding a policy-ID tag to each chunk and requiring the answer to name its source policy cut the drop to 4 points.

## The mistake people make
Measuring only whether the right chunk was retrieved, not what else came with it.

---

# G8 – CITATION PRECISION AND CITATION RECALL

## What it is
**Citation precision:** does each cited passage actually support the sentence it's attached to? **Citation recall:** is every claim that needs a citation given one?

## Why it matters
**Citations that look plausible but don't support the claim destroy trust and create liability.** Users, and especially professionals, check citations only occasionally. When one fails the check, they stop trusting every answer. In legal and medical products, a wrong citation is worse than none.

## How to do it properly
1. **For each (sentence, citation) pair, judge whether the passage entails the sentence,** using the same NLI or judge setup as G3.
2. **For each sentence that makes a claim, check whether it has a citation.**
3. **Report both,** plus the share of answers with at least one bad citation.
4. **Check that citation IDs resolve** (the document exists and the page or paragraph exists) with deterministic code before any judging.

## Real scenarios

**Legal – research assistant citing Supreme Court and High Court judgments**
- **Input:** 300 answers with 1,100 citations.
- **Output:** Every citation linked to a real judgment, so the ID-resolution check passed at 100%.
- **Verdict:** Citation precision was **81%**, so **1 in 5 cited judgments didn't support the sentence** it was attached to. Most were real judgments on the same statute but a different point, for example a Section 138 case cited for a limitation proposition it never discussed. For advocates filing in court, one such citation is a professional embarrassment. The team added per-citation entailment verification and suppressed citations below threshold, taking precision to 96% while citation recall fell from 88% to 79%. The advocates preferred that trade.

**Healthcare – clinical-guideline Q&A for GPs**
- **Input:** 200 answers.
- **Output:** Citation precision 94%.
- **Verdict:** Citation *recall* was only **63%**. Dosage and contraindication claims, the ones a GP most needs to verify, were the least likely to carry a citation, because the model cited general statements and left specific ones uncited. Requiring a citation on every sentence containing a number raised recall to 91%.

## The mistake people make
Checking that citations exist and link to real documents, without checking that they support the claim they're attached to.

## The line to use in a meeting
*"Every citation points to a real judgment, but 1 in 5 doesn't support the sentence it's attached to. For an advocate, that's worse than no citation."*

---

# SECTION G DECISION FLOW

```
START: RAG answers are wrong, invented, or badly cited.
│
├─ Do you have gold passage labels?
│     └─ NO → label 200–300 questions first. Nothing below works without them.
│
├─ Split the score (G1):  recall@k   vs   accuracy with gold context
│     ├─ recall@k is lower → RETRIEVAL problem
│     │     ├─ attribute failures (G2): not retrieved vs ranked beyond k
│     │     ├─ ranked beyond k → reranker; measure nDCG@10 (G4) or MRR/Hit@k if one right doc (G5)
│     │     └─ not retrieved → chunking, synonyms, metadata filters
│     └─ generator-with-gold is lower → GENERATION problem
│           ├─ extra unsupported claims → faithfulness, claim-level (G3)
│           └─ confused by junk → context precision + distractor test (G7)
│
├─ Does the system answer things the corpus doesn't cover?
│     └─ add 15–25% unanswerables; false-answer rate AND over-abstention (G6)
│
└─ Are citations shown to users?
      └─ ID resolution (code) → citation precision + recall (G8)
```

---

# THE THREE THINGS TO REMEMBER

1. **Split the score before you fix anything.** End-to-end ≈ recall@k × accuracy-with-gold, and the lower factor is where the sprint goes.

2. **Correct and faithful are different metrics.** Check every claim against the retrieved context, and measure what the system does on questions it can't answer.

3. **A citation that exists isn't necessarily one that supports the claim.** Measure citation precision per sentence, because one bad citation costs the user's trust in all the others.
