# Predicate-polarity lexicon — suggestions for the unsigned / review entries

> **Status:** research proposal (Issue #30). This document does **not** edit
> `scripts/quality/predicate_polarity.yaml`; it recommends changes for a maintainer to apply.
> **Goal:** reduce `indeterminate` net-polarity results by resolving every `confidence: review`
> entry (and every entry that the checker currently treats as `opaque` or `reverse`) with a
> suggestion grounded in the Biolink model definition text.

---

## How the polarity check uses these entries (recap)

`predicate_polarity.yaml` assigns each predicate a **`sign`** — the effect of the edge's *subject*
on its *object*, read along the edge direction (`source → target`):

- `+1` subject increases / activates / brings about the object
- `-1` subject decreases / inhibits / removes the object
- `0`  no inherent direction of influence

Net polarity of a drug→disease path = product of the signs of the **directional** edges (`0` edges
skipped). A correct therapeutic mechanism must net to `-1`. An edge becomes **indeterminate** (path
routed to needs-review, not silently composed) in two cases, per the lexicon's own orientation notes
(lines 116-121):

- **opaque** — `sign: 0` but `role` is `regulatory` / `correlation` / `clinical_outcome`
  (directional relationship, unknown direction); and
- **reverse** — `role: reverse` (the causal arrow points `target → source`, opposite the edge),
  which cannot be composed into a forward-walking product.

So "reduce indeterminate" means, per predicate, one of:
- **(A) Confirm/assign a definite sign** and drop `review` → the edge composes cleanly.
- **(B) Reassign the sign/role** when the Biolink definition says the relationship is really
  neutral scaffolding.
- **(C) Reclassify a `reverse` entry to `correlation`** when the relationship is symmetric in
  polarity terms (co-variation), so it composes without an unsound causal claim.
- **(D) Keep opaque** (genuinely direction-unspecified) — the resolution is *data-level*:
  re-curate to the already-signed sibling predicate.
- **(E) Keep as reverse / flag for re-orientation** — the relationship is a genuinely reversed
  causal/derivation arrow; signing it in place would be unsound, so the resolution is a data fix
  (flip the edge to its forward inverse).

### Sources used

The lexicon deliberately retains the legacy predicate vocabulary without conversion, so some
predicates below are current Biolink slots while five were removed in the Biolink 3.x/4.x
qualifier refactor. Definitions are quoted from:

- **Biolink 4.4.3** (current) — `https://raw.githubusercontent.com/biolink/biolink-model/v4.4.3/biolink-model.yaml`
  and the per-slot docs pages `https://biolink.github.io/biolink-model/<slot>/`.
- **Biolink 2.4.8** (for predicates removed from 4.x) —
  `https://raw.githubusercontent.com/biolink/biolink-model/v2.4.8/biolink-model.yaml`.

All quotes are the verbatim `description:` text of the slot in the cited file.

---

## Summary table (all 22 review predicates)

| # | Predicate | Current lexicon | Action | Suggested result |
|---|-----------|-----------------|--------|------------------|
| 1 | `increases transport of` | +1 regulatory, review | **A** confirm | +1 regulatory, high |
| 2 | `increases response to` | +1 regulatory, review | **A** confirm (caveat) | +1 regulatory, high |
| 3 | `decreases response to` | −1 regulatory, review | **A** confirm (caveat) | −1 regulatory, high |
| 4 | `has output` | +1 causal, review | **A** confirm | +1 causal, high |
| 5 | `predisposes` | +1 clinical_outcome, review | **A** confirm | +1 clinical_outcome, high |
| 6 | `has metabolite` | +1 derivation, review | **A** confirm | +1 derivation, high |
| 7 | `derives into` | +1 derivation, review | **A** confirm | +1 derivation, high |
| 8 | `has phenotype` | +1 correlation, review | **A** confirm | +1 correlation, high |
| 9 | `manifestation of` | +1 correlation, review | **A** confirm | +1 correlation, high |
| 10 | `phenotype of` | +1 **reverse**, review | **C** reclassify | +1 **correlation**, high |
| 11 | `expresses` | +1 regulatory, review | **B** reassign | **0 contextual**, high |
| 12 | `enables` | +1 causal, review | **B** reassign | **0 contextual**, high |
| 13 | `contraindicated for` | 0 clinical_outcome, review | **B** confirm-0 | 0 clinical_outcome, high (flag) |
| 14 | `regulates` | 0 regulatory, review (opaque) | **D** keep opaque | 0, tighten → pos/neg regulates |
| 15 | `correlated with` | 0 correlation, review (opaque) | **D** keep opaque | 0, tighten → pos/neg correlated with |
| 16 | `affects risk for` | 0 clinical_outcome, review (opaque) | **D** keep opaque | 0, tighten → predisposes / prevents |
| 17 | `affected by` | 0 reverse, review | **D/E** keep opaque | 0, tighten → signed inverse |
| 18 | `caused by` | +1 reverse, review | **E** keep reverse | reverse, flag re-orient → `causes` |
| 19 | `disrupted by` | −1 reverse, review | **E** keep reverse | reverse, flag re-orient → `disrupts` |
| 20 | `is metabolite of` | +1 reverse, review | **E** keep reverse | reverse, flag re-orient → `has metabolite` |
| 21 | `produced by` | +1 reverse, review | **E** keep reverse | reverse, flag re-orient → `produces` |
| 22 | `derives from` | +1 reverse, review | **E** keep reverse | reverse, flag re-orient → `derives into` |

(Count: 22 distinct `confidence: review` predicates — including `contraindicated for`, a `sign: 0`
review entry. All are detailed in the sections that follow.)

---

## Group A — Confirm the sign, drop `review` (composes cleanly)

These have a definite Biolink-grounded direction. Removing the `review` flag lets them participate
in the net-polarity product instead of forcing the human to confirm every path that uses them.

### 1. `increases transport of` — current: `{sign: +1, role: regulatory, confidence: review}`

> "holds between two chemical or gene/gene product entities where the action or effect of one
> **increases the rate of transport** of the other across some boundary in a system of interest"
> — Biolink 2.4.8 (`increases transport of`, removed in 4.x).
> Source: `https://raw.githubusercontent.com/biolink/biolink-model/v2.4.8/biolink-model.yaml`

Decisively, Biolink files this predicate under the grouping mixin **`increases amount or activity
of`** ("*a grouping mixin to help with searching for all the predicates that increase the amount or
activity of the object*", same file). Biolink itself classifies increased transport as **increasing
the object** → **+1 confirmed**.

**Suggestion: (A) keep `+1`, change `confidence: review` → `high`.** Consistent with the lexicon's
existing high-confidence `decreases uptake of = −1`, which is the mirror-image transport predicate
under the `decreases amount or activity of` mixin. *Caveat to note in the row comment:* transport can
also mean efflux (moving the object out of a compartment), which would lower its local level; Biolink's
canonical classification nonetheless treats "increases transport of" as `+1`, so adopt `+1` and let a
context-specific efflux case be caught by edge-level review, not the default sign.

### 2. `increases response to` — current: `{sign: +1, role: regulatory, confidence: review}`
### 3. `decreases response to` — current: `{sign: -1, role: regulatory, confidence: review}`

> `increases response to`: "holds between two chemical entities where the action or effect of one
> **increases the susceptibility** of a biological entity or system … to the other"
> `decreases response to`: "… **decreases the susceptibility** … to the other"
> — Biolink 2.4.8 (both removed in 4.x; superseded by `associated with response to` + direction/aspect
> qualifiers). Source: `https://raw.githubusercontent.com/biolink/biolink-model/v2.4.8/biolink-model.yaml`

Biolink files `increases response to` under **`increases amount or activity of`** and
`decreases response to` under **`decreases amount or activity of`**, so the signs `+1` / `−1` match
Biolink's own classification.

**Suggestion: (A) keep `+1` / `−1`, change `confidence: review` → `high`.** *Caveat:* these are
*sensitization/potentiation* relationships (they change how strongly the system responds to the
object, not the object's own abundance). Before upgrading, confirm they actually occur mid-mechanism
in the corpus; if they never appear on a directional backbone, upgrading is low-risk. The current
Biolink form encodes the same +/− split via the `object_direction_qualifier` (increased/decreased)
on `associated with response to`, so the sign is unambiguous.

### 4. `has output` — current: `{sign: +1, role: causal, confidence: review}`

> "holds between a process and a continuant, where the continuant is **an output of the process**"
> — Biolink 4.4.3 (`has output`, `is_a: has participant`, `exact_mappings: RO:0002234`).
> Source: `https://biolink.github.io/biolink-model/has_output/`

The object is *generated by* the process, so the process brings the object into being → **+1**. Note
the lexicon marks the generic parent `has participant` as `0` (neutral); `has output` is the more
specific, directional child and correctly carries `+1`.

**Suggestion: (A) keep `+1`, change `confidence: review` → `high`.**

### 5. `predisposes` — current: `{sign: +1, role: clinical_outcome, confidence: review}`

> "holds between two entities where exposure to one entity **increases the chance** of developing the
> other" — Biolink 2.4.8 (`predisposes`; note `opposite_of: prevents`). In 4.4.3 this is
> `predisposes to condition` (`is_a: affects likelihood of`): "*Holds between two entities where the
> presence or application of one increases the chance that the other will come to be.*"
> Sources: `https://raw.githubusercontent.com/biolink/biolink-model/v2.4.8/biolink-model.yaml`;
> `https://biolink.github.io/biolink-model/predisposes_to_condition/`

"Increases the chance of the disease" → **+1**, and Biolink names it the explicit `opposite_of` of
`prevents` (which the lexicon signs `−1`, high). The sign is well-grounded.

**Suggestion: (A) keep `+1`, change `confidence: review` → `high`.** Like `treats`/`prevents`, it is a
drug↔disease `clinical_outcome` edge and should still trip the shortcut-edge flag when it appears
mid-mechanism — that is a topology concern, separate from its (now settled) sign.

### 6. `has metabolite` — current: `{sign: +1, role: derivation, confidence: review}`
### 7. `derives into` — current: `{sign: +1, role: derivation, confidence: review}`

> `has metabolite`: "holds between two molecular entities in which the second one is **derived from
> the first one as a product of metabolism**" — Biolink 4.4.3 (`is_a: derives into`).
> `derives into`: "holds between two distinct material entities, the old entity and the new entity, in
> which the **new entity begins to exist** when the old entity ceases to exist …" — Biolink 4.4.3.
> Sources: `https://biolink.github.io/biolink-model/has_metabolite/`,
> `https://biolink.github.io/biolink-model/derives_into/`

These are *forward-oriented* along the edge (`source = parent/old`, `target = metabolite/new`). The
object (the new entity / metabolite) **comes to exist**, i.e. its amount rises from zero → **+1**.

**Suggestion: (A) keep `+1`, change `confidence: review` → `high`.** These are the forward derivation
predicates; their reversed inverses (`is metabolite of`, `derives from`) are handled in Group E.

### 8. `has phenotype` — current: `{sign: +1, role: correlation, confidence: review}`
### 9. `manifestation of` — current: `{sign: +1, role: correlation, confidence: review}`

> `has phenotype`: "holds between a biological entity and a phenotype … construed broadly as any kind
> of quality of an organism part …" — Biolink 4.4.3 (`exact_mappings: RO:0002200`).
> `manifestation of`: "that part of a phenomenon which is directly observable or visibly expressed, or
> which **gives evidence to the underlying process**; used … for linking things like dysfunctions and
> processes to some disease or syndrome" — Biolink 4.4.3 (`range: disease`).
> Sources: `https://biolink.github.io/biolink-model/has_phenotype/`,
> `https://biolink.github.io/biolink-model/manifestation_of/`

Both express **positive co-variation** between a phenotype/manifestation and the entity/disease it
characterizes: more disease ⇒ more phenotype. For net-polarity composition that is exactly a positive
correlation edge — decreasing the upstream node decreases the disease read-out. `manifestation of` is
*causally* disease→phenotype (a read-out relationship), but because correlation is **symmetric in
sign**, orienting it as `+1` correlation composes correctly regardless of arrow direction.

**Suggestion: (A) keep `+1 correlation`, change `confidence: review` → `high`.** Keep the `correlation`
role (weaker than causal) so the topology checker still treats them as soft evidence rather than a
hard mechanistic step.

---

## Group C — Reclassify a `reverse` entry to `correlation` (reduces indeterminate)

### 10. `phenotype of` — current: `{sign: +1, role: reverse, confidence: review}`

> Biolink 4.4.3 defines `phenotype of` only structurally: `domain: phenotypic feature`,
> `range: biological entity`, **`inverse: has phenotype`** (it carries no separate description; it is
> the declared inverse of `has phenotype`).
> Source: `https://biolink.github.io/biolink-model/phenotype_of/`

`phenotype of` is the exact inverse of `has phenotype` (#8) and the mirror of `manifestation of` (#9).
Marking it `role: reverse` forces **indeterminate**, but — unlike the causal reverse predicates in
Group E — a phenotype↔entity link is an **association that is symmetric in polarity terms**. The
phenotype and the entity it characterizes co-vary positively in *either* reading, so composing it as
`+1 correlation` is sound and matches how `manifestation of` (its semantic twin) is already treated.

**Suggestion: (C) change `role: reverse` → `correlation`, keep `+1`, set `confidence: high`.**
Rationale: aligns the phenotype trio (`has phenotype`, `manifestation of`, `phenotype of`) on one
consistent `+1 correlation` treatment grounded in `has phenotype`'s RO:0002200 semantics, and removes
a whole class of paths from the indeterminate bucket without an unsound causal claim.

---

## Group B — Reassign the sign: Biolink says the relationship is neutral scaffolding

### 11. `expresses` — current: `{sign: +1, role: regulatory, confidence: review}`

> "holds between an **anatomical entity and gene or gene product** that is expressed there" —
> Biolink 4.4.3 (`is_a: location of`, `inverse: expressed in`, `exact_mappings: RO:0002292`).
> Source: `https://biolink.github.io/biolink-model/expresses/`

Biolink makes `expresses` a **subtype of `location of`** — it says a tissue *is the place where* a
gene product is present, not that anything *increased* it. The lexicon already signs its parent
`location of` and its inverse `expressed in` as `0 contextual (high)`, so `+1 regulatory` is
inconsistent with Biolink's own placement.

**Suggestion: (B) change to `{sign: 0, role: contextual, confidence: high}`.** It becomes neutral
scaffolding (skipped in the product), matching `location of` / `expressed in`. *Note:* this does not
flip any path's net sign — a skipped edge and a `+1` edge both leave the running product unchanged —
so the change is purely a faithfulness/cleanliness fix, but it removes a `review` flag and stops
`expresses` from being (incorrectly) counted as a directional mechanistic step.

### 12. `enables` — current: `{sign: +1, role: causal, confidence: review}`

> "holds between a **physical entity and a process**, where the physical entity **executes the
> process**" — Biolink 4.4.3 (`is_a: participates in`, `exact_mappings: RO:0002327`).
> Source: `https://biolink.github.io/biolink-model/enables/`

Biolink makes `enables` a **subtype of `participates in`** (the standard GO gene-product→molecular-
function link: the entity *carries out* the activity). It asserts participation, not an increase or
decrease of the process. The lexicon signs the parent `participates in` as `0 contextual (high)`.

**Suggestion: (B) change to `{sign: 0, role: contextual, confidence: high}`** to match its Biolink
parent. As with `expresses`, this is polarity-neutral in effect (a `+1` step and a skipped step give
the same product), so it is safe; it just stops treating a participation edge as a causal step.
*(Alternative, if you prefer to keep it directional: leaving it `+1` never changes a net sign either,
so the choice is about semantic faithfulness, not correctness — Biolink's `is_a: participates in`
favors `0`.)*

### 13. `contraindicated for` — current: `{sign: 0, role: clinical_outcome, confidence: review}`

> Biolink 4.4.3 spells this `contraindicated in`: "Holds between a substance, procedure, or activity
> and a medical condition or circumstance, where an authority has established that the substance …
> **should not be applied** as an intervention in patients with the condition … because it can result
> in **detrimental outcomes**." (`opposite_of: treats`.)
> Source: `https://biolink.github.io/biolink-model/contraindicated_in/`

This is **not a mechanistic step** — it is an administrative/safety assertion that a drug must not be
used in a condition. It carries no direction of biological influence along a mechanism backbone.

**Suggestion: (B) keep `{sign: 0}`, change `confidence: review` → `high`, keep the "flag if present"
note.** The `0` is a settled decision (neutral, skipped), not an unknown direction; it should never
appear mid-mechanism, and its presence should raise a structural flag (like the other
`clinical_outcome` shortcuts), which is already noted.

---

## Group D — Keep opaque (direction genuinely unspecified); resolve by re-curation

For these, Biolink's definition is explicitly non-directional. Signing them would fabricate direction
Biolink does not assert. The correct resolution is a **data-level tightening**: re-curate the edge to
the already-signed sibling predicate (all of which are present in the lexicon). Recommend keeping
`sign: 0` but changing `confidence: review` → `high` with a `note: "opaque; re-curate to <sibling>"`,
so the entry is no longer "unresolved" — it is a *deliberate* opaque marker that routes the path to
review with an actionable instruction.

### 14. `regulates` — current: `{sign: 0, role: regulatory, confidence: review}`  (the flagship case)

> "A **more specific form of affects**, that implies the effect results from a biologically evolved
> control mechanism. … " — Biolink 4.4.3 (`is_a: affects`, `exact_mappings: RO:0002448`).
> Source: `https://biolink.github.io/biolink-model/regulates/`

`regulates` is deliberately **direction-agnostic** in Biolink; direction is expressed either by the
subtypes `positively regulates` / `negatively regulates` (Biolink ≤2.x) or the
`object_direction_qualifier: increased|decreased` on `regulates` (Biolink 4.x). Both directional forms
are **already signed high in the lexicon** (`positively regulates = +1`, `negatively regulates = −1`).

**Suggestion: (D) keep `sign: 0` opaque; set `confidence: high` with
`note: "direction-agnostic per Biolink; re-curate to positively/negatively regulates"`.** This keeps
the check honest (an un-directioned regulation genuinely *is* indeterminate) while making the fix
unambiguous and moving the resolution to where it belongs — the data.

### 15. `correlated with` — current: `{sign: 0, role: correlation, confidence: review}`

> "A relationship that holds between two concepts … for which a **statistical correlation** is
> believed to exist …" — Biolink 4.4.3 (`symmetric: true`, `exact_mappings: RO:0002610`).
> Source: `https://biolink.github.io/biolink-model/correlated_with/`

Biolink marks it **`symmetric: true`** and gives it no sign; its signed siblings
`positively correlated with` (+1) and `negatively correlated with` (−1) already exist and are signed
high in the lexicon.

**Suggestion: (D) keep `sign: 0` opaque; set `confidence: high` with
`note: "symmetric/unsigned per Biolink; re-curate to positively/negatively correlated with"`.**

### 16. `affects risk for` — current: `{sign: 0, role: clinical_outcome, confidence: review}`

> "holds between two entities where **exposure to one entity alters the chance** of developing the
> other" — Biolink 2.4.8 (removed in 4.x; superseded by `affects likelihood of`: "*Holds between two
> entities where the presence or application of one alters the chance that the other will come to
> be.*"). Sources: `https://raw.githubusercontent.com/biolink/biolink-model/v2.4.8/biolink-model.yaml`;
> `https://biolink.github.io/biolink-model/affects_likelihood_of/`

"Alters the chance" is explicitly **directionless**. The directional children exist and are signed:
`predisposes` (+1, #5) raises risk, `prevents` (−1, lexicon high) lowers it (Biolink 4.x:
`associated with increased likelihood of` / `associated with decreased likelihood of`).

**Suggestion: (D) keep `sign: 0` opaque; set `confidence: high` with
`note: "direction unspecified per Biolink; re-curate to predisposes (+1) or prevents (−1)"`.**

### 17. `affected by` — current: `{sign: 0, role: reverse, confidence: review}`

> "describes an entity of which the **state or quality is affected by** another existing entity." —
> Biolink 4.4.3 (`inverse: affects`).
> Source: `https://biolink.github.io/biolink-model/affected_by/`

This is the inverse of the generic `affects`, which is itself directionless ("*has an effect on the
state or quality of another*"). So `affected by` is **both** direction-unspecified **and** reverse-
oriented — doubly indeterminate.

**Suggestion: (D/E) keep `sign: 0` opaque; set `confidence: high` with
`note: "direction + orientation unspecified; re-curate to a signed forward inverse (increases/decreases …)"`.**
Signing it would invent a direction Biolink withholds; the fix is data-level specification.

---

## Group E — Keep as `reverse`; flag for re-orientation (do not sign in place)

Each of these has a **definite forward inverse with a known sign**, but the edge is oriented against
causation (`role: reverse`). In a DMDB path (ordered cause→effect, drug→disease) a reverse-oriented
edge is a **mis-oriented edge**, not a signable step: multiplying a backward causal arrow into a
forward-walking product is unsound. The right resolution is to **flip the edge to its forward inverse**
(a data fix), after which it composes with the inverse's known sign. Recommend leaving these
`reverse` but adding an explicit re-orientation target in the `note`, and — see the checker refinement
below — having the checker emit a distinct **"re-orient"** verdict rather than a bland "indeterminate."

### 18. `caused by` — current: `{sign: +1, role: reverse, confidence: review}`

> "holds between two entities where the occurrence, existence, or activity of one **is caused by** the
> occurrence or generation of the other" — Biolink 4.4.3 (`inverse: causes`).
> Source: `https://biolink.github.io/biolink-model/caused_by/`

Inverse of `causes` (lexicon `+1` high). **Suggestion: (E) keep `reverse`; `note: "re-orient to
'causes' (+1)"`.**

### 19. `disrupted by` — current: `{sign: -1, role: reverse, confidence: review}`

> "describes a relationship where the structure, function, or occurrence of one entity is **degraded
> or interfered with by** another." — Biolink 4.4.3 (`is_a: affected by`, `inverse: disrupts`).
> Source: `https://biolink.github.io/biolink-model/disrupted_by/`

Inverse of `disrupts` (lexicon `−1` high). **Suggestion: (E) keep `reverse`; `note: "re-orient to
'disrupts' (−1)"`.**

### 20. `is metabolite of` — current: `{sign: +1, role: reverse, confidence: review}`

> "holds between two molecular entities in which the first one **is derived from the second one** as a
> product of metabolism" — Biolink 4.4.3 (`inverse: has metabolite`).
> Source: `https://biolink.github.io/biolink-model/is_metabolite_of/`

Inverse of `has metabolite` (#6, `+1`). Unlike the phenotype case, derivation is **causally
asymmetric** (the metabolite does not generate more parent), so it cannot be reclassified to
correlation. **Suggestion: (E) keep `reverse`; `note: "re-orient to 'has metabolite' (+1)"`.**

### 21. `produced by` — current: `{sign: +1, role: reverse, confidence: review}`

> Biolink 4.4.3 declares `produced by` as `inverse: produces` (`exact_mappings: RO:0003001`); its
> forward twin `produces` is defined "holds between a material entity and a product that is generated
> through the intentional actions or functioning of the material entity."
> Source: `https://biolink.github.io/biolink-model/produced_by/`

Inverse of `produces` (lexicon `+1` high). **Suggestion: (E) keep `reverse`; `note: "re-orient to
'produces' (+1)"`.**

### 22. `derives from` — current: `{sign: +1, role: reverse, confidence: review}`

> "holds between two distinct material entities, the **new entity and the old entity**, in which the
> new entity begins to exist when the old entity ceases to exist …" — Biolink 4.4.3
> (`inverse: derives into`).
> Source: `https://biolink.github.io/biolink-model/derives_from/`

Inverse of `derives into` (#7, `+1`). **Suggestion: (E) keep `reverse`; `note: "re-orient to
'derives into' (+1)"`.**

---

## Neutral scaffolding already at `confidence: high` — confirmed, no change

For completeness (self-verification), the lexicon's other `sign: 0` entries are `role: contextual` or
`role: structural` and are **not** opaque (they are deliberately neutral and are skipped, never routed
to indeterminate). Each is a Biolink location / participation / interaction / part-hood / similarity
relation with no direction of influence, so `sign: 0, confidence: high` is correct and needs **no
change**: `participates in`, `occurs in`, `in taxon`, `located in`, `location of`, `expressed in`,
`precedes`, `capable of`, `actively involved in`, `has participant`, `molecularly interacts with`,
`directly interacts with`, `physically interacts with`, `interacts with`, `in complex with`,
`coexists with`, `part of`, `has part`, `subclass of`, `superclass of`, `chemically similar to`,
`similar to`, `has active ingredient`. (If #11 `expresses` and #12 `enables` are reassigned as
suggested, they join this neutral set consistently with their Biolink parents `location of` and
`participates in`.)

---

## Expected impact & one optional checker refinement

- **Groups A + C (11 predicates)** move out of `review` and compose with a definite sign — this is the
  bulk of the indeterminate reduction, because these are directional predicates that were only
  indeterminate for lack of a confirmed sign.
- **Group B (3 predicates)** stop being (incorrectly) counted as directional; they become clean
  neutral scaffolding.
- **Groups D + E (8 predicates)** stay indeterminate *by design* — but the fix is now explicit and
  data-level (a named sibling to re-curate to, or an edge to re-orient), so they surface as
  actionable review items rather than silent "indeterminate."

**Optional refinement (worth flagging, not required for the lexicon edit):** split the checker's
single `indeterminate` verdict into two — **`opaque`** (Group D: "direction unknown → re-curate to a
signed sibling") and **`re-orient`** (Group E: "edge points against causation → flip to its forward
inverse"). Both are already distinguishable from the lexicon's `role`/orientation fields, and each
carries a different, concrete fix. This does not reduce the count of non-composable edges, but it
converts an opaque "needs-review" into a specific instruction, which is the practical goal of Issue #30.

---

## Self-verification checklist (every `review` / opaque / reverse entry addressed)

Confirmed the following `confidence: review` predicates in `predicate_polarity.yaml` each have a
Biolink-grounded suggestion above (§ = section number):

`increases transport of` (§1) · `increases response to` (§2) · `decreases response to` (§3) ·
`has output` (§4) · `predisposes` (§5) · `has metabolite` (§6) · `derives into` (§7) ·
`has phenotype` (§8) · `manifestation of` (§9) · `phenotype of` (§10) · `expresses` (§11) ·
`enables` (§12) · `contraindicated for` (§13) · `regulates` (§14) · `correlated with` (§15) ·
`affects risk for` (§16) · `affected by` (§17) · `caused by` (§18) · `disrupted by` (§19) ·
`is metabolite of` (§20) · `produced by` (§21) · `derives from` (§22).

= **22 review predicates, all addressed.** The four **opaque** entries (`regulates`, `correlated with`,
`affects risk for`, `affected by`) and the seven **reverse** entries (`phenotype of`, `caused by`,
`affected by`, `disrupted by`, `is metabolite of`, `produced by`, `derives from`) — the ones that
actually produce `indeterminate` — are each covered (Groups C/D/E). Every suggestion quotes the
Biolink `description:` text and cites its version-pinned source URL.
