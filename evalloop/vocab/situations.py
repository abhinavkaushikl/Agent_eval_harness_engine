"""The ``Situation`` vocabulary: the conditions that select a technique.

A situation is a *branch condition*. The corpus states one twice: loosely, in
the ``Situation`` column of the master lookup, and precisely, in each section's
decision flow ("Is the system stochastic (temp > 0, agents, retrieval)?"). Where
the two differ, the decision flow is the better statement of what selects the
technique, and this module names members from it.

The starting set was the 48 members ``CLAUDE.md`` section 6 listed before this
stage; section 6 now lists the 57 below. Section 6 asks for that list to be
verified against the corpus and extended only where a member is genuinely
missing, with every addition justified here. Verification covered all 73
``Situation`` cells of the master lookup, the ten "You are here when..." section
openings, the ten decision flows, and the index's "Read it when" column.

Conventions, all asserted in ``tests/test_vocab.py``:

* ``StrEnum`` is ``evalloop._compat.StrEnum``, not ``enum.StrEnum`` (the stdlib
  class is 3.11+ and the floor is 3.10 -- decision EL-012).
* Member value == lowercase member name.
* Families appear in ``CLAUDE.md`` section 6 order and members are alphabetical
  within a family, so a reviewer can find a member without reading the file.

Ruling: ``items_grouped`` vs ``grouped_items``
---------------------------------------------
``CLAUDE.md`` section 6 carried both -- the same two words reversed, in two
families. The corpus has **one** situation here: master lookup section B, row
"Items come in groups" (cluster bootstrap), restated in the section B decision
flow as "Are items grouped (docs, conversations, customers)?". One source
condition gets one member, so ``items_grouped`` is dropped and ``grouped_items``
is kept, in the DATA family, because grouping is a property of the data rather
than of a comparison: section B's flow applies it to "every CI below", not only
to the two-way comparison that prompted it.

Members added beyond ``CLAUDE.md`` section 6
--------------------------------------------
Each line gives the corpus condition that forced the member and the technique
left unreachable without it. Without these, sections C and D in particular load
and pass integrity checks while never matching anything (the audit in
``decisions/EL-003-new-situations.md`` group 1).

* ``high_stakes_decision`` -- master lookup section A, row "High-stakes final
  decision"; section A decision flow, "Is a wrong answer high-stakes (health,
  legal, money, regulator)?". Reaches A6 domain-expert human review. The flow
  makes this a branch *under* open-ended text, so ``prose_generation`` cannot
  carry it without routing every prose item to double expert annotation.
* ``stochastic_system`` -- master lookup section C, row "Stochastic system";
  section C decision flow, "Is the system stochastic (temp > 0, agents,
  retrieval)?". Reaches C3 (k >= 5 runs, mean +- SD).
* ``score_near_0_or_100`` -- master lookup section C, row "Score near 0% or
  100%"; section C decision flow, "Is the score near 0% or 100%, or n < 100?".
  Reaches C4 (Wilson / Clopper-Pearson, rule of three). Named after the row
  because the corpus itself words the condition as the two boundaries.
* ``many_slices_checked`` -- master lookup section C, row "Checking many metrics
  or slices"; section C decision flow, "Did you check many slices / metrics /
  variants?". Reaches C5 (Holm-Bonferroni / Benjamini-Hochberg).
* ``heavy_tailed_metric`` -- master lookup section C, row "You don't trust the
  test's assumptions"; section C decision flow, "Is the metric heavy-tailed
  (latency, ₹, ETA)?". Reaches C6 (permutation test). Named from the flow: the
  row cell states a feeling, the flow states the testable property.
* ``false_alarm_expensive`` -- master lookup section D, row "False alarms are
  expensive"; section D decision flow, "Is a false alarm expensive (blocks,
  suspensions, denials)?". Reaches D2 (precision at a fixed floor).
* ``threshold_not_chosen`` -- master lookup section D, row "You haven't picked a
  threshold yet"; section D decision flow, "Choosing between models, no
  threshold agreed?". Reaches D3 (average precision / PR-AUC). The flow's
  condition is a conjunction, so a record is expected to pair this with a
  comparison member.
* ``error_costs_priceable`` -- master lookup section D, row "Setting the
  threshold"; section D decision flow, "Can you price both errors in ₹?".
  Reaches D4 (cost-based threshold). Named from the flow deliberately:
  ``setting_threshold`` would sit one word from ``threshold_not_chosen`` and
  reintroduce the spelling hazard the ruling above just removed.
* ``measuring_safety`` -- master lookup section D, row "Measuring safety";
  section D decision flow, "Is this a safety / abuse / manipulation risk?".
  Reaches D5 (red-team set + ASR per category). Nothing in section 6's list
  means "this output can harm someone"; ``rare_class`` is not a substitute,
  because D5 exists precisely because random samples contain almost no attacks.
* ``reporting_safety_numbers`` -- master lookup section D, row "Reporting safety
  numbers"; section D decision flow, "Reporting the result?" ->
  upper bound ("≤ X% at 95%") + per-category counts table. Reaches D6.

Source conditions deliberately *not* given a member
---------------------------------------------------
* "Any score, ever" (master lookup section C) -- C1 applies universally. Listing
  all members in its ``triggers_on_situation`` would be meaningless and unstable,
  and the field is specified non-empty, so a universal record has no honest
  encoding today. This is a schema question, raised rather than worked around
  (``CLAUDE.md`` section 7.5); a sentinel member would be a planner behaviour
  smuggled into the vocabulary.
* "Balancing quality and money" (master lookup section J) -- proposed as an
  addition by the EL-003 audit, but section J's decision flow puts J3 in an
  unconditional "Final call" branch rather than behind a condition, so
  ``model_selection`` already routes it and the remaining discrimination (₹ per
  1,000 tasks is known) is a precondition, not a branch.
* The 17 rows in the EL-003 audit's group 2 -- each is routed by an existing
  member, with the finer distinction left to ``required_signals``, which
  ``CLAUDE.md`` section 6 defines as "free-text preconditions on artifact/data".
  Section G's eight rows all trigger on ``rag_answer``; section H's on
  ``agent_action``. That reading is what keeps the vocabulary coarse enough to
  stay spellable.
"""

