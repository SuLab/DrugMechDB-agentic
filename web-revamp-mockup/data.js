/* Sample DMDB data for the mockup. Structure mirrors real records
   (nodes: id/label/name · links: key/source/target · graph metadata
   · references · optional per-edge evidence). Browse index is a compact
   per-record summary — the kind of small JSON the real site would ship. */

window.DMDB_RECORD = {
  graph: {
    _id: "DB00570_MESH_D013736_2",
    drug: "Vinblastine",
    disease: "Malignant tumor of testis",
    drugbank: "DB00570",
    drug_mesh: "MESH:D014747",
    disease_mesh: "MESH:D013736",
    summary: "Vinblastine binds tubulin and inhibits microtubule assembly, arresting mitosis in rapidly dividing testicular tumor cells and thereby reducing tumor cell proliferation."
  },
  nodes: [
    { id: "MESH:D014747", label: "Drug",              name: "Vinblastine" },
    { id: "UniProt:Q71U36", label: "Protein",         name: "Tubulin alpha-1A chain" },
    { id: "UniProt:P07437", label: "Protein",         name: "Tubulin beta chain" },
    { id: "UniProt:Q9UJT1", label: "Protein",         name: "Tubulin delta chain" },
    { id: "UniProt:P23258", label: "Protein",         name: "Tubulin gamma-1 chain" },
    { id: "UniProt:Q9UJT0", label: "Protein",         name: "Tubulin epsilon chain" },
    { id: "GO:1902850", label: "BiologicalProcess",   name: "Microtubule cytoskeleton organization in mitosis" },
    { id: "GO:0140014", label: "BiologicalProcess",   name: "Mitotic nuclear division" },
    { id: "GO:0008283", label: "BiologicalProcess",   name: "Cell population proliferation" },
    { id: "MESH:D013736", label: "Disease",           name: "Malignant tumor of testis" }
  ],
  /* Per-edge `evidence` is an array of EvidenceItem objects, mirroring the real
     PathEdge.evidence schema. Each item carries the curator fields (reference,
     snippet, supports, evidence_source, explanation, source_tier) AND a joined
     `paper` credential block (title/authors/journal/year/doi/pmcid/license) sourced
     from references_cache frontmatter. DrugBank-MoA evidence has no `paper` block. */
  links: [
    { key: "decreases activity of", source: "MESH:D014747", target: "UniProt:Q71U36",
      evidence: [
        { reference: "DB00570", source_type: "drugbank", supports: "SUPPORT", evidence_source: "OTHER",
          snippet: "Vinblastine binds to tubulin dimers, inhibiting assembly of microtubules.",
          explanation: "DrugBank Mechanism-of-Action text asserts the established target interaction.",
          paper: null },
        { reference: "PMID:12042791", source_type: "pubmed", supports: "SUPPORT", evidence_source: "IN_VITRO",
          source_tier: "ABSTRACT",
          snippet: "Vinblastine binds β-tubulin at the vinca domain and blocks microtubule polymerization in vitro.",
          paper: { title: "Vinca alkaloid binding to the colchicine domain of tubulin", authors: ["Gigant B","Wang C","Ravelli RBG"], journal: "Nature", year: "2005", doi: "10.1038/nature03566", pmcid: "PMC1351096", license: "CC BY" } }
      ] },
    { key: "decreases activity of", source: "MESH:D014747", target: "UniProt:P07437",
      evidence: [
        { reference: "PMID:18322465", source_type: "pubmed", supports: "SUPPORT", evidence_source: "IN_VITRO",
          source_tier: "ABSTRACT",
          snippet: "By binding β-tubulin, vinblastine disrupts microtubule dynamics and blocks mitotic spindle formation.",
          paper: { title: "Microtubule-targeting agents and mitotic arrest", authors: ["Jordan MA","Wilson L"], journal: "Nat Rev Cancer", year: "2004", doi: "10.1038/nrc1317", pmcid: null, license: "publisher (closed)" } }
      ] },
    { key: "decreases activity of", source: "MESH:D014747", target: "UniProt:Q9UJT1" },
    { key: "decreases activity of", source: "MESH:D014747", target: "UniProt:P23258" },
    { key: "decreases activity of", source: "MESH:D014747", target: "UniProt:Q9UJT0" },
    { key: "part of", source: "UniProt:Q71U36", target: "GO:1902850",
      evidence: [
        { reference: "PMID:18322465", source_type: "pubmed", supports: "PARTIAL", evidence_source: "IN_VITRO",
          source_tier: "ABSTRACT",
          snippet: "Alpha-tubulin is a core structural component of the mitotic spindle microtubules.",
          explanation: "Supports α-tubulin's structural role in the spindle, but speaks to the spindle generally rather than this exact pathway term.",
          paper: { title: "Microtubule-targeting agents and mitotic arrest", authors: ["Jordan MA","Wilson L"], journal: "Nat Rev Cancer", year: "2004", doi: "10.1038/nrc1317", pmcid: null, license: "publisher (closed)" } }
      ] },
    { key: "part of", source: "UniProt:P07437", target: "GO:1902850" },
    { key: "part of", source: "UniProt:Q9UJT1", target: "GO:1902850" },
    { key: "part of", source: "UniProt:P23258", target: "GO:1902850" },
    { key: "part of", source: "UniProt:Q9UJT0", target: "GO:1902850" },
    { key: "positively regulates", source: "GO:1902850", target: "GO:0140014",
      evidence: [
        { reference: "PMID:20071333", source_type: "pubmed", supports: "SUPPORT", evidence_source: "MODEL_ORGANISM",
          source_tier: "FULL_TEXT",
          snippet: "proper microtubule organization is required for progression through mitotic nuclear division",
          explanation: "Snippet taken from the open-access full text (the abstract was insufficient); the full-text body is stripped before the PR.",
          paper: { title: "Spindle microtubule organization governs mitotic progression in vivo", authors: ["Compton DA"], journal: "J Cell Biol", year: "2010", doi: "10.1083/jcb.201001102", pmcid: "PMC2867311", license: "CC BY-NC-SA" } }
      ] },
    { key: "positively regulates", source: "GO:0140014", target: "GO:0008283" },
    { key: "positively correlated with", source: "GO:0008283", target: "MESH:D013736",
      evidence: [
        { reference: "PMID:21376230", source_type: "pubmed", supports: "NO_EVIDENCE", evidence_source: "HUMAN_CLINICAL",
          source_tier: "ABSTRACT",
          snippet: "Uncontrolled cell proliferation is a hallmark driving testicular tumor growth.",
          explanation: "Closest paper found, but it does not establish the proliferation→this-neoplasm link specifically — edge retained and flagged for review (held out of the ai_curated profile).",
          paper: { title: "Hallmarks of cancer: the next generation", authors: ["Hanahan D","Weinberg RA"], journal: "Cell", year: "2011", doi: "10.1016/j.cell.2011.02.013", pmcid: null, license: "publisher (closed)" } }
      ] }
  ],
  references: [
    { url: "https://go.drugbank.com/drugs/DB00570#BE0001340", type: "drugbank", label: "DrugBank — Mechanism of action" },
    { url: "https://en.wikipedia.org/wiki/Vinblastine", type: "wiki", label: "Wikipedia — Vinblastine" }
  ]
};

