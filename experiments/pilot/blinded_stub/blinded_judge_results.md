# Blinded judge results

- generated: `2026-07-23T13:14:22+00:00`
- mode: **stub**
- judge: STUB (offline, deterministic — NO API)
- paths: 29  ·  arms: outputs
- seed: 1234  ·  eval_pairs: (none)

> The judge saw only path *content* (nodes / predicates / evidence / drug+disease); it was never
> told the source model. The per-path table below is blind (drug→disease is shared across arms).
> The reveal key and per-arm aggregate are joined in only after scoring.

## Per-path verdicts (blind)

| blind_id | drug → disease | evidence-edges | edge SUPPORT | path verdict | vs legacy |
|---|---|---|---|---|---|
| B001 | calcium acetate → Hypocalcemia | 2 | 2/2 | revise | agent_simpler_but_valid |
| B002 | clortermine → Anorexia | 2 | 3/3 | revise | agent_simpler_but_valid |
| B003 | alteplase → Pulmonary embolism | 4 | 6/6 | revise | agent_simpler_but_valid |
| B004 | cetuximab → Malignant tumor of colon | 3 | 4/4 | accept | agent_more_complete |
| B005 | Etanercept → Psoriasis with arthropathy | 3 | 3/3 | accept | reproduces |
| B006 | imatinib → Chronic myeloid leukemia, BCR-ABL positive | 2 | 2/2 | reject | disagree |
| B007 | insulin human → Diabetes Mellitus, Type 1 | 4 | 7/7 | revise | agent_simpler_but_valid |
| B008 | bleomycin → Squamous cell carcinoma | 4 | 4/4 | revise | agent_simpler_but_valid |
| B009 | imatinib → Chronic myelogenous leukemia, BCR-ABL positive | 2 | 3/3 | reject | disagree |
| B010 | Thiamine → Avitaminosis | 4 | 4/4 | reject | disagree |
| B011 | alteplase → Pulmonary embolism | 3 | 5/5 | revise | agent_simpler_but_valid |
| B012 | sermorelin → Pituitary dwarfism | 3 | 6/6 | reject | disagree |
| B013 | cetuximab → Malignant tumor of colon | 3 | 3/3 | accept | agent_more_complete |
| B014 | oprelvekin → Thrombocytopenic disorder | 4 | 6/6 | accept | reproduces |
| B015 | anakinra → Cryopyrin-associated periodic syndrome | 3 | 5/5 | reject | disagree |
| B016 | Thiamine → Avitaminosis | 1 | 1/1 | reject | disagree |
| B017 | azathioprine → Rheumatoid arthritis | 4 | 8/8 | revise | agent_simpler_but_valid |
| B018 | alteplase → Pulmonary embolism | 3 | 3/3 | revise | agent_simpler_but_valid |
| B019 | urokinase → Pulmonary thromboembolism | 4 | 4/4 | reject | disagree |
| B020 | atorvastatin → Hypercholesterolemia | 5 | 5/5 | revise | agent_simpler_but_valid |
| B021 | empagliflozin → Diabetes Mellitus, Type 2 | 5 | 5/5 | accept | reproduces |
| B022 | imatinib → Chronic myeloid leukemia | 3 | 3/3 | reject | disagree |
| B023 | aminobenzoic acid → Dermatomyositis | 3 | 5/5 | revise | agent_simpler_but_valid |
| B024 | thiamine → Avitaminosis | 3 | 3/3 | accept | reproduces |
| B025 | aminobenzoic acid → Dermatomyositis | 2 | 4/4 | revise | agent_simpler_but_valid |
| B026 | aminobenzoic acid → Dermatomyositis | 2 | 4/4 | revise | agent_simpler_but_valid |
| B027 | cetuximab → Malignant tumor of colon | 3 | 3/3 | accept | agent_more_complete |
| B028 | desmopressin → Hereditary factor VIII deficiency disease | 4 | 6/6 | accept | reproduces |
| B029 | donepezil → Alzheimer's disease | 3 | 4/4 | accept | reproduces |

## Aggregate (unblinded after scoring)

**Path-coherence verdicts**

| arm | accept | revise | reject | abstain | other |
|---|---|---|---|---|---|
| outputs | 9 | 12 | 8 | 0 | 0 |
| **all** | 9 | 12 | 8 | 0 | 0 |

**Agreement with legacy** (judge did not classify the pair as `disagree`, among paths that have a legacy path)

- overall: 21/29 (72%)
- outputs: 21/29 (72%)

**Gold-comparison distribution**