from __future__ import annotations

from evalloop._compat import StrEnum

__all__ = ["Situation"]


class Situation(StrEnum):
    """A condition under which some technique is the right one to use."""

    # --- artifact: what is being produced and graded -----------------------
    agent_action = "agent_action"
    api_endpoint = "api_endpoint"
    classification = "classification"
    code_generation = "code_generation"
    data_pipeline = "data_pipeline"
    model_training = "model_training"
    prose_generation = "prose_generation"
    qa_answer = "qa_answer"
    rag_answer = "rag_answer"
    sql_generation = "sql_generation"
    structured_extraction = "structured_extraction"
    summarization = "summarization"

    # --- measurement: something about a number that has already moved -----
    all_candidates_high = "all_candidates_high"
    all_candidates_zero = "all_candidates_zero"
    benchmark_too_good = "benchmark_too_good"
    length_increased = "length_increased"
    many_slices_checked = "many_slices_checked"
    no_change_score_moved = "no_change_score_moved"
    score_jumped = "score_jumped"
    score_near_0_or_100 = "score_near_0_or_100"
    score_up_business_flat = "score_up_business_flat"
    single_benchmark_dominance = "single_benchmark_dominance"

    # --- comparison: how many things are being weighed against each other -
    external_leaderboard = "external_leaderboard"
    many_candidates = "many_candidates"
    metric_without_formula = "metric_without_formula"
    two_candidates = "two_candidates"

    # --- grader_trust: whether the instrument can be believed -------------
    annotators_disagree = "annotators_disagree"
    measuring_agreement = "measuring_agreement"
    multiple_annotators = "multiple_annotators"
    new_judge_built = "new_judge_built"
    position_bias_risk = "position_bias_risk"
    scale_compressed = "scale_compressed"
    self_preference_risk = "self_preference_risk"

    # --- data: a property of the items or their distribution --------------
    contamination_risk = "contamination_risk"
    distribution_mismatch = "distribution_mismatch"
    false_alarm_expensive = "false_alarm_expensive"
    grouped_items = "grouped_items"
    heavy_tailed_metric = "heavy_tailed_metric"
    phi_present = "phi_present"
    rare_class = "rare_class"
    small_sample = "small_sample"
    stochastic_system = "stochastic_system"

    # --- lifecycle: where in the work this is happening -------------------
    ab_testing = "ab_testing"
    building_eval_set = "building_eval_set"
    ci_flaking = "ci_flaking"
    debugging_regression = "debugging_regression"
    detecting_drift = "detecting_drift"
    error_costs_priceable = "error_costs_priceable"
    high_stakes_decision = "high_stakes_decision"
    measuring_impact = "measuring_impact"
    measuring_safety = "measuring_safety"
    model_selection = "model_selection"
    pre_development = "pre_development"
    reporting_safety_numbers = "reporting_safety_numbers"
    scoring_live_traffic = "scoring_live_traffic"
    shipping_change = "shipping_change"
    threshold_not_chosen = "threshold_not_chosen"