/* Compact browse index — a few representative rows */
window.DMDB_INDEX = [
  { id:"DB00570_MESH_D013736_2", drug:"Vinblastine",   disease:"Malignant tumor of testis", area:"Neoplasms",          target:"Tubulin beta chain", types:["Drug","Protein","BiologicalProcess","Disease"], steps:5 },
  { id:"DB00945_MESH_D013167_1", drug:"Aspirin",       disease:"Rheumatoid arthritis",      area:"Immune",             target:"Prostaglandin G/H synthase 2", types:["Drug","Protein","BiologicalProcess","PhenotypicFeature","Disease"], steps:4 },
  { id:"DB01076_MESH_D006937_1", drug:"Atorvastatin",  disease:"Hypercholesterolemia",      area:"Metabolic",          target:"HMG-CoA reductase", types:["Drug","Protein","Pathway","Disease"], steps:4 },
  { id:"DB00619_MESH_D015464_1", drug:"Imatinib",      disease:"Chronic myeloid leukemia",  area:"Neoplasms",          target:"BCR/ABL fusion protein", types:["Drug","Protein","BiologicalProcess","Disease"], steps:3 },
  { id:"DB00331_MESH_D003924_1", drug:"Metformin",     disease:"Type 2 diabetes mellitus",  area:"Metabolic",          target:"AMP-activated protein kinase", types:["Drug","Protein","MolecularActivity","Disease"], steps:5 },
  { id:"DB00316_MESH_D010146_1", drug:"Acetaminophen", disease:"Pain",                      area:"Nervous system",     target:"Prostaglandin G/H synthase 1", types:["Drug","Protein","BiologicalProcess","PhenotypicFeature"], steps:6 },
  { id:"DB00997_MESH_D013736_1", drug:"Doxorubicin",   disease:"Malignant tumor of testis", area:"Neoplasms",          target:"DNA topoisomerase 2-alpha", types:["Drug","Protein","BiologicalProcess","Disease"], steps:4 },
  { id:"DB00563_MESH_D009101_1", drug:"Methotrexate",  disease:"Multiple myeloma",          area:"Neoplasms",          target:"Dihydrofolate reductase", types:["Drug","Protein","Pathway","BiologicalProcess","Disease"], steps:5 },
  { id:"DB00788_MESH_D010003_1", drug:"Naproxen",      disease:"Osteoarthritis",            area:"Musculoskeletal",    target:"Prostaglandin G/H synthase 2", types:["Drug","Protein","BiologicalProcess","Disease"], steps:4 },
  { id:"DB00482_MESH_D002289_1", drug:"Celecoxib",     disease:"Colorectal carcinoma",      area:"Neoplasms",          target:"Prostaglandin G/H synthase 2", types:["Drug","Protein","BiologicalProcess","Disease"], steps:5 },
  { id:"DB00390_MESH_D006333_1", drug:"Digoxin",       disease:"Heart failure",             area:"Cardiovascular",     target:"Sodium/potassium-transporting ATPase", types:["Drug","Protein","MolecularActivity","Disease"], steps:4 },
  { id:"DB00641_MESH_D006937_2", drug:"Simvastatin",   disease:"Hypercholesterolemia",      area:"Metabolic",          target:"HMG-CoA reductase", types:["Drug","Protein","Pathway","Disease"], steps:4 }
];