| classification | count |
|---|---|
| reproduces | 6 |
| agent_more_complete | 3 |
| agent_simpler_but_valid | 12 |
| disagree | 8 |
| other | 0 |

Mean per-path edge SUPPORT fraction: **1.0**

## Reveal key

> Do not consult before scoring is complete. Maps each blind id to its source arm/file.

| blind_id | arm | legacy_path_id | source_file |
|---|---|---|---|
| B001 | outputs | DB00258_MESH_D006996_1 | experiments/pilot/outputs/DB00258_MESH_D006996_1.yaml |
| B002 | outputs | DB01527_MESH_D000856_1 | experiments/pilot/outputs/DB01527_MESH_D000856_1.yaml |
| B003 | outputs | DB00009_MESH_D011655_1 | experiments/pilot/outputs/DB00009_MESH_D011655_1__r2.yaml |
| B004 | outputs | DB00002_MESH_D003110_1 | experiments/pilot/outputs/DB00002_MESH_D003110_1__r2.yaml |
| B005 | outputs | DB00005_MESH_D015535_1 | experiments/pilot/outputs/DB00005_MESH_D015535_1.yaml |
| B006 | outputs | DB00619_MESH_D015464_1 | experiments/pilot/outputs/DB00619_MESH_D015464_1__r2.yaml |
| B007 | outputs | DB00030_MESH_D003922_1 | experiments/pilot/outputs/DB00030_MESH_D003922_1.yaml |
| B008 | outputs | DB00290_MESH_D002294_1 | experiments/pilot/outputs/DB00290_MESH_D002294_1.yaml |
| B009 | outputs | DB00619_MESH_D015464_1 | experiments/pilot/outputs/DB00619_MESH_D015464_1__r3.yaml |
| B010 | outputs | DB00152_MESH_D001361_1 | experiments/pilot/outputs/DB00152_MESH_D001361_1__r2.yaml |
| B011 | outputs | DB00009_MESH_D011655_1 | experiments/pilot/outputs/DB00009_MESH_D011655_1__r3.yaml |
| B012 | outputs | DB00010_MESH_D004393_1 | experiments/pilot/outputs/DB00010_MESH_D004393_1.yaml |
| B013 | outputs | DB00002_MESH_D003110_1 | experiments/pilot/outputs/DB00002_MESH_D003110_1__r3.yaml |
| B014 | outputs | DB00038_MESH_D013921_1 | experiments/pilot/outputs/DB00038_MESH_D013921_1.yaml |
| B015 | outputs | DB00026_MESH_D056587_1 | experiments/pilot/outputs/DB00026_MESH_D056587_1.yaml |
| B016 | outputs | DB00152_MESH_D001361_1 | experiments/pilot/outputs/DB00152_MESH_D001361_1.yaml |
| B017 | outputs | DB00993_MESH_D001172_1 | experiments/pilot/outputs/DB00993_MESH_D001172_1.yaml |
| B018 | outputs | DB00009_MESH_D011655_1 | experiments/pilot/outputs/DB00009_MESH_D011655_1.yaml |
| B019 | outputs | DB00013_MESH_D011655_1 | experiments/pilot/outputs/DB00013_MESH_D011655_1.yaml |
| B020 | outputs | DB01076_MESH_D006937_1 | experiments/pilot/outputs/DB01076_MESH_D006937_1.yaml |
| B021 | outputs | DB09038_MESH_D003924_1 | experiments/pilot/outputs/DB09038_MESH_D003924_1.yaml |
| B022 | outputs | DB00619_MESH_D015464_1 | experiments/pilot/outputs/DB00619_MESH_D015464_1.yaml |
| B023 | outputs | B02362_MESH_D003882_1 | experiments/pilot/outputs/B02362_MESH_D003882_1__r2.yaml |
| B024 | outputs | DB00152_MESH_D001361_1 | experiments/pilot/outputs/DB00152_MESH_D001361_1__r3.yaml |
| B025 | outputs | B02362_MESH_D003882_1 | experiments/pilot/outputs/B02362_MESH_D003882_1__r3.yaml |
| B026 | outputs | B02362_MESH_D003882_1 | experiments/pilot/outputs/B02362_MESH_D003882_1.yaml |
| B027 | outputs | DB00002_MESH_D003110_1 | experiments/pilot/outputs/DB00002_MESH_D003110_1.yaml |
| B028 | outputs | DB00035_MESH_D006467_1 | experiments/pilot/outputs/DB00035_MESH_D006467_1.yaml |
| B029 | outputs | DB00843_MESH_D000544_1 | experiments/pilot/outputs/DB00843_MESH_D000544_1.yaml |