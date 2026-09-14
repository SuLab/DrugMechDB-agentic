# Term-existence audit

Does every node CURIE in the corpus resolve in its source ontology, and does
each record `name` match the canonical label? **This is an audit, not a gate** —
nothing in `just qc` enforces it.

- files checked: **4846**
- node occurrences: **33009**
- unique CURIEs resolved: **5122**
- existence failures (distinct CURIEs): **186**
- name mismatches (distinct CURIE+name): **624**

## Status by prefix

| prefix | exists | absent | obsolete | unresolved | skipped |
|---|---|---|---|---|---|
| CHEBI | 452 | 0 | 1 | 0 | 0 |
| CL | 181 | 0 | 0 | 0 | 0 |
| DB | 0 | 0 | 0 | 0 | 220 |
| GO | 8696 | 1 | 107 | 0 | 0 |
| HP | 1476 | 0 | 2 | 0 | 0 |
| InterPro | 0 | 0 | 0 | 0 | 879 |
| MESH | 11429 | 0 | 204 | 0 | 0 |
| PR | 0 | 0 | 0 | 4 | 0 |
| Pfam | 0 | 0 | 0 | 0 | 112 |
| TIGR | 0 | 0 | 0 | 0 | 3 |
| UBERON | 511 | 0 | 0 | 0 | 0 |
| UniProt | 6982 | 0 | 70 | 3 | 0 |
| reactome | 322 | 7 | 0 | 0 | 0 |
| taxonomy | 1317 | 30 | 0 | 0 | 0 |

> **7 node occurrences are UNRESOLVED** — the authority could not be
> reached, or does not serve that ontology. These are *not* failures: nothing was
> established about them either way. Re-run with network access to settle them.

## Existence failures (186)

The identifier does not resolve (ABSENT) or is deprecated upstream (OBSOLETE). One row per distinct CURIE.

| CURIE | status | record name | Biolink type | first seen in |
|---|---|---|---|---|
| `GO:0000737` | obsolete | DNA catabolic process, endonucleolytic | BiologicalProcess | `DB00003_MESH_D003550_1.yaml` |
| `GO:1901998` | obsolete | toxin transport | BiologicalProcess | `DB00004_MESH_D016410_1.yaml` |
| `taxonomy:11103` | absent | Hepacivirus C | OrganismTaxon | `DB00008_MESH_D019698_1.yaml` |
| `reactome:R-HSA-140834` | absent | Extrinsic Pathway of Fibrin Clot Formation | Pathway | `DB00036_MESH_D002836_1.yaml` |
| `GO:0046323` | obsolete | glucose import | BiologicalProcess | `DB00046_MESH_D003922_1.yaml` |
| `MESH:C086648` | obsolete | Eptifibatide | Drug | `DB00063_MESH_D054058_1.yaml` |
| `MESH:C096529` | obsolete | alemtuzumab | Drug | `DB00087_MESH_D020529_1.yaml` |
| `MESH:C554127` | obsolete | interferon alfa-2b | Drug | `DB00105_MESH_C554498_1.yaml` |
| `MESH:C105196` | obsolete | enfuvirtide | Drug | `DB00109_MESH_D015658_1.yaml` |
| `MESH:C096001` | obsolete | daclizumab | Drug | `DB00111_MESH_D020529_1.yaml` |
| `GO:005507` | absent | iron ion homeostasis | BiologicalProcess | `DB00115_MESH_D018798_1.yaml` |
| `GO:0060558` | obsolete | regulation of calcidiol 1-monooxygenase activity | BiologicalProcess | `DB00136_MESH_D006996_1.yaml` |
| `GO:1903184` | obsolete | L-dopa metabolic process | BiologicalProcess | `DB00190_MESH_D010300_1.yaml` |
| `GO:0090503` | obsolete | RNA phosphodiester bond hydrolysis, exonucleolytic | BiologicalProcess | `DB00194_MESH_D007635_1.yaml` |
| `GO:0043631` | obsolete | RNA polyadenylation | BiologicalProcess | `DB00194_MESH_D007635_1.yaml` |
| `taxonomy:1535326` | absent | Candida | OrganismTaxon | `DB00196_MESH_C536777_1.yaml` |
| `MESH:C064276` | obsolete | Pantoprazole | Drug | `DB00213_MESH_D005764_1.yaml` |
| `MESH:C026116` | obsolete | torsemide | Drug | `DB00214_MESH_D004487_1.yaml` |
| `UniProt:A0A0E1NU92` | obsolete | DNA gyrase subunit A | Protein | `DB00218_MESH_D010930_1.yaml` |
| `UniProt:A0A0E1NWQ7` | obsolete | DNA topoisomerase 4 subunit A | Protein | `DB00218_MESH_D010930_1.yaml` |
| `UniProt:Q9Z7D7` | obsolete | DNA topoisomerase 1 | Protein | `DB00218_MESH_D061387_1.yaml` |
| `MESH:C074679` | obsolete | reboxetine | Drug | `DB00234_MESH_D003865_1.yaml` |
| `UniProt:A0A2B7ICU0` | obsolete | Dihydropteroate synthase (Cutibacterium acnes) | Protein | `DB00250_MESH_D000152_1.yaml` |
| `MESH:C036944` | obsolete | Sulfanilamide | Drug | `DB00259_MESH_D002181_1.yaml` |
| `GO:0016575` | obsolete | histone deacetylation | BiologicalProcess | `DB00277_MESH_D000080445_1.yaml` |
| `GO:0019933` | obsolete | cAMP-mediated signaling | BiologicalProcess | `DB00277_MESH_D000080445_1.yaml` |
| `MESH:C019248` | obsolete | Pamidronic acid | Drug | `DB00282_MESH_C562390_1.yaml` |
| `MESH:C446479` | obsolete | ertapenem | Drug | `DB00303_MESH_D011018_1.yaml` |
| `MESH:C095105` | obsolete | Bexarotene | Drug | `DB00307_MESH_D016410_1.yaml` |
| `GO:0071442` | obsolete | H3 hyperacetylation | BiologicalProcess | `DB00313_MESH_D004827_1.yaml` |
| `MESH:C419708` | obsolete | Gefitinib | Drug | `DB00317_MESH_D002289_1.yaml` |
| `MESH:C066340` | obsolete | Tolcapone | Drug | `DB00323_MESH_D010300_1.yaml` |
| `MESH:C012255` | obsolete | clobazam | Drug | `DB00349_MESH_D065768_1.yaml` |
| `UniProt:R4YB92` | obsolete | Peptidoglycan D,D-transpeptidase FtsI | Protein | `DB00355_MESH_D012226_1.yaml` |
| `MESH:C030852` | obsolete | vinorelbine | Drug | `DB00361_MESH_D002289_1.yaml` |
| `MESH:C102786` | obsolete | anidulafungin | Drug | `DB00362_MESH_D058387_1.yaml` |
| `MESH:C035133` | obsolete | Mirtazapine | Drug | `DB00370_MESH_D003865_1.yaml` |
| `UniProt:Q9UE69` | obsolete | 5HT3 serotonin receptor | Protein | `DB00370_MESH_D003865_1.yaml` |
| `MESH:C471405` | obsolete | Sorafenib | Drug | `DB00398_MESH_D002292_1.yaml` |
| `MESH:C088658` | obsolete | zoledronic acid | Drug | `DB00399_MESH_C562390_1.yaml` |
| `MESH:C061333` | obsolete | pramipexole | Drug | `DB00413_MESH_D010300_1.yaml` |
| `UniProt:A0A132A3X0` | obsolete | Gamma-aminobutyric acid receptor subunit beta-like protein 1 (Sarcoptes scabiei) | Protein | `DB00431_MESH_D012532_1.yaml` |
| `UniProt:Q155P6` | obsolete | 30S ribosomal protein S12 | Protein | `DB00479_MESH_D016868_1.yaml` |
| `MESH:C467567` | obsolete | Lenalidomide | Drug | `DB00480_MESH_D009101_1.yaml` |
| `GO:0006305` | obsolete | DNA alkylation | BiologicalProcess | `DB00488_MESH_D010051_1.yaml` |
| `GO:0102084` | obsolete | L-dopa O-methyltransferase activity | MolecularActivity | `DB00494_MESH_D010300_1.yaml` |
| `MESH:C056814` | obsolete | Cefdinir | Drug | `DB00535_MESH_D011018_1.yaml` |
| `UniProt:D8GUW8` | obsolete | DNA gyrase subunit A | Protein | `DB00537_MESH_D000881_1.yaml` |
| `UniProt:D8H6M3` | obsolete | DNA topoisomerase 4 subunit A | Protein | `DB00537_MESH_D000881_1.yaml` |
| `UniProt:A0A156YKX6` | obsolete | DNA gyrase subunit A | Protein | `DB00537_MESH_D004756_1.yaml` |
| `UniProt:A0A156J405` | obsolete | DNA topoisomerase 4 subunit A | Protein | `DB00537_MESH_D004756_1.yaml` |
| `UniProt:R4Y7H5` | obsolete | DNA gyrase subunit A | Protein | `DB00537_MESH_D012226_1.yaml` |
| `UniProt:R4YE07` | obsolete | DNA topoisomerase 4 subunit A | Protein | `DB00537_MESH_D012226_1.yaml` |
| `UniProt:A0A717UR96` | obsolete | DNA gyrase subunit A | Protein | `DB00537_MESH_D014435_1.yaml` |
| `UniProt:A0A715KJC7` | obsolete | DNA topoisomerase 4 subunit A | Protein | `DB00537_MESH_D014435_1.yaml` |
| `MESH:C047781` | obsolete | lamotrigine | Drug | `DB00555_MESH_D004827_1.yaml` |
| `MESH:C086232` | obsolete | Bosentan | Drug | `DB00559_MESH_D000081029_1.yaml` |
| `MESH:C084555` | obsolete | valaciclovir | Drug | `DB00577_MESH_D002644_1.yaml` |
| `UniProt:S2ZP52` | obsolete | 30S ribosomal protein S4 | Protein | `DB00595_MESH_D000196_1.yaml` |
| `UniProt:S3ABF8` | obsolete | 30S ribosomal protein S9 | Protein | `DB00595_MESH_D000196_1.yaml` |
| `UniProt:D0RGZ2` | obsolete | 30S ribosomal protein S4 | Protein | `DB00595_MESH_D002006_1.yaml` |
| `UniProt:D0RGV5` | obsolete | 30S ribosomal protein S9 | Protein | `DB00595_MESH_D002006_1.yaml` |
| `UniProt:S7IK33` | obsolete | 30S ribosomal protein S4 | Protein | `DB00595_MESH_D009956_1.yaml` |
| `UniProt:S7IMP9` | obsolete | 30S ribosomal protein S9 | Protein | `DB00595_MESH_D009956_1.yaml` |
| `MESH:C072042` | obsolete | Latanoprost | Drug | `DB00654_MESH_D005902_1.yaml` |
| `MESH:C043877` | obsolete | acamprosate | Drug | `DB00659_MESH_D000437_1.yaml` |
| `UniProt:Q9Z7I9` | obsolete | DNA topoisomerase 4 subunit A (Chlamydial pneumoniae) | Protein | `DB00685_MESH_D061387_1.yaml` |
| `GO:0001207` | obsolete | histone displacement | BiologicalProcess | `DB00694_MESH_D004915_1.yaml` |
| `MESH:C088482` | obsolete | Tamsulosin | Drug | `DB00706_MESH_D011470_1.yaml` |
| `MESH:C073007` | obsolete | ibandronic acid | Drug | `DB00710_MESH_D006934_1.yaml` |
| `MESH:C024262` | obsolete | Norethindrone acetate | Drug | `DB00717_MESH_D004715_1.yaml` |
| `MESH:C056493` | obsolete | imiquimod | Drug | `DB00724_MESH_D003218_1.yaml` |
| `MESH:C060142` | obsolete | Nateglinide | Drug | `DB00731_MESH_D003924_1.yaml` |
| `GO:0070997` | obsolete | Neuronal cell death | BiologicalProcess | `DB00740_MESH_D000690_1.yaml` |
| `MESH:C048833` | obsolete | Modafinil | Drug | `DB00745_MESH_D009290_1.yaml` |
| `MESH:C059500` | obsolete | meropenem | Drug | `DB00760_MESH_D008585_1.yaml` |
| `MESH:C036006` | obsolete | oxcarbazepine | Drug | `DB00776_MESH_D004828_1.yaml` |
| `GO:0045272` | obsolete | plasma membrane respiratory chain complex I | CellularComponent | `DB00781_MESH_D003234_1.yaml` |
| `GO:0010737` | obsolete | Protein kinase A signaling | BiologicalProcess | `DB00806_MESH_D016491_1.yaml` |
| `MESH:C065757` | obsolete | Meloxicam | Drug | `DB00814_MESH_D001171_1.yaml` |
| `GO:0007263` | obsolete | nitric oxide mediated signal transduction | BiologicalProcess | `DB00820_MESH_D006976_1.yaml` |
| `GO:0006069` | obsolete | ethanol oxidation | BiologicalProcess | `DB00822_MESH_D000437_1.yaml` |
| `taxonomy:5519` | absent | Malassezia | OrganismTaxon | `DB00825_MESH_D012628_1.yaml` |
| `MESH:C076946` | obsolete | donepezil | Drug | `DB00843_MESH_D000544_1.yaml` |
| `MESH:C047246` | obsolete | temozolomide | Drug | `DB00853_MESH_D001254_1.yaml` |
| `MESH:C041359` | obsolete | terbinafine | Drug | `DB00857_MESH_D014006_1.yaml` |
| `GO:0140603` | obsolete | ATP hydrolysis activity | MolecularActivity | `DB00884_MESH_D010001_1.yaml` |
| `MESH:C059205` | obsolete | tiagabine | Drug | `DB00906_MESH_D004828_1.yaml` |
| `MESH:C076731` | obsolete | Levosimendan | Drug | `DB00922_MESH_D006333_1.yaml` |
| `MESH:C084588` | obsolete | Methanthelinium | Drug | `DB00940_MESH_D010437_1.yaml` |
| `MESH:C047360` | obsolete | Felbamate | Drug | `DB00949_MESH_D004827_1.yaml` |
| `UniProt:W8TZX4` | obsolete | 50S ribosomal subunit assembly factor BipA (Staphylococcus aureus) | Protein | `DB00954_MESH_D013203_1.yaml` |
| `MESH:C008729` | obsolete | oxaprozin | Drug | `DB00991_MESH_D001171_1.yaml` |
| `UniProt:Q8GND6` | obsolete | Dihydropteroate synthase | Protein | `DB01015_MESH_D004405_1.yaml` |
| `UniProt:A0A448KJJ7` | obsolete | 30S ribosomal protein S9 | Protein | `DB01017_MESH_D002602_1.yaml` |
| `UniProt:X2JRY4` | obsolete | 30S ribosomal protein S4 | Protein | `DB01017_MESH_D010518_1.yaml` |
| `UniProt:X2K2U8` | obsolete | 30S ribosomal protein S9 | Protein | `DB01017_MESH_D010518_1.yaml` |
| `GO:0051208` | obsolete | Sequestering of calcium ion | BiologicalProcess | `DB01020_MESH_D000787_1.yaml` |
| `MESH:C081309` | obsolete | Irbesartan | Drug | `DB01029_MESH_D003928_1.yaml` |
| `GO:0015711` | obsolete | Organic anion transport | BiologicalProcess | `DB01032_MESH_D015210_1.yaml` |
| `GO:0036473` | obsolete | cell death in response to oxidative stress | BiologicalProcess | `DB01041_MESH_D009101_1.yaml` |
| `MESH:C078049` | obsolete | Gatifloxacin | Drug | `DB01044_MESH_D003234_1.yaml` |
| `MESH:C106538` | obsolete | abacavir | Drug | `DB01048_MESH_D015658_1.yaml` |
| `UniProt:G4NN22` | obsolete | DNA topoisomerase 1 | Protein | `DB01059_MESH_D004716_1.yaml` |
| `MESH:C055122` | obsolete | orlistat | Drug | `DB01083_MESH_D009765_1.yaml` |
| `MESH:C065180` | obsolete | fluvastatin | Drug | `DB01095_MESH_D001161_1.yaml` |
| `MESH:C045463` | obsolete | Leflunomide | Drug | `DB01097_MESH_D001172_1.yaml` |
| `MESH:C043211` | obsolete | Carvedilol | Drug | `DB01136_MESH_D006973_1.yaml` |
| `MESH:C121905` | obsolete | micafungin | Drug | `DB01141_MESH_D058387_1.yaml` |
| `MESH:C052018` | obsolete | cefprozil | Drug | `DB01150_MESH_D001991_1.yaml` |
| `UniProt:J7M8X7` | obsolete | Autolysin | Protein | `DB01150_MESH_D014069_1.yaml` |
| `MESH:C103274` | obsolete | Gemifloxacin | Drug | `DB01155_MESH_D007710_1.yaml` |
| `UniProt:A0A0C4MI94` | obsolete | DNA topoisomerase 4 subunit A (Klebsiella pneumoniae) | Protein | `DB01155_MESH_D007710_1.yaml` |
| `UniProt:A0A443X2G9` | obsolete | DNA gyrase subunit A (Klebsiella pneumoniae) | Protein | `DB01155_MESH_D007710_1.yaml` |
| `MESH:C045645` | obsolete | cilostazol | Drug | `DB01166_MESH_D007383_1.yaml` |
| `MESH:C006632` | obsolete | arsenic trioxide | Drug | `DB01169_MESH_D015473_1.yaml` |
| `MESH:C011585` | obsolete | ciclopirox | Drug | `DB01188_MESH_D002179_1.yaml` |
| `MESH:C026098` | obsolete | levetiracetam | Drug | `DB01202_MESH_D004828_1.yaml` |
| `MESH:C042734` | obsolete | Rifaximin | Drug | `DB01220_MESH_D006501_1.yaml` |
| `GO:0006306` | obsolete | DNA methylation | BiologicalProcess | `DB01262_MESH_D015470_1.yaml` |
| `UniProt:A0A6C1LUF2` | obsolete | Lanosterol 14-alpha demethylase (Coccidioides immitis) | Protein | `DB01263_MESH_D003047_1.yaml` |
| `MESH:C487779` | obsolete | Telbivudine | Drug | `DB01265_MESH_D019694_1.yaml` |
| `MESH:C473478` | obsolete | sunitinib | Drug | `DB01268_MESH_D002292_2.yaml` |
| `GO:0046855` | obsolete | Inositol phosphate dephosphorylation | BiologicalProcess | `DB01356_MESH_D001171_1.yaml` |
| `GO:0006919` | obsolete | activation of cysteine-type endopeptidase activity involved in apoptotic process | BiologicalProcess | `DB01394_MESH_D006073_1.yaml` |
| `MESH:C043266` | obsolete | Cefepime | Drug | `DB01413_MESH_D011018_1.yaml` |
| `MESH:C053267` | obsolete | cefpodoxime proxetil | Drug | `DB01416_MESH_D006069_1.yaml` |
| `GO:0015874` | obsolete | norepinephrine transport | BiologicalProcess | `DB01579_MESH_D009765_4.yaml` |
| `GO:0055072` | obsolete | iron ion homeostasis | BiologicalProcess | `DB01592_MESH_D018798_1.yaml` |
| `MESH:C043265` | obsolete | tazobactam | Drug | `DB01606_MESH_D000077299_1.yaml` |
| `MESH:C415250` | obsolete | Deferasirox | Drug | `DB01609_MESH_D017086_1.yaml` |
| `CHEBI:21241` | obsolete | vitamin C | ChemicalSubstance | `DB01698_MESH_D001206_1.yaml` |
| `MESH:C111237` | obsolete | vorinostat | Drug | `DB02546_MESH_D016410_1.yaml` |
| `GO:0070577` | obsolete | acetylated histones | ChemicalSubstance | `DB02546_MESH_D016410_1.yaml` |
| `GO:0071158` | obsolete | cell cycle arrest | BiologicalProcess | `DB02546_MESH_D016410_1.yaml` |
| `UniProt:V5AL63` | obsolete | Elongation factor G | Protein | `DB02703_MESH_D004756_1.yaml` |
| `UniProt:S7JCG1` | obsolete | Elongation factor G | Protein | `DB02703_MESH_D009956_1.yaml` |
| `UniProt:R4Y4Z5` | obsolete | Elongation factor G | Protein | `DB02703_MESH_D012226_1.yaml` |
| `UniProt:A0A8A6J2U1` | obsolete | Elongation factor G | Protein | `DB02703_MESH_D016868_1.yaml` |
| `MESH:C118667` | obsolete | dronedarone | Drug | `DB04855_MESH_D001281_1.yaml` |
| `MESH:C001652` | obsolete | omacetaxine mepesuccinate | Drug | `DB04865_MESH_D015464_1.yaml` |
| `MESH:C502012` | obsolete | Evogliptin | Drug | `DB04876_MESH_D003924_1.yaml` |
| `MESH:C048107` | obsolete | Milnacipran | Drug | `DB04896_MESH_D005356_1.yaml` |
| `GO:0070265` | obsolete | Necrotic cell death | BiologicalProcess | `DB05013_MESH_D055623_1.yaml` |
| `MESH:C099150` | obsolete | Trabectedin | Drug | `DB05109_MESH_D007890_1.yaml` |
| `UniProt:B0B3C9` | obsolete | Genome polyprotein | Protein | `DB05521_MESH_D019698_1.yaml` |
| `MESH:C543333` | obsolete | ramucirumab | Drug | `DB05578_MESH_D002289_1.yaml` |
| `UniProt:Q9NJG8` | obsolete | DNA topoisomerase I | Protein | `DB05630_MESH_D007896_1.yaml` |
| `MESH:C005312` | obsolete | sulfathiazole | Drug | `DB06147_MESH_D014848_1.yaml` |
| `MESH:C089032` | obsolete | Rimonabant | Drug | `DB06155_MESH_D009765_1.yaml` |
| `MESH:C523979` | obsolete | Tapentadol | Drug | `DB06204_MESH_D010146_1.yaml` |
| `MESH:C099245` | obsolete | Doripenem | Drug | `DB06211_MESH_D002764_1.yaml` |
| `MESH:C116664` | obsolete | tolvaptan | Drug | `DB06212_MESH_D007010_1.yaml` |
| `GO:0033387` | obsolete | Putrescine biosynthetic process from ornithine | BiologicalProcess | `DB06243_MESH_D014353_1.yaml` |
| `MESH:C579652` | obsolete | Armodafinil | Drug | `DB06413_MESH_D009290_1.yaml` |
| `MESH:C515501` | obsolete | Ceftaroline fosamil | Drug | `DB06590_MESH_D004927_1.yaml` |
| `MESH:C496932` | obsolete | Panobinostat | Drug | `DB06603_MESH_D009101_1.yaml` |
| `HP:0002355` | obsolete | Difficulty walking | PhenotypicFeature | `DB06637_MESH_D009103_1.yaml` |
| `MESH:C102070` | obsolete | lumefantrine | Drug | `DB06708_MESH_D016778_1.yaml` |
| `GO:0050828` | obsolete | Surface tension at the air-liquid interface | BiologicalProcess | `DB06761_MESH_D012127_1.yaml` |
| `MESH:C008976` | obsolete | polidocanol | Drug | `DB06811_MESH_D014648_1.yaml` |
| `UniProt:Q7ZJM1` | obsolete | Integrase | Protein | `DB06817_MESH_D015658_1.yaml` |
| `MESH:C503700` | obsolete | Ticagrelor | Drug | `DB08816_MESH_D016491_1.yaml` |
| `MESH:C044919` | obsolete | deferiprone | Drug | `DB08826_MESH_D017086_1.yaml` |
| `GO:0005947` | obsolete | mitochondrial alpha-ketoglutarate dehydrogenase complex | CellularComponent | `DB08842_MESH_D000544_1.yaml` |
| `MESH:C547738` | obsolete | brentuximab vedotin | Drug | `DB08870_MESH_D006689_1.yaml` |
| `reactome:R-HSA-8932339` | absent | ROS sensing by NFE2L2 | Pathway | `DB08908_MESH_D011565_1.yaml` |
| `MESH:C562325` | obsolete | dolutegravir | Drug | `DB08930_MESH_D015658_1.yaml` |
| `GO:0044825` | obsolete | retroviral strand transfer activity | MolecularActivity | `DB08930_MESH_D015658_1.yaml` |
| `GO:0051934` | obsolete | catecholamine uptake involved in synaptic transmission | BiologicalProcess | `DB09016_MESH_D003866_1.yaml` |
| `UniProt:Q5L478` | obsolete | Nonstructural protein 5A | Protein | `DB09027_MESH_D019698_1.yaml` |
| `reactome:R-HSA-140877` | absent | Formation of Fibrin Clot (Clotting Cascade) | Pathway | `DB09030_MESH_D020521_1.yaml` |
| `MESH:C581771` | obsolete | nivolumab | Drug | `DB09035_MESH_D002289_1.yaml` |
| `MESH:C557874` | obsolete | vortioxetine | Drug | `DB09068_MESH_D003865_1.yaml` |
| `GO:0007048` | obsolete | Obsolete oncogenesis | BiologicalProcess | `DB09074_MESH_D010051_1.yaml` |
| `GO:0005747` | obsolete | Mitochondrial respiratory chain complex I | CellularComponent | `DB09081_MESH_D029242_1.yaml` |
| `MESH:C088408` | obsolete | ivabradine | Drug | `DB09083_MESH_D000787_1.yaml` |
| `GO:0003809` | obsolete | Obsolete thrombin activity | BiologicalProcess | `DB09108_MESH_D006467_1.yaml` |
| `GO:0042135` | obsolete | neurotransmitter catabolic process | BiologicalProcess | `DB09248_MESH_D003866_1.yaml` |
| `GO:0030641` | obsolete | regulation of cellular pH | BiologicalProcess | `DB09552_MESH_D010032_1.yaml` |
| `MESH:C032302` | obsolete | rilmenidine | Drug | `DB11738_MESH_D006973_1.yaml` |
| `HP:0025428` | obsolete | Bronchospasm | PhenotypicFeature | `DB12017_MESH_D001249_1.yaml` |
| `GO:0036475` | obsolete | neuron death in response to oxidative stress | BiologicalProcess | `DB12131_MESH_D003704_2.yaml` |
| `GO:0007253` | obsolete | cytoplasmic sequestering of NF-kappaB | BiologicalProcess | `DB12233_MESH_D001172_1.yaml` |
| `MESH:C005435` | obsolete | edaravone | Drug | `DB12243_MESH_D000690_1.yaml` |
| `MESH:C056507` | obsolete | gemcitabine | Drug | `DB12459_MESH_D002289_2.yaml` |

## Name mismatches (624)

The identifier resolves but the record's `name` differs from the ontology's canonical label. Weaker signal — ontologies carry synonyms a record may legitimately prefer.

| CURIE | record name | canonical label | first seen in |
|---|---|---|---|
| `MESH:D010411` | Induratio penis plastica | Penile Induration | `B02362_MESH_D010411_1.yaml` |
| `MESH:D003110` | Malignant tumor of colon | Colonic Neoplasms | `DB00002_MESH_D003110_1.yaml` |
| `MESH:D015535` | Psoriasis with arthropathy | Arthritis, Psoriatic | `DB00005_MESH_D015535_1.yaml` |
| `CL:0000232` | erythrocytes | erythrocyte | `DB00016_MESH_D000740_1.yaml` |
| `MESH:D006467` | Hereditary factor VIII deficiency disease | Hemophilia A | `DB00035_MESH_D006467_1.yaml` |
| `MESH:C103587` | eptacog alfa (activated) | recombinant FVIIa | `DB00036_MESH_D002836_1.yaml` |
| `MESH:D002836` | Hereditary factor IX deficiency disease | Hemophilia B | `DB00036_MESH_D002836_1.yaml` |
| `MESH:D013921` | Thrombocytopenic disorder | Thrombocytopenia | `DB00038_MESH_D013921_1.yaml` |
| `MESH:D007003` | Hypoglycemic disorder | Hypoglycemia | `DB00040_MESH_D007003_1.yaml` |
| `CL:0000767` | basophill | basophil | `DB00043_MESH_D000080223_1.yaml` |
| `reactome:R-HSA-2454202` | Allergen dependent IgE bound FCERI aggregation | Fc epsilon receptor (FCERI) signaling | `DB00043_MESH_D000080223_1.yaml` |
| `MESH:C016671` | Vasopressin | pitressin tannate | `DB00067_MESH_D006467_1.yaml` |
| `MESH:D015352` | Tear film insufficiency | Dry Eye Syndromes | `DB00091_MESH_D015352_1.yaml` |
| `MESH:D003218` | Condyloma acuminatum | Condylomata Acuminata | `DB00105_MESH_D003218_1.yaml` |
| `MESH:D015658` | Human immunodeficiency virus infection | HIV Infections | `DB00109_MESH_D015658_1.yaml` |
| `CL:0000584` | enterocytes | enterocyte | `DB00130_MESH_D012778_1.yaml` |
| `MESH:D002762` | Colecalciferol | Cholecalciferol | `DB00169_MESH_D006996_1.yaml` |
| `MESH:D001161` | Arteriosclerotic vascular disease | Arteriosclerosis | `DB00175_MESH_D001161_1.yaml` |
| `MESH:D006950` | Mixed hyperlipidemia | Hyperlipidemia, Familial Combined | `DB00175_MESH_D006950_1.yaml` |
| `MESH:D006973` | Hypertensive disorder | Hypertension | `DB00177_MESH_D006973_1.yaml` |
| `MESH:D010383` | Niacin deficiency | Pellagra | `DB00184_MESH_D010383_1.yaml` |
| `MESH:D002180` | Candidiasis of mouth | Candidiasis, Oral | `DB00196_MESH_D002180_1.yaml` |
| `MESH:D002181` | Candidal vulvovaginitis | Candidiasis, Vulvovaginal | `DB00196_MESH_D002181_1.yaml` |
| `GO:0140374` | viral budding from plasma membrane | antiviral innate immune response | `DB00198_MESH_D007251_1.yaml` |
| `UniProt:O76074` | phosphodisterase type 5 | cGMP-specific 3',5'-cyclic phosphodiesterase | `DB00203_MESH_D007172_1.yaml` |
| `MESH:D006152` | cGMP | Cyclic GMP | `DB00203_MESH_D007172_1.yaml` |
| `MESH:D011019` | Bacterial pneumonia | Pneumonia, Mycoplasma | `DB00207_MESH_D011019_1.yaml` |
| `MESH:D013203` | Infection due to Staphylococcus aureus | Staphylococcal Infections | `DB00207_MESH_D013203_1.yaml` |
| `MESH:D013290` | Streptococcus pyogenes infection | Streptococcal Infections | `DB00207_MESH_D013290_1.yaml` |
| `UniProt:Q72874` | Protease | HIV-1 retropepsin | `DB00220_MESH_D015658_1.yaml` |
| `MESH:D005076` | Eruption of skin | Exanthema | `DB00223_MESH_D005076_1.yaml` |
| `HP:0002621` | atherosclerotic plaque formation | Atherosclerosis | `DB00227_MESH_D001161_1.yaml` |
| `MESH:D008736` | Methylclothiazide | Methyclothiazide | `DB00232_MESH_D004487_1.yaml` |
| `MESH:C021139` | Anagrelid | anagrelide | `DB00261_MESH_D013920_1.yaml` |
| `MESH:D005910` | Glioma, malignant | Glioma | `DB00262_MESH_D005910_1.yaml` |
| `MESH:D003235` | Chlamydial conjunctivitis | Conjunctivitis, Inclusion | `DB00263_MESH_D003235_1.yaml` |
| `MESH:D011537` | Itching of skin | Pruritus | `DB00265_MESH_D011537_1.yaml` |
| `MESH:D012532` | Infestation by Sarcoptes scabiei var hominis | Scabies | `DB00265_MESH_D012532_1.yaml` |
| `MESH:D013923` | Thromboembolic disorder | Thromboembolism | `DB00266_MESH_D013923_1.yaml` |
| `MESH:D011018` | Pneumonia due to Streptococcus | Pneumonia, Pneumococcal | `DB00274_MESH_D011018_1.yaml` |
| `MESH:D006043` | Simple goiter | Goiter, Endemic | `DB00279_MESH_D006043_1.yaml` |
| `MESH:D002974` | clementine | Clemastine | `DB00283_MESH_D003233_1.yaml` |
| `MESH:D019584` | Menopausal flushing | Hot Flashes | `DB00286_MESH_D019584_1.yaml` |
| `MESH:D010412` | Malignant tumor of penis | Penile Neoplasms | `DB00290_MESH_D010412_1.yaml` |
| `UniProt:P44469` | Penicillin-binding proteins | Peptidoglycan D,D-transpeptidase MrdA | `DB00303_MESH_D018410_1.yaml` |
| `GO:0009252` | Bacterial Cell Wall Synthesis | peptidoglycan biosynthetic process | `DB00303_MESH_D018410_1.yaml` |
| `MESH:D059413` | Infectious disease of abdomen | Intraabdominal Infections | `DB00303_MESH_D059413_1.yaml` |
| `GO:0051823` | synaptic remodeling | regulation of synapse structural plasticity | `DB00313_MESH_D001714_2.yaml` |
| `reactome:R-HSA-211976` | sterol metabolism | Endogenous sterols | `DB00313_MESH_D004827_2.yaml` |
| `reactome:R-HSA-2162123` | cycloxygenaze pathways | Synthesis of Prostaglandins (PG) and Thromboxanes (TX) | `DB00316_MESH_D005334_1.yaml` |
| `MESH:D010612` | Sore throat symptom | Pharyngitis | `DB00318_MESH_D010612_1.yaml` |
| `MESH:D014390` | Tuberculosis of meninges | Tuberculosis, Meningeal | `DB00339_MESH_D014390_1.yaml` |
| `MESH:D020176` | Tyrosinemia type I | Tyrosinemias | `DB00348_MESH_D020176_1.yaml` |
| `reactome:R-HSA-5684996` | ERK1/ERK2 pathway | MAPK1/MAPK3 signaling | `DB00350_MESH_D000505_1.yaml` |
| `UniProt:P01148` | gonadotropin releasing hormone | Progonadoliberin-1 | `DB00351_MESH_D016889_1.yaml` |
| `MESH:D003234` | Pneumonia due to Mycoplasma pneumoniae | Conjunctivitis, Bacterial | `DB00365_MESH_D003234_1.yaml` |
| `MESH:D001480` | Extrapyramidal disease | Basal Ganglia Diseases | `DB00376_MESH_D001480_1.yaml` |
| `UniProt:P22303` | Cholinesterase | Acetylcholinesterase | `DB00382_MESH_D000544_1.yaml` |
| `MESH:D014839` | Allergens | Vomiting | `DB00420_MESH_D003233_1.yaml` |
| `MESH:D008721` | Methacarbamol | Methocarbamol | `DB00423_MESH_D009128_1.yaml` |
| `MESH:D012798` | Excessive salivation | Sialorrhea | `DB00424_MESH_D012798_1.yaml` |
| `MESH:D053159` | MESH:D053159 | Dysuria | `DB00424_MESH_D053159_1.yaml` |
| `MESH:D015210` | Articular gout | Arthritis, Gouty | `DB00437_MESH_D015210_1.yaml` |
| `MESH:D012282` | Disease caused by rickettsiae | Rickettsia Infections | `DB00446_MESH_D012282_1.yaml` |
| `MESH:D014648` | Venous varices | Varicose Veins | `DB00464_MESH_D014648_1.yaml` |
| `GO:0060047` | voltage-gated calcium channel activity | heart contraction | `DB00489_MESH_D001281_1.yaml` |
| `MESH:D011471` | Malignant tumor of prostate | Prostatic Neoplasms | `DB00499_MESH_D011471_1.yaml` |
| `MESH:D003457` | Infection by Cryptosporidium | Cryptosporidiosis | `DB00507_MESH_D003457_1.yaml` |
| `MESH:D004443` | Echinococcus granulosus infection of lung | Echinococcosis | `DB00518_MESH_D004443_1.yaml` |
| `MESH:D005936` | Beta(1,3)-D-glucan | Glucans | `DB00520_MESH_D058387_3.yaml` |
| `MESH:D011018` | Streptococcus pyogenes infection | Pneumonia, Pneumococcal | `DB00535_MESH_D011018_2.yaml` |
| `MESH:D012594` | Systemic sclerosis | Scleroderma, Localized | `DB00559_MESH_D012594_1.yaml` |
| `CHEBI:93775` | Methotrexate polyglutamate | 2-[[[4-[(2,4-diamino-6-pteridinyl)methyl-methylamino]phenyl]-oxomethyl]amino]pentanedioic acid | `DB00563_MESH_D001171_1.yaml` |
| `MESH:C538636` | Langerhans cell histiocytosis, disseminated | Familial Letterer-Siwe disease | `DB00570_MESH_C538636_2.yaml` |
| `MESH:D013736` | Malignant tumor of testis | Testicular Neoplasms | `DB00570_MESH_D013736_2.yaml` |
| `MESH:C064466` | Ulobetasol propionate | halobetasol | `DB00596_MESH_D003876_1.yaml` |
| `MESH:D009254` | naftili | Nafcillin | `DB00607_MESH_D013203_2.yaml` |
| `UniProt:P00519` | BCR/ABL | Tyrosine-protein kinase ABL1 | `DB00619_MESH_D015464_1.yaml` |
| `MESH:D015464` | CML (ph+) | Leukemia, Myelogenous, Chronic, BCR-ABL Positive | `DB00619_MESH_D015464_1.yaml` |
| `UniProt:P16234` | Pdgf | Platelet-derived growth factor receptor alpha | `DB00619_MESH_D034721_1.yaml` |
| `UniProt:P21728` | dopaminaergeinc receptors | Dopamine receptor D1 | `DB00623_MESH_D012559_1.yaml` |
| `MESH:D003456` | Undescended testicle | Cryptorchidism | `DB00624_MESH_D003456_1.yaml` |
| `MESH:D007713` | Klinefelter's syndrome, XXY | Klinefelter Syndrome | `DB00624_MESH_D007713_1.yaml` |
| `HP:0000822` | Blood pressure | Hypertension | `DB00629_MESH_D006973_1.yaml` |
| `MESH:D019386` | alendronic acid | Alendronate | `DB00630_MESH_D010001_1.yaml` |
| `MESH:D000562` | Amebic infection | Amebiasis | `DB00634_MESH_D000562_1.yaml` |
| `MESH:D011241` | prednisolone | Prednisone | `DB00635_MESH_D008224_1.yaml` |
| `MESH:D005443` | Flumetasone | Flumethasone | `DB00663_MESH_D003876_1.yaml` |
| `UniProt:P08913` | Tumor necrosis factor | Alpha-2A adrenergic receptor | `DB00668_MESH_D005902_3.yaml` |
| `MESH:D018856` | Ulcerative cystitis | Cystitis, Interstitial | `DB00686_MESH_D018856_1.yaml` |
| `MESH:D004915` | Erythroleukemia, FAB M6 | Leukemia, Erythroblastic, Acute | `DB00694_MESH_D004915_1.yaml` |
| `MESH:D009270` | Naltrexone | Naloxone | `DB00704_MESH_D000437_1.yaml` |
| `MESH:D009270` | Low Dose Naltrexone | Naloxone | `DB00704_MESH_D059350_1.yaml` |
| `MESH:D004938` | Malignant tumor of esophagus | Esophageal Neoplasms | `DB00707_MESH_D004938_1.yaml` |
| `MESH:D004604` | Lymphatic filariasis | Elephantiasis | `DB00711_MESH_D004604_1.yaml` |
| `MESH:D008118` | Infection by Loa loa | Loiasis | `DB00711_MESH_D008118_1.yaml` |
| `MESH:D009855` | Infection by Onchocerca volvulus | Onchocerciasis | `DB00711_MESH_D009855_1.yaml` |
| `MESH:D011657` | Eosinophilic asthma | Pulmonary Eosinophilia | `DB00711_MESH_D011657_1.yaml` |
| `MESH:C056244` | methylhomatropine | homatropine methylbromide | `DB00725_MESH_D003371_1.yaml` |
| `MESH:D013322` | Infection by Strongyloides | Strongyloidiasis | `DB00730_MESH_D013322_1.yaml` |
| `MESH:D014120` | Infection due to Toxocara | Toxocariasis | `DB00730_MESH_D014120_1.yaml` |
| `MESH:D014235` | Infection by larvae of Trichinella spiralis | Trichinellosis | `DB00730_MESH_D014235_1.yaml` |
| `GO:0006412` | Protein biosynthesis | translation | `DB00738_MESH_D014353_1.yaml` |
| `UniProt:O43612` | Orexin | Hypocretin neuropeptide precursor | `DB00745_MESH_D009290_1.yaml` |
| `GO:0001696` | Intestinal Secretions | gastric acid secretion | `DB00771_MESH_D004760_1.yaml` |
| `MESH:D020803` | Encephalitis due to Herpesvirus | Encephalitis, Herpes Simplex | `DB00787_MESH_D020803_1.yaml` |
| `MESH:D004025` | Dicycloverine | Dicyclomine | `DB00804_MESH_D043183_1.yaml` |
| `GO:0097366` | Bronchodilation | response to bronchodilator | `DB00816_MESH_D001249_1.yaml` |
| `MESH:D008610` | Levomenthol | Menthol | `DB00825_MESH_D001416_1.yaml` |
| `MESH:D005478` | Fludroxycortide | Flurandrenolone | `DB00846_MESH_D003876_1.yaml` |
| `MESH:D001254` | Astrocytoma, anaplastic | Astrocytoma | `DB00853_MESH_D001254_1.yaml` |
| `UniProt:P04083` | lipocortins | Annexin A1 | `DB00860_MESH_D012507_1.yaml` |
| `GO:0006954` | Inflammation signaling | inflammatory response | `DB00860_MESH_D012507_1.yaml` |
| `HP:0007906` | Intraocular pressure | Ocular hypertension | `DB00905_MESH_D005902_2.yaml` |
| `MESH:D018805` | Bacterial septicemia | Sepsis | `DB00916_MESH_D018805_1.yaml` |
| `UniProt:P23219` | COX | Prostaglandin G/H synthase 1 | `DB00945_MESH_D013927_1.yaml` |
| `MESH:D010051` | Malignant tumor of ovary | Ovarian Neoplasms | `DB00958_MESH_D010051_1.yaml` |
| `MESH:D004997` | Ethinylestradiol | Ethinyl Estradiol | `DB00977_MESH_D000152_1.yaml` |
| `CL:0001063` | tumor cells | neoplastic cell | `DB00987_MESH_D015470_1.yaml` |
| `MESH:D006918` | Hydroxycarbamide | Hydroxyurea | `DB01005_MESH_D000755_1.yaml` |
| `MESH:D014812` | Phytomenadione | Vitamin K | `DB01022_MESH_D006996_1.yaml` |
| `UniProt:P04585` | HIV-1 reverse transcriptase | Gag-Pol polyprotein | `DB01048_MESH_D015658_1.yaml` |
| `UniProt:P43702` | topoisomerases II, IV | DNA topoisomerase 4 subunit A | `DB01059_MESH_D004405_1.yaml` |
| `GO:0003746` | Translocation of EF-G | translation elongation factor activity | `DB01059_MESH_D004405_1.yaml` |
| `GO:0006412` | Bacterial Protein Synthesis | translation | `DB01059_MESH_D004405_1.yaml` |
| `CL:0000169` | Islet Cells | type B pancreatic cell | `DB01067_MESH_D006943_1.yaml` |
| `MESH:D014987` | Aptyalism | Xerostomia | `DB01085_MESH_D014987_1.yaml` |
| `MESH:D012552` | Infection by Schistosoma | Schistosomiasis | `DB01096_MESH_D012552_1.yaml` |
| `MESH:D005879` | Tourette’s Disorder | Tourette Syndrome | `DB01100_MESH_D005879_1.yaml` |
| `CHEBI:63528` | Thymidine monophosphate | dTMP(2-) | `DB01101_MESH_D013274_1.yaml` |
| `UniProt:P31645` | Solute carrier family 6 member 4, SLC6A4 | Sodium-dependent serotonin transporter | `DB01104_MESH_D000072861_1.yaml` |
| `MESH:D002179` | Candidiasis of skin | Candidiasis, Cutaneous | `DB01110_MESH_D002179_1.yaml` |
| `MESH:D046768` | Islet cell hyperplasia | Nesidioblastosis | `DB01119_MESH_D046768_1.yaml` |
| `taxonomy:4751` | Candida | Fungi | `DB01141_MESH_D058387_1.yaml` |
| `MESH:D002181` | Candidiasis of vagina | Candidiasis, Vulvovaginal | `DB01152_MESH_D002181_1.yaml` |
| `MESH:D016724` | Empyema of pleura | Empyema, Pleural | `DB01190_MESH_D016724_1.yaml` |
| `MESH:D011471` | Neoplasm of prostate | Prostatic Neoplasms | `DB01196_MESH_D011471_1.yaml` |
| `MESH:C107057` | rifapentine | fropenem | `DB01201_MESH_D014397_2.yaml` |
| `MESH:D011018` | Pneumonia due to Mycoplasma pneumoniae | Pneumonia, Pneumococcal | `DB01208_MESH_D011018_1.yaml` |
| `MESH:D000138` | Methanol poisoning | Acidosis | `DB01213_MESH_D000138_1.yaml` |
| `HP:0001649` | heart rate | Tachycardia | `DB01228_MESH_D018879_1.yaml` |
| `MESH:D000312` | Adrenogenital disorder | Adrenal Hyperplasia, Congenital | `DB01234_MESH_D000312_1.yaml` |
| `MESH:D011657` | Löffler's syndrome | Pulmonary Eosinophilia | `DB01234_MESH_D011657_1.yaml` |
| `MESH:D013716` | Epicondylitis | Tennis Elbow | `DB01234_MESH_D013716_1.yaml` |
| `MESH:D029503` | Congenital hypoplastic anemia | Anemia, Diamond-Blackfan | `DB01234_MESH_D029503_1.yaml` |
| `MESH:D001752` | Blastic phase chronic myeloid leukemia | Blast Crisis | `DB01254_MESH_D001752_1.yaml` |
| `MESH:D009181` | Fungal Infection | Mycoses | `DB01263_MESH_D009181_1.yaml` |
| `MESH:D006009` | Lysosomal alpha-1,4-glucosidase deficiency - infantile onset | Glycogen Storage Disease Type II | `DB01272_MESH_D006009_1.yaml` |
| `GO:0070471` | contractions | uterine smooth muscle contraction | `DB01282_MESH_D006473_1.yaml` |
| `reactome:R-HSA-2022377` | Renin-angiotensin-aldosterone system | Metabolism of Angiotensinogen to Angiotensins | `DB01349_MESH_D006973_1.yaml` |
| `UniProt:P23219` | COX Genes | Prostaglandin G/H synthase 1 | `DB01380_MESH_D007634_1.yaml` |
| `UniProt:P04083` | lipocortin-1 | Annexin A1 | `DB01380_MESH_D007634_1.yaml` |
| `GO:0050900` | Immune Cell Funciton | leukocyte migration | `DB01380_MESH_D007634_1.yaml` |
| `UniProt:P0AD65` | Penicillin-binding protein 2 (Streptococcus pneumoniae) | Peptidoglycan D,D-transpeptidase MrdA | `DB01413_MESH_D011018_1.yaml` |
| `UniProt:P0AD65` | Penicillin-binding protein 2 (Escherichia coli) | Peptidoglycan D,D-transpeptidase MrdA | `DB01413_MESH_D059413_1.yaml` |
| `GO:0007596` | Clotting Factor Synthesis | blood coagulation | `DB01418_MESH_D011655_1.yaml` |
| `MESH:D000242` | cAMP | Cyclic AMP | `DB01433_MESH_D009293_1.yaml` |
| `UniProt:P0AD65` | Penicillin-binding proteins | Peptidoglycan D,D-transpeptidase MrdA | `DB01598_MESH_D010538_1.yaml` |
| `MESH:D003586` | CMV infection | Cytomegalovirus Infections | `DB01610_MESH_D003586_1.yaml` |
| `MESH:D048909` | Diabetic complication | Diabetes Complications | `DB02383_MESH_D048909_1.yaml` |
| `UniProt:P13196` | Aminolevulinic acid synthase | 5-aminolevulinate synthase, non-specific, mitochondrial | `DB03404_MESH_D017118_1.yaml` |
| `MESH:D011162` | porpholobilinogen | Porphobilinogen | `DB03404_MESH_D017118_1.yaml` |
| `MESH:C009927` | Estrone sulphate | estropipate | `DB04574_MESH_D059268_1.yaml` |
| `MESH:C004315` | dantron | danthron | `DB04816_MESH_D003248_1.yaml` |
| `GO:0042438` | Melanogenesis | melanin biosynthetic process | `DB04931_MESH_D046351_1.yaml` |
| `CHEBI:18361` | Diphosphate(4−) | diphosphate(4-) | `DB05768_MESH_D007014_1.yaml` |
| `MESH:C071542` | incadronic acid | cimadronate | `DB06255_MESH_C562390_1.yaml` |
| `MESH:C106276` | Sitaxentan | sitaxsentan | `DB06268_MESH_D000081029_1.yaml` |
| `UniProt:Q91RS4` | Genome polyprotein | NS3 protease | `DB06290_MESH_D019698_1.yaml` |
| `MESH:D001752` | Blastic phase of chronic myeloid leukemia | Blast Crisis | `DB06616_MESH_D001752_1.yaml` |
| `MESH:C508735` | isavuconazonium | isavuconazole | `DB06636_MESH_D001228_1.yaml` |
| `MESH:D015761` | fampridine | 4-Aminopyridine | `DB06637_MESH_D009103_1.yaml` |
| `MESH:D000308` | Hypercortisolism | Adrenocortical Hyperfunction | `DB06663_MESH_D000308_1.yaml` |
| `CL:0000198` | Nociceptors | pain receptor cell | `DB06691_MESH_D004412_1.yaml` |
| `MESH:D002769` | Calculus in biliary tract | Cholelithiasis | `DB06777_MESH_D002769_1.yaml` |
| `MESH:D020301` | Spasm of cerebral arteries | Vasospasm, Intracranial | `DB08162_MESH_D020301_1.yaml` |
| `GO:0032640` | BiologicalProcess | tumor necrosis factor production | `DB08895_MESH_D001172_1.yaml` |
| `MESH:D004103` | ponatinib | Iodoquinol | `DB08901_MESH_D015464_1.yaml` |
| `UniProt:Q16236` | Nrf2 | Nuclear factor erythroid 2-related factor 2 | `DB08908_MESH_D009103_1.yaml` |
| `MESH:D014652` | Disorder of blood vessel | Vascular Diseases | `DB08941_MESH_D014652_1.yaml` |
| `UniProt:P0DTD1` | SARS-CoV-2 main protease | Replicase polyprotein 1ab | `DB09010_MESH_D000086382_1.yaml` |
| `MESH:C495502` | captodiame | captodiamine | `DB09014_MESH_D001008_1.yaml` |
| `MESH:C107241` | inorgainc pyrophosphate | diphosphoric acid | `DB09105_MESH_D007014_1.yaml` |
| `GO:0030282` | hydroxpatite crystal growth | bone mineralization | `DB09105_MESH_D007014_1.yaml` |
| `UniProt:P00734` | Thrombin | Prothrombin | `DB09109_MESH_D006467_1.yaml` |
| `CHEBI:18367` | phosphate(3−) | phosphate(3-) | `DB09146_MESH_D054559_1.yaml` |
| `MESH:D001786` | glycated hemoglobin | Blood Glucose | `DB09198_MESH_D003924_1.yaml` |
| `MESH:C010524` | Ubidecarenone | vitamin Q | `DB09270_MESH_D006333_1.yaml` |
| `MESH:C516303` | octinoxate | ethylhexyl methoxycinnamate | `DB09496_MESH_D008548_1.yaml` |
| `GO:0042060` | fibroblast proliferation | wound healing | `DB11100_MESH_D012628_1.yaml` |
| `MESH:C569381` | levomefolic acid | levomefolate calcium | `DB11256_MESH_D000152_1.yaml` |
| `MESH:D012676` | Sennosides | Senna Extract | `DB11365_MESH_D003248_1.yaml` |
| `MESH:D058766` | levofolinic acid | Levoleucovorin | `DB11596_MESH_D000749_1.yaml` |
| `MESH:C587014` | Efmoroctocog alfa | factor VIII-Fc fusion protein | `DB11607_MESH_D006467_1.yaml` |
| `MESH:D014355` | Infection by Trypanosoma cruzi | Chagas Disease | `DB11820_MESH_D014355_1.yaml` |
| `MESH:D011471` | Nonmetastatic prostate cancer | Prostatic Neoplasms | `DB11901_MESH_D011471_1.yaml` |
| `MESH:C107057` | thioacetazone | fropenem | `DB12829_MESH_D014397_1.yaml` |
| `HP:0002901` | An abnormally decreased calcium concentration in the blood | Hypocalcemia | `DB12865_MESH_D006962_1.yaml` |
| `MESH:D014841` | vonicog alfa | von Willebrand Factor | `DB12872_MESH_D014842_1.yaml` |
| `taxonomy:2` | Bateria | Bacteria | `DB13092_MESH_D000152_1.yaml` |
| `MESH:D000196` | Actinomycotic infection | Actinomycosis | `DB13092_MESH_D000196_1.yaml` |
| `taxonomy:1872` | Bacillus anthracis | Actinoplanes sp. ATCC 31351 | `DB13092_MESH_D000881_1.yaml` |
| `taxonomy:783` | Chlamydia trachomatis | Rickettsia rickettsii | `DB13092_MESH_D012373_1.yaml` |
| `MESH:D064412` | levosalbutamol | Levalbuterol | `DB13139_MESH_D001986_1.yaml` |
| `MESH:C536657` | TNF receptor-associated periodic fever syndrome (TRAPS) | Periodic fever, familial, autosomal dominant | `DB06168_MESH_C536657_1.yaml` |
| `reactome:R-HSA-2162123` | inflammatory prostaglandins production | Synthesis of Prostaglandins (PG) and Thromboxanes (TX) | `DB00313_MESH_D008881_1.yaml` |
| `MESH:D010547` | Persistent pulmonary hypertension of the newborn | Persistent Fetal Circulation Syndrome | `DB00797_MESH_D010547_1.yaml` |
| `UniProt:Q07817-1` | Bcl-xL | Isoform Bcl-X(L) of Bcl-2-like protein 1 | `DB00993_MESH_D001172_1.yaml` |
| `MESH:D015451` | Chronic lymphoid leukemia, disease | Leukemia, Lymphocytic, Chronic, B-Cell | `DB00240_MESH_D015451_1.yaml` |
| `reactome:R-HSA-2162123` | Prostaglandin Synthesis | Synthesis of Prostaglandins (PG) and Thromboxanes (TX) | `DB00547_MESH_D003876_1.yaml` |
| `UniProt:Q72874` | Human immunodeficiency virus type 1 protease | HIV-1 retropepsin | `DB00932_MESH_D015658_1.yaml` |
| `MESH:D001943` | Hormone receptor positive malignant neoplasm of breast | Breast Neoplasms | `DB01217_MESH_D001943_1.yaml` |
| `MESH:D020261` | Toxic effect of arsenic AND/OR its compounds | Arsenic Poisoning | `DB06782_MESH_D020261_1.yaml` |
| `GO:0045893` | gene transcription | positive regulation of DNA-templated transcription | `DB00313_MESH_D004827_4.yaml` |
| `CL:0000346` | dermal papillary cells | hair follicle dermal papilla cell | `DB00350_MESH_D000505_1.yaml` |
| `MESH:D001943` | Secondary malignant neoplasm of female breast | Breast Neoplasms | `DB00357_MESH_D001943_1.yaml` |
| `MESH:D001714` | Bipolar affective disorder, current episode depression | Bipolar Disorder | `DB00472_MESH_D001714_1.yaml` |
| `UniProt:P10721` | c-Kit | Mast/stem cell growth factor receptor Kit | `DB00619_MESH_D034721_1.yaml` |
| `MESH:D018270` | Infiltrating duct carcinoma of breast | Carcinoma, Ductal, Breast | `DB00675_MESH_D018270_1.yaml` |
| `UniProt:P75575` | 50S ribosomal protein L22 (Mycoplasma pneumoniae (strain ATCC 29342 / M129) | Large ribosomal subunit protein uL22 | `DB00954_MESH_D011019_1.yaml` |
| `MESH:D012713` | Transfusion reaction due to serum protein reaction | Serum Sickness | `DB01234_MESH_D012713_1.yaml` |
| `GO:0001951` | uptake of blood glucose | intestinal D-glucose absorption | `DB09198_MESH_D003924_1.yaml` |
| `UniProt:Q9UM73` | anaplastic lymphoma kinase (ALK) | ALK tyrosine kinase receptor | `DB12267_MESH_D002289_1.yaml` |
| `MESH:D005776` | Chronic non-neuropathic Gaucher's disease | Gaucher Disease | `DB00088_MESH_D005776_1.yaml` |
| `MESH:D053202` | Urge incontinence of urine | Urinary Incontinence, Urge | `DB00209_MESH_D053202_2.yaml` |
| `UniProt:Q92206` | Squalene monooxygenase (Candida albicans) | Squalene epoxidase ERG1 | `DB00525_MESH_D014008_1.yaml` |
| `MESH:D011019` | Pneumonia due to Mycoplasma pneumoniae | Pneumonia, Mycoplasma | `DB00685_MESH_D011019_1.yaml` |
| `MESH:D013313` | Posttraumatic stress disorder | Stress Disorders, Post-Traumatic | `DB00715_MESH_D013313_1.yaml` |
| `MESH:D007710` | Pneumonia due to Klebsiella pneumoniae | Klebsiella Infections | `DB00766_MESH_D007710_1.yaml` |
| `MESH:D000532` | Anoxia due to high altitude | Altitude Sickness | `DB00819_MESH_D000532_1.yaml` |
| `MESH:D016868` | Bacterial infection due to Serratia | Serratia Infections | `DB00948_MESH_D016868_1.yaml` |
| `MESH:D006152` | Cyclic guanosine 3',5'-monophosphate (cGMP) | Cyclic GMP | `DB01020_MESH_D000787_1.yaml` |
| `UniProt:P72525` | Topoisomeraze 4 | DNA topoisomerase 4 subunit A | `DB01155_MESH_D018410_1.yaml` |
| `UniProt:Q68HC5` | Lanosterol 14-alpha-demethylase | sterol 14alpha-demethylase | `DB01167_MESH_D006660_1.yaml` |
| `UniProt:Q2G0P0` | 50S ribosomal protein L1 Staphylococcus aureus (strain NCTC 8325) | Large ribosomal subunit protein uL1 | `DB01190_MESH_D011023_1.yaml` |
| `UniProt:P10613` | sterol 14a-demethylase | Lanosterol 14-alpha demethylase | `DB01263_MESH_D009181_1.yaml` |
| `MESH:D046150` | Laron-type isolated somatotropin defect | Laron Syndrome | `DB01277_MESH_D046150_2.yaml` |
| `GO:1990768` | gastric acid secretion | gastric mucosal blood circulation | `DB08900_MESH_D012778_1.yaml` |
| `GO:0001696` | gastric mucosal blood circulation | gastric acid secretion | `DB08900_MESH_D012778_1.yaml` |
| `UniProt:Q9HGT2` | Cytosolic leucyl-tRNA synthetase | leucine--tRNA ligase | `DB09041_MESH_D014009_1.yaml` |
| `UniProt:P0C1U9` | Topoisomeraze 4 | DNA topoisomerase 4 subunit A | `DB09335_MESH_D011023_1.yaml` |
| `MESH:D001932` | Primary malignant neoplasm of brain | Brain Neoplasms | `DB11812_MESH_D001932_1.yaml` |
| `MESH:D008224` | Follicular non-Hodgkin's lymphoma | Lymphoma, Follicular | `DB00078_MESH_D008224_1.yaml` |
| `MESH:D014806` | Cobalamin deficiency | Vitamin B 12 Deficiency | `DB00115_MESH_D014806_1.yaml` |
| `MESH:D001932` | Malignant neoplasm of brain | Brain Neoplasms | `DB00262_MESH_D001932_1.yaml` |
| `UniProt:Q9UKV0` | histone deactylase (HDAC) | Histone deacetylase 9 | `DB00313_MESH_D004827_1.yaml` |
| `MESH:D017449` | allergic skin disorders | Dermatitis, Allergic Contact | `DB00342_MESH_D017449_1.yaml` |
| `MESH:D012141` | Upper respiratory infection | Respiratory Tract Infections | `DB00417_MESH_D012141_1.yaml` |
| `MESH:D014552` | Bacterial urinary infection | Urinary Tract Infections | `DB00438_MESH_D014552_1.yaml` |
| `MESH:D000071074` | Sepsis of the newborn | Neonatal Sepsis | `DB00512_MESH_D000071074_1.yaml` |
| `MESH:D013274` | Malignant tumor of stomach | Stomach Neoplasms | `DB00544_MESH_D013274_1.yaml` |
| `MESH:D008175` | Malignant tumor of lung | Lung Neoplasms | `DB00563_MESH_D008175_1.yaml` |
| `MESH:D034721` | Systemic mast cell disease | Mastocytosis, Systemic | `DB00619_MESH_D034721_1.yaml` |
| `MESH:D000749` | Megaloblastic anemia (Methotrexate Treatment) | Anemia, Megaloblastic | `DB00650_MESH_D000749_1.yaml` |
| `MESH:D007948` | Acute monocytic/monoblastic leukemia | Leukemia, Monocytic, Acute | `DB00694_MESH_D007948_1.yaml` |
| `UniProt:Q72547` | HIV-1 reverse transcriptase | Reverse transcriptase/RNaseH | `DB00709_MESH_D015658_1.yaml` |
| `MESH:D000242` | Cyclic adenosine monophosphate (cAMP) | Cyclic AMP | `DB00816_MESH_D001249_1.yaml` |
| `MESH:D007635` | Herpes simplex dendritic keratitis | Keratitis, Dendritic | `DB01004_MESH_D007635_1.yaml` |
| `UniProt:P11388` | DNA gyrase | DNA topoisomerase 2-alpha | `DB01137_MESH_D011704_1.yaml` |
| `MESH:D009140` | Disorder of musculoskeletal system | Musculoskeletal Diseases | `DB01234_MESH_D009140_1.yaml` |
| `MESH:D004756` | Infection due to Enterobacteriaceae | Enterobacteriaceae Infections | `DB01326_MESH_D004756_1.yaml` |
| `MESH:D014812` | Reduced Vitamin k2 (vkH2) | Vitamin K | `DB01418_MESH_D011655_1.yaml` |
| `UniProt:Q9UBN7` | Histone deacetylase 6 | Protein deacetylase HDAC6 | `DB02546_MESH_D016410_1.yaml` |
| `MESH:D018088` | Drug resistant tuberculosis | Tuberculosis, Multidrug-Resistant | `DB08903_MESH_D018088_1.yaml` |
| `GO:0008283` | proliferation of cells | cell population proliferation | `DB12267_MESH_D002289_1.yaml` |
| `UniProt:Q9Z9A3` | 50S ribosomal protein L1 (Chlamydia pneumoniae) | Large ribosomal subunit protein uL1 | `DB00207_MESH_D061387_1.yaml` |
| `UniProt:Q5F5S1` | 30S ribosomal protein S12 (Neisseria gonorrhoeae) | Small ribosomal subunit protein uS12 | `DB00919_MESH_D006069_1.yaml` |
| `UniProt:P0C0D5` | 50S ribosomal protein L4 (Streptococcus sp) | Large ribosomal subunit protein uL4 | `DB00954_MESH_D011018_1.yaml` |
| `UniProt:P0C0D5` | 50S ribosomal protein L4 (Streptococcus pyogenes) | Large ribosomal subunit protein uL4 | `DB00954_MESH_D013290_1.yaml` |
| `UniProt:P66096` | 50S ribosomal protein L1 Streptococcus pneumoniae | Large ribosomal subunit protein uL1 | `DB01190_MESH_D011018_1.yaml` |
| `UniProt:Q9A1X4` | 50S ribosomal protein L3 (Streptococcus pyogenes) | Large ribosomal subunit protein uL3 | `DB01256_MESH_D007169_1.yaml` |
| `UniProt:Q8XET6` | 50S ribosomal protein L16 (Salmonella typhi) | Large ribosomal subunit protein uL16 | `DB07565_MESH_D012480_1.yaml` |
| `GO:0036037` | Cytotoxic T-Cell activity | CD8-positive, alpha-beta T cell activation | `DB11945_MESH_D015266_1.yaml` |
| `MESH:C028815` | Calcitonin (salmon synthetic) | salmon calcitonin | `DB00017_MESH_D010001_1.yaml` |
| `MESH:D013964` | Thyroid cancer (Diagnostic) | Thyroid Neoplasms | `DB00024_MESH_D013964_1.yaml` |
| `GO:0008283` | cellular proliferation | cell population proliferation | `DB00059_MESH_D054198_1.yaml` |
| `MESH:D008059` | Mucopolysaccharidosis, MPS-I | Mucopolysaccharidosis I | `DB00090_MESH_D008059_2.yaml` |
| `reactome:R-HSA-194138` | Signaling by Vascular Epithelial Growth Factors (VEGF) | Signaling by VEGF | `DB00112_MESH_D005909_1.yaml` |
| `UniProt:O43451` | Maltase-glucoamylase, intestinal | Maltase-glucoamylase | `DB00284_MESH_D003924_1.yaml` |
| `MESH:D006258` | Malignant tumor of head and/or neck | Head and Neck Neoplasms | `DB00290_MESH_D006258_1.yaml` |
| `reactome:R-HSA-556833` | glycerolipids metabolism | Metabolism of lipids | `DB00313_MESH_D004827_3.yaml` |
| `GO:0023041` | Neuronal activation | neuronal signal transduction | `DB00344_MESH_D003865_1.yaml` |
| `GO:0007268` | corticothalamic transmission | chemical synaptic transmission | `DB00347_MESH_D004832_1.yaml` |
| `GO:0045907` | Vasoconstriction | positive regulation of vasoconstriction | `DB00350_MESH_D006973_1.yaml` |
| `MESH:D014009` | Onychomycosis due to dermatophyte | Onychomycosis | `DB00400_MESH_D014009_1.yaml` |
| `GO:0051610` | Neuronal serotonin reuptake | serotonin uptake | `DB00476_MESH_D003865_1.yaml` |
| `GO:0006351` | gene transcription | DNA-templated transcription | `DB00499_MESH_D011471_1.yaml` |
| `MESH:D001943` | Carcinoma of breast | Breast Neoplasms | `DB00531_MESH_D001943_1.yaml` |
| `MESH:D012131` | Decreased respiratory function | Respiratory Insufficiency | `DB00561_MESH_D012131_1.yaml` |
| `MESH:D004828` | Simple partial seizure | Epilepsies, Partial | `DB00564_MESH_D004828_1.yaml` |
| `MESH:D004942` | Peptic reflux disease | Esophagitis, Peptic | `DB00585_MESH_D004942_1.yaml` |
| `MESH:D003928` | Diabetic renal disease | Diabetic Nephropathies | `DB00678_MESH_D003928_1.yaml` |
| `GO:0007596` | Coagulation factor Synthesis | blood coagulation | `DB00682_MESH_D011655_1.yaml` |
| `MESH:D013203` | Staphylococcal infectious disease | Staphylococcal Infections | `DB00713_MESH_D013203_1.yaml` |
| `MESH:D003233` | seasonal allergic conjunctivitis | Conjunctivitis, Allergic | `DB00748_MESH_D003233_1.yaml` |
| `MESH:D014245` | Infection by Trichomonas | Trichomonas Infections | `DB00911_MESH_D014245_1.yaml` |
| `MESH:C029371` | hydroxyethyl oxamic acid | hydroxyethyloxamic acid | `DB00916_MESH_D018805_1.yaml` |
| `MESH:D016055` | Retention of urine | Urinary Retention | `DB01019_MESH_D016055_1.yaml` |
| `MESH:D001932` | Neoplasm of brain | Brain Neoplasms | `DB01206_MESH_D001932_1.yaml` |
| `MESH:D000242` | cyclic adenosine monophosphate | Cyclic AMP | `DB01210_MESH_D009798_3.yaml` |
| `UniProt:P44350` | 50S Ribosomal protein l-10 | Large ribosomal subunit protein uL10 | `DB01211_MESH_D015523_1.yaml` |
| `MESH:D000309` | Adrenal cortical hypofunction | Adrenal Insufficiency | `DB01234_MESH_D000309_1.yaml` |
| `MESH:D005128` | Disorder of eye | Eye Diseases | `DB01234_MESH_D005128_1.yaml` |
| `MESH:D007819` | Edema of larynx | Laryngeal Edema | `DB01234_MESH_D007819_1.yaml` |
| `MESH:D012871` | Disorder of skin | Skin Diseases | `DB01234_MESH_D012871_1.yaml` |
| `MESH:D016532` | Mucopolysaccharidosis, MPS-II | Mucopolysaccharidosis II | `DB01271_MESH_D016532_1.yaml` |
| `MESH:D008171` | Disorder of lung | Lung Diseases | `DB01291_MESH_D008171_1.yaml` |
| `MESH:D011008` | Pneumococcal infectious disease | Pneumococcal Infections | `DB01627_MESH_D011008_1.yaml` |
| `MESH:D013290` | Streptococcal infectious disease | Streptococcal Infections | `DB01627_MESH_D013290_1.yaml` |
| `MESH:D012509` | Sarcoma of soft tissue | Sarcoma | `DB06043_MESH_D012509_1.yaml` |
| `MESH:D056806` | Disorder of the urea cycle metabolism | Urea Cycle Disorders, Inborn | `DB08909_MESH_D056806_1.yaml` |
| `UniProt:P23560` | brain-derived neurotrophic factor (BDNF) | Neurotrophic factor BDNF precursor form | `DB09014_MESH_D001008_1.yaml` |
| `MESH:D007897` | American mucocutaneous leishmaniasis | Leishmaniasis, Mucocutaneous | `DB09031_MESH_D007897_1.yaml` |
| `GO:0022851` | GABA-A receptor activity | GABA-gated chloride ion channel activity | `DB09166_MESH_D001008_1.yaml` |
| `MESH:D010402` | Procaine benzylpenicillin | Penicillin G Procaine | `DB09320_MESH_C536773_1.yaml` |
| `GO:0019370` | leukotriene biosysntesis | leukotriene biosynthetic process | `DB14649_MESH_D009101_1.yaml` |
| `CHEBI:28648` | β-D-GalNAc-(1→4)-[α-Neu5Ac-(2→8)-α-Neu5Ac-(2→3)]-β-D-Gal-(1→4)-β-D-Glc-(1↔1')-Cer | beta-D-GalNAc-(1->4)-[alpha-Neu5Ac-(2->8)-alpha-Neu5Ac-(2->3)]-beta-D-Gal-(1->4)-beta-D-Glc-(1<->1')-Cer | `DB09077_MESH_D009447_1.yaml` |
| `UniProt:O14975` | microsomal long-chain fatty acyl-CoA synthetase | Long-chain fatty acid transport protein 2 | `DB00313_MESH_D008881_1.yaml` |
| `MESH:D006475` | Hemorrhagic disease of the newborn due to vitamin K deficiency | Vitamin K Deficiency Bleeding | `DB12148_MESH_D006475_1.yaml` |
| `GO:0004697` | protein kinase C activity | diacylglycerol-dependent serine/threonine kinase activity | `DB00002_MESH_D003110_1.yaml` |
| `MESH:D016410` | Primary cutaneous T-cell lymphoma | Lymphoma, T-Cell, Cutaneous | `DB00004_MESH_D016410_1.yaml` |
| `MESH:C554498` | Kaposi's sarcoma associated with AIDS | AIDS-related Kaposi sarcoma | `DB00105_MESH_C554498_1.yaml` |
| `UniProt:Q96885` | RNA-directed RNA polymerase (Hepatitis C virus) | RNA dependent RNA polymerase | `DB00811_MESH_D018357_1.yaml` |
| `UniProt:Q5NFG2` | 30S ribosomal protein S9 | Small ribosomal subunit protein uS9 | `DB01017_MESH_D014406_1.yaml` |
| `GO:0032869` | tissue sensitivity to insulin | cellular response to insulin stimulus | `DB09198_MESH_D003924_1.yaml` |
| `HP:0003141` | Increased LDL cholesterol concentration | Elevated circulating LDL-C concentration | `DB09302_MESH_D006937_1.yaml` |
| `MESH:C536392` | Acquired factor VIII deficiency disease | Factor 8 deficiency, acquired | `DB11606_MESH_C536392_1.yaml` |
| `UniProt:P08908` | 5-HT1a receptor (serotonin 1A) | 5-hydroxytryptamine receptor 1A | `DB12184_MESH_D003865_1.yaml` |
| `MESH:C536227` | Cyclical neutropenia | Cyclic neutropenia | `DB00099_MESH_C536227_1.yaml` |
| `MESH:D019694` | Chronic type B viral hepatitis | Hepatitis B, Chronic | `DB00105_MESH_D019694_1.yaml` |
| `MESH:D000249` | adenosine phosphate | Adenosine Monophosphate | `DB00131_MESH_D003550_1.yaml` |
| `MESH:D013832` | Thiamin deficiency | Thiamine Deficiency | `DB00152_MESH_D013832_1.yaml` |
| `MESH:D004831` | Myoclonic seizure | Epilepsies, Myoclonic | `DB00186_MESH_D004831_1.yaml` |
| `MESH:D004832` | Absence seizure | Epilepsy, Absence | `DB00186_MESH_D004832_1.yaml` |
| `MESH:C536777` | Disseminated candidiasis | Systemic candidiasis | `DB00196_MESH_C536777_1.yaml` |
| `taxonomy:2104` | Mycoplasma pneumoniae | Mycoplasmoides pneumoniae | `DB00199_MESH_D011019_1.yaml` |
| `MESH:D007172` | Erectile Disfunction | Erectile Dysfunction | `DB00203_MESH_D007172_1.yaml` |
| `MESH:D011618` | Psychotic disorder | Psychotic Disorders | `DB00206_MESH_D011618_1.yaml` |
| `taxonomy:730` | Haemophilus ducreyi | [Haemophilus] ducreyi | `DB00207_MESH_D002602_1.yaml` |
| `MESH:D009410` | neural degeneration | Nerve Degeneration | `DB00313_MESH_D004827_1.yaml` |
| `MESH:D020773` | Headache disorder | Headache Disorders | `DB00318_MESH_D020773_1.yaml` |
| `taxonomy:613` | Serratia sp. | Serratia <enterobacteria> | `DB00319_MESH_D016868_1.yaml` |
| `reactome:R-HSA-390651` | Dopamine receptor | Dopamine receptors | `DB00391_MESH_D012559_1.yaml` |
| `MESH:D009298` | Nasal polyp | Nasal Polyps | `DB00394_MESH_D009298_1.yaml` |
| `MESH:D001943` | Breast Neoplasm | Breast Neoplasms | `DB00445_MESH_D001943_1.yaml` |
| `UniProt:P0A7S3` | 30S Ribosomal Subunit | Small ribosomal subunit protein uS12 | `DB00479_MESH_D016920_1.yaml` |
| `MESH:C100237` | octatropine methylbromide | octotropine methylbromide | `DB00517_MESH_D010437_1.yaml` |
| `UniProt:P0A7J3` | 50S Ribosomal Subunit | Large ribosomal subunit protein uL10 | `DB00618_MESH_D000073605_1.yaml` |
| `MESH:D010907` | hypophyseal hormones | Pituitary Hormones | `DB00623_MESH_D012559_1.yaml` |
| `taxonomy:83558` | Chlamydial pneumoniae | Chlamydia pneumoniae | `DB00685_MESH_D061387_1.yaml` |
| `MESH:D015473` | Acute promyelocytic leukemia, FAB M3 | Leukemia, Promyelocytic, Acute | `DB00694_MESH_D015473_1.yaml` |
| `MESH:D004927` | Infection due to Escherichia coli | Escherichia coli Infections | `DB00766_MESH_D004927_1.yaml` |
| `MESH:D018633` | Congenital atresia of the pulmonary valve | Pulmonary Atresia | `DB00770_MESH_D018633_1.yaml` |
| `MESH:D002561` | Cerebrovascular disease | Cerebrovascular Disorders | `DB00797_MESH_D002561_1.yaml` |
| `taxonomy:5820` | Plasmodium sp. | Plasmodium <genus> | `DB00908_MESH_D008288_1.yaml` |
| `MESH:D015508` | Nasal Congestion | Nasal Obstruction | `DB00935_MESH_D015508_1.yaml` |
| `CHEBI:141146` | α-methylnoradrenaline | alpha-methylnoradrenaline | `DB00968_MESH_D006973_1.yaml` |
| `MESH:D015658` | HIV infection | HIV Infections | `DB01048_MESH_D015658_1.yaml` |
| `MESH:D000080362` | Stargardt's disease | Stargardt Disease | `DB01057_MESH_D000080362_1.yaml` |
| `GO:0014046` | Dopamine Release | dopamine secretion | `DB01100_MESH_D005879_1.yaml` |
| `MESH:D015479` | Acute myelomonocytic leukemia, FAB M4 | Leukemia, Myelomonocytic, Acute | `DB01169_MESH_D015479_1.yaml` |
| `UniProt:P30559` | oxytocin receptors | Oxytocin receptor | `DB01282_MESH_D006473_1.yaml` |
| `MESH:D061267` | insulin detemir | Insulin Aspart | `DB01306_MESH_D003920_1.yaml` |
| `MESH:D007710` | Klebsiella cystitis | Klebsiella Infections | `DB01332_MESH_D007710_1.yaml` |
| `GO:0009039` | Urease activityS | urease activity | `DB05197_MESH_D013276_1.yaml` |
| `MESH:D004828` | Partial seizure | Epilepsies, Partial | `DB05541_MESH_D004828_1.yaml` |
| `UniProt:Q9H8P0` | Polyprenol reductase | Polyprenal reductase | `DB05812_MESH_D011471_6.yaml` |
| `GO:0006954` | inflammatory signalling | inflammatory response | `DB06786_MESH_D012871_1.yaml` |
| `MESH:D012480` | Salmonella infection | Salmonella Infections | `DB07565_MESH_D012480_1.yaml` |
| `UniProt:P0A298` | 50S ribosomal subunit | Large ribosomal subunit protein uL10 | `DB07565_MESH_D014435_1.yaml` |
| `MESH:D017439` | Hypertrophic scar | Cicatrix, Hypertrophic | `DB07615_MESH_D017439_1.yaml` |
| `CHEBI:64645` | amyloid-β | amyloid-beta | `DB08842_MESH_D000544_1.yaml` |
| `UniProt:Q72547` | Reverse transcriptase/RNaseH (Human immunodeficiency virus 1) | Reverse transcriptase/RNaseH | `DB08864_MESH_D015658_1.yaml` |
| `MESH:D009196` | Myeloproliferative disorder | Myeloproliferative Disorders | `DB08877_MESH_D009196_1.yaml` |
| `MESH:D001008` | Anxiety disorder | Anxiety Disorders | `DB09014_MESH_D001008_1.yaml` |
| `taxonomy:5658` | Leishmania sp | Leishmania <genus> | `DB09031_MESH_D007897_1.yaml` |
| `MESH:D008258` | Waldenström macroglobulinemia | Waldenstrom Macroglobulinemia | `DB09053_MESH_D008258_1.yaml` |
| `UniProt:Q9HB55` | cytochrome P450 3A (CYP3A) isoforms | Cytochrome P450 3A43 | `DB09065_MESH_D015658_1.yaml` |
| `MESH:D009290` | Cataplexy and narcolepsy | Narcolepsy | `DB09072_MESH_D009290_1.yaml` |
| `UniProt:P14867` | GABA-A receptor alpha 1 | Gamma-aminobutyric acid receptor subunit alpha-1 | `DB09166_MESH_D001008_1.yaml` |
| `MESH:C567691` | Hereditary factor XIII A subunit deficiency | Factor Xiii, A Subunit, Deficiency Of | `DB09310_MESH_C567691_1.yaml` |
| `MESH:C026329` | Potassium hydrogencarbonate | potassium bicarbonate | `DB11098_MESH_D004415_1.yaml` |
| `UBERON:0000451` | Prefrontal complex | prefrontal cortex | `DB12710_MESH_D012559_1.yaml` |
| `reactome:R-HSA-390651` | Dopamine pathway | Dopamine receptors | `DB13676_MESH_D012559_1.yaml` |
| `MESH:C004648` | Testosterone enantate | testosterone enanthate | `DB13944_MESH_D005058_1.yaml` |
| `MESH:D009101` | Multiple meyloma | Multiple Myeloma | `DB14649_MESH_D009101_1.yaml` |
| `MESH:C571912` | Inhalational anthrax | Inhalation anthrax | `DBDB08902_MESH_C571912_1.yaml` |
| `MESH:D003233` | Allergic conjuctivitis | Conjunctivitis, Allergic | `MESH_C106301_MESH_D003233_1.yaml` |
| `MESH:D053098` | Familial x-linked hypophosphatemic vitamin D refractory rickets | Familial Hypophosphatemic Rickets | `DB00153_MESH_D053098_1.yaml` |
| `MESH:D016403` | Diffuse non-Hodgkin's lymphoma, large cell | Lymphoma, Large B-Cell, Diffuse | `DB00262_MESH_D016403_1.yaml` |
| `UniProt:Q5UBX3` | Tubulin beta chain Trichophyton rubrum (Athlete's foot fungus) | Tubulin beta chain | `DB00400_MESH_D014006_1.yaml` |
| `GO:0070474` | uterine smooth muscle relaxation | positive regulation of uterine smooth muscle contraction | `DB01282_MESH_D006473_2.yaml` |
| `MESH:D015470` | Acute myeloid leukemia, disease | Leukemia, Myeloid, Acute | `DB00041_MESH_D015470_1.yaml` |
| `MESH:D003550` | Cystic fibrosis of the lung | Cystic Fibrosis | `DB00131_MESH_D003550_1.yaml` |
| `MESH:D006952` | Familial type 3 hyperlipoproteinemia | Hyperlipoproteinemia Type III | `DB00175_MESH_D006952_1.yaml` |
| `UniProt:P05412` | Transcription factor AP-1 | Transcription factor Jun | `DB00257_MESH_D000152_2.yaml` |
| `MESH:D014552` | Urinary tract infectious disease | Urinary Tract Infections | `DB00263_MESH_D014552_1.yaml` |
| `UBERON:0014892` | skeletal muscle organ | skeletal muscle organ, vertebrate | `DB00395_MESH_D009128_1.yaml` |
| `MESH:D017192` | Bacterial infection of skin | Skin Diseases, Bacterial | `DB00446_MESH_D017192_1.yaml` |
| `UniProt:P08546` | viral DNA Polymerase | DNA polymerase catalytic subunit | `DB00529_MESH_D017726_1.yaml` |

_…and 224 more (see the JSON report)._
