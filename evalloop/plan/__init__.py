"""Planning: readiness, capability, and the conflict/companion rules.

``AGENT.md`` section 3.5 fixes a seven-step resolution order. Steps 1 and 7 --
selection and ordering -- live in ``evalloop/registry/query.py``, because they
read nothing but the records. The middle steps live here, each in its own
module and each a pure function:

==== ============================================= =========================
step what                                          where
==== ============================================= =========================
3    capability check -> ``unavailable``            ``capability.py``
4    readiness check -> ``pending``                 ``readiness.py``
5    ``conflicts_with`` -> a replaced record drops  ``rules.apply_conflicts``
6    ``companion_checks`` -> companions join        ``rules.resolve_companions``
==== ============================================= =========================

Step 2 (the ``constraint`` records) and the assembly of ``Plan`` itself are
EL-123's, in ``planner.py``, which does not exist yet. Nothing here imports
anything from ``evalloop`` outside ``registry`` and ``vocab``, and nothing here
touches a file, a clock or a global: the whole package is arguments in, frozen
result out, so a plan is reproducible from its inputs alone
(``USER_EXPERIENCE.md`` section 4, principle 7).
"""
