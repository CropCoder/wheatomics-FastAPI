"""Declarative catalog of the WheatOmics MCP server.

This module is intentionally dependency-free (no ``mcp`` import): it is the
single source of truth for

* the tools advertised by the MCP server (name / description / JSON schema),
* the module groups used by the documentation page and the ``list_resources``
  module catalog,
* the copy-ready "generate a WheatOmics data-query skill" prompt.

``app/mcp/wheatomics_tools.py`` turns ``TOOL_SPECS`` into ``mcp.types.Tool``
objects and routes ``call_tool`` to the corresponding FastAPI handler;
``/agent.html`` and the docs are kept in sync with the same list.
"""
from __future__ import annotations

#: Module catalog: public REST prefix + doc anchor for every platform module.
MODULE_CATALOG: list[dict[str, str]] = [
    {"module": "Known Genes", "rest": "/api/genes/known", "docs": "/agent.html#mcp"},
    {"module": "GeneHub", "rest": "/api/genes/detail/{gene_id}", "docs": "/agent.html#mcp"},
    {"module": "PfamSearch", "rest": "/api/genes/functions/pfam", "docs": "/agent.html#mcp"},
    {"module": "IntervalTool", "rest": "/api/genes/functions/interval", "docs": "/agent.html#mcp"},
    {"module": "Sequences", "rest": "/api/sequence", "docs": "/agent.html#mcp"},
    {"module": "BLAST", "rest": "/api/blast", "docs": "/agent.html#mcp"},
    {"module": "Expression", "rest": "/api/expression", "docs": "/agent.html#mcp"},
    {"module": "Co-expression", "rest": "/api/coexpression", "docs": "/agent.html#mcp"},
    {"module": "WheatPPI", "rest": "/api/ppi", "docs": "/agent.html#mcp"},
    {"module": "Comparative", "rest": "/api/comparative", "docs": "/agent.html#mcp"},
    {"module": "GO/KEGG Enrichment", "rest": "/api/go · /api/kegg", "docs": "/agent.html#mcp"},
    {"module": "eQTL Atlas", "rest": "/api/eqtl", "docs": "/agent.html#mcp"},
    {"module": "Triticeae Papers", "rest": "/api/papers", "docs": "/agent.html#mcp"},
    {"module": "Genomes", "rest": "/api/genomes", "docs": "/agent.html#mcp"},
    {"module": "JBrowse", "rest": "/api/jbrowse", "docs": "/agent.html#mcp"},
    {"module": "CAPS/dCAPS", "rest": "/api/caps", "docs": "/agent.html#mcp"},
    {"module": "VariantHub", "rest": "/api/VariantHub", "docs": "/agent.html#mcp"},
    {"module": "OrthoFinder", "rest": "/api/orthofinder", "docs": "/agent.html#mcp"},
    {"module": "PrimerServer2", "rest": "/api/PrimerServer2", "docs": "/agent.html#mcp"},
]

#: The copy-ready prompt shown on /agent.html#howto (keep the two in sync).
AGENT_PROMPT: str = """Please read the WheatOmics platform OpenAPI documentation:
https://wheatomics.sdau.edu.cn/api/docs
Machine-readable schema:
https://wheatomics.sdau.edu.cn/api/openapi.json

Based on that documentation, generate a "WheatOmics Data Query" skill for me.

Requirements:
1. Cover every module in the documentation — gene search, expression profiles, sequence retrieval, BLAST, synteny, variation data, literature, and any other module you find.
2. For each module, document its endpoints, parameters, response format, call examples and important notes.
3. Organize the result into a reusable skill file that can be loaded directly in later conversations.
4. Generate everything strictly from the actual endpoint definitions in the OpenAPI document — never invent endpoints that do not exist.
5. Write this hard rule into the skill: whenever an answer involves a specific gene ID, pathway ID (GO/KEGG) or cited reference (PMID/DOI), you MUST call the corresponding API endpoint to verify it in real time. Never rely on memory or guesswork, and never present anything as fact unless it came from an actual API response.
6. Add an "automatic result persistence" convention to the skill: whenever a query produces results the user may want to cite or reproduce later (gene details, expression profiles, BLAST hits, enrichment results, literature, etc.), write them to local files (JSON / Markdown report) by default instead of leaving them only in the conversation. Document the save-to-file usage `wheatomics.py ... -o <file>` and suggest an output directory (for example `./wheatomics_results/`)."""


def _p(type_: str, description: str, default=None, enum=None, items=None, minimum=None, maximum=None):
    prop: dict = {"type": type_, "description": description}
    if default is not None:
        prop["default"] = default
    if enum is not None:
        prop["enum"] = enum
    if items is not None:
        prop["items"] = items
    if minimum is not None:
        prop["minimum"] = minimum
    if maximum is not None:
        prop["maximum"] = maximum
    return prop


def _tool(name: str, group: str, description: str, properties: dict, required: list[str]):
    return {
        "name": name,
        "group": group,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


#: All tools exposed by the WheatOmics MCP server.
TOOL_SPECS: list[dict] = [
    # ------------------------------------------------------------------
    # Sequences & primers (original 4 tools, unchanged schemas)
    # ------------------------------------------------------------------
    _tool(
        "get_sequence_by_gene",
        "Sequences & primers",
        "Retrieve wheat gene and protein FASTA records by gene ID.",
        {
            "gene_id": _p("string", "Target gene ID (e.g., TraesCS1A02G001000)"),
            "gene_db": _p("string", "Gene database name", default="all_gene"),
            "protein_db": _p("string", "Protein database name", default="all_protein"),
        },
        ["gene_id"],
    ),
    _tool(
        "get_sequence_by_interval",
        "Sequences & primers",
        "Retrieve FASTA sequence by genomic interval using blastdbcmd.",
        {
            "region": _p("string", "Genomic region in legacy format (e.g., chr1A:10-100)"),
            "database": _p("string", "Genome database name (must contain 'genome')"),
        },
        ["region", "database"],
    ),
    _tool(
        "batch_sequence",
        "Sequences & primers",
        "Retrieve direct-entry FASTA for multiple gene IDs.",
        {
            "database": _p("string", "Database name"),
            "ids": _p("string", "Space-separated string of gene identifiers"),
        },
        ["database", "ids"],
    ),
    _tool(
        "design_caps_primers",
        "Sequences & primers",
        "Design CAPS/dCAPS primer pairs that discriminate two alleles of a SNP by restriction digestion. "
        "Provide the two allele sequences (equal length, differing at exactly one position); returns ranked "
        "designs with enzyme, primer sequences, mismatches, cut position and Tm. mismatch_max 0 = CAPS only "
        "(natural site), 1-3 = dCAPS (primer introduces mismatches).",
        {
            "seq1": _p("string", "Allele 1 sequence (A/C/G/T)"),
            "seq2": _p("string", "Allele 2 sequence, same length, one base differs"),
            "mismatch_max": _p("integer", "Max primer mismatches (0-3)", default=1, minimum=0, maximum=3),
            "top_n": _p("integer", "Number of designs to return", default=10),
        },
        ["seq1", "seq2"],
    ),
    # ------------------------------------------------------------------
    # Genes & annotation
    # ------------------------------------------------------------------
    _tool(
        "search_known_genes",
        "Genes & annotation",
        "Search the curated KnownGene list (cloned, functionally validated wheat genes) by keyword. "
        "Returns phenotype, functional category, species, reference genome IDs and publications. "
        "Use it before claiming a gene's function or citing a cloned-gene paper.",
        {
            "search": _p("string", "Search keyword (partial match; gene ID, gene name, phenotype, DOI, ...)"),
            "field": _p(
                "string",
                "Field to search",
                default="all",
                enum=[
                    "all", "gene_id", "gene_name", "reference_genome_id", "phenotype",
                    "species", "doi", "protein_family", "functional_category", "chrom_pos",
                    "research_strategy",
                ],
            ),
            "limit": _p("integer", "Maximum rows (1-5000)", default=20, minimum=1, maximum=5000),
            "offset": _p("integer", "Pagination offset", default=0, minimum=0),
        },
        ["search"],
    ),
    _tool(
        "get_known_gene",
        "Genes & annotation",
        "Get one curated KnownGene record with v2056 structured fields (phenotype, functional category, "
        "reference genome ID, validation methods, publications). Numeric IDs match clone_id; other values "
        "match gene_id / gene_name.",
        {"gene_id": _p("string", "Known-gene ID, gene name or numeric clone_id")},
        ["gene_id"],
    ),
    _tool(
        "get_gene_detail",
        "Genes & annotation",
        "Get normalized GeneHub details for a wheat gene: genome location, protein length / MW / pI, "
        "functional annotations, cross-version IDs and JBrowse/Ensembl links. Accepts IWGSC v1, v2 and v3 "
        "gene IDs (e.g. TraesCS5A02G391700).",
        {"gene_id": _p("string", "Wheat gene ID (IWGSC v1/v2/v3)")},
        ["gene_id"],
    ),
    _tool(
        "resolve_gene_id",
        "Genes & annotation",
        "Resolve a gene ID across the Genefunc annotation tables and return its Chinese Spring 02G "
        "mapping. Useful for non-Chinese-Spring IDs before querying other modules.",
        {"gene_id": _p("string", "Gene ID to resolve (any annotation version)")},
        ["gene_id"],
    ),
    _tool(
        "search_pfam",
        "Genes & annotation",
        "Find all genes carrying a PFAM domain (gene-family search with PfamSearch). Table defaults to "
        "the Chinese Spring IWGSC03 annotation; use /api/genes/functions/tables for alternatives.",
        {
            "domain": _p("string", "PFAM domain ID starting with PF (e.g. PF00069)"),
            "table": _p("string", "Genefunc table name", default="Genefunc_CS_IWGSC03G_table"),
        },
        ["domain"],
    ),
    _tool(
        "genes_in_interval",
        "Genes & annotation",
        "List all genes within a chromosomal interval (IntervalTool). Also returns the PFAM/domain "
        "annotation column for those genes.",
        {
            "region": _p("string", "Interval, e.g. chr5A:587000000..587200000"),
            "table": _p("string", "Genefunc table name", default="Genefunc_CS_IWGSC03G_table"),
        },
        ["region"],
    ),
    # ------------------------------------------------------------------
    # Expression & networks
    # ------------------------------------------------------------------
    _tool(
        "list_expression_projects",
        "Expression & networks",
        "List the gene-expression projects available for query_expression (project keys and descriptions).",
        {},
        [],
    ),
    _tool(
        "query_expression",
        "Expression & networks",
        "Query expression values (and standard deviations) of one or more genes in an expression project. "
        "Gene IDs must use the Chinese Spring IWGSC v2.1 annotation. Call list_expression_projects first "
        "to discover valid project keys.",
        {
            "gene_ids": _p("string", "Comma-separated gene IDs (e.g. TraesCS1A02G001000)"),
            "project": _p("string", "Expression project key", default="PRJEB5314_paired_tbl"),
        },
        ["gene_ids"],
    ),
    _tool(
        "query_coexpression",
        "Expression & networks",
        "Query co-expression partners of genes in a co-expression database. filter_value < 1 filters by "
        "PCC (|PCC| >= value); filter_value >= 1 filters by mutual rank (MR <= value).",
        {
            "gene_ids": _p("string", "Comma-separated gene IDs"),
            "database": _p("string", "Co-expression database name", default="CO_PRJEB25639"),
            "filter_value": _p("number", "PCC threshold (<1) or mutual-rank threshold (>=1)", default=300),
        },
        ["gene_ids"],
    ),
    _tool(
        "query_ppi",
        "Expression & networks",
        "Query protein-protein interactions for wheat proteins (wheatPPI, CF-MS). Input must be "
        "transcript IDs with the '.1' suffix (e.g. TraesCS6D02G084800.1).",
        {
            "gene_ids": _p("string", "Comma-separated transcript IDs ('.1' suffix required)"),
            "table": _p("string", "PPI data table", default="PPI_result"),
            "min_score": _p("number", "Minimum interaction score", default=0.5),
        },
        ["gene_ids"],
    ),
    # ------------------------------------------------------------------
    # Comparative & variation
    # ------------------------------------------------------------------
    _tool(
        "find_homologs",
        "Comparative & variation",
        "Find rice and Arabidopsis homologs of a wheat gene with alignment details (Qcovs, identity, "
        "E-value, score). max_targets caps hits per species.",
        {
            "gene_id": _p("string", "Wheat gene ID (Traes...) or a gene ID from another species"),
            "max_targets": _p("integer", "Maximum homologs per species", default=3, minimum=1, maximum=50),
        },
        ["gene_id"],
    ),
    _tool(
        "search_synteny",
        "Comparative & variation",
        "Search synteny relationships between Chinese Spring and Durum wheat, wild emmer, T. urartu and "
        "Ae. tauschii. Query mode 1: genomic interval (chr5A:100000-200000); mode 2: a single gene ID.",
        {
            "query": _p("string", "Gene ID or genomic interval (chr5A:100000-200000)"),
            "table": _p("string", "Synteny table name", default="CSsymaptbl"),
        },
        ["query"],
    ),
    _tool(
        "convert_gene_ids",
        "Comparative & variation",
        "Convert transcript IDs from MIPS v2.2, TGACv1 or IWGSC v1.0 annotation to IWGSC v1.1 (02G). "
        "Provide transcript IDs with the '.1' suffix; multiple IDs are separated by newlines or spaces.",
        {
            "gene_ids": _p("string", "One or more transcript IDs ('.1' suffix)"),
            "version": _p(
                "string",
                "Source annotation table",
                enum=["MIPS_result", "TGACv1_result", "IWGSCv1_result"],
            ),
        },
        ["gene_ids", "version"],
    ),
    _tool(
        "search_eqtl",
        "Comparative & variation",
        "Query eQTL records for a gene (fuzzy match on the eQTL table) and return each project's FarmCPU "
        "Manhattan-plot information.",
        {"gene": _p("string", "Gene ID (e.g. TraesCS5A02G391700)")},
        ["gene"],
    ),
    # ------------------------------------------------------------------
    # Enrichment & literature
    # ------------------------------------------------------------------
    _tool(
        "go_enrichment",
        "Enrichment & literature",
        "Run GO enrichment (hypergeometric test + Benjamini-Hochberg FDR) for a list of wheat genes using "
        "the wheat_function database.",
        {
            "genes": _p("array", "Wheat gene IDs", items={"type": "string"}),
            "padj_threshold": _p("number", "Adjusted p-value threshold", default=0.05),
        },
        ["genes"],
    ),
    _tool(
        "kegg_enrichment",
        "Enrichment & literature",
        "Run KEGG pathway enrichment (hypergeometric test + Benjamini-Hochberg FDR) for a list of wheat genes.",
        {
            "genes": _p("array", "Wheat gene IDs", items={"type": "string"}),
            "padj_threshold": _p("number", "Adjusted p-value threshold", default=0.05),
        },
        ["genes"],
    ),
    _tool(
        "search_papers",
        "Enrichment & literature",
        "Search the Triticeae literature table (12K+ papers) by title, abstract, journal, authors, PubMed "
        "keywords, gene name, PMID or date. Always verify PMID/DOI claims against get_paper or the paper "
        "annotation endpoint.",
        {
            "q": _p("string", "Full-text keyword query"),
            "title": _p("string", "Title keyword"),
            "abstract": _p("string", "Abstract keyword"),
            "journal": _p("string", "Journal keyword"),
            "authors": _p("string", "Author keyword"),
            "pubmed_keywords": _p("string", "PubMed keyword"),
            "gene_name": _p("string", "Gene name keyword"),
            "pmid": _p("string", "PubMed ID"),
            "pub_date_start": _p("string", "Publication date start (inclusive)"),
            "pub_date_end": _p("string", "Publication date end (inclusive)"),
            "since_days": _p("integer", "Only papers added to the table within the last N days"),
            "limit": _p("integer", "Maximum rows", default=20, minimum=1, maximum=200),
            "offset": _p("integer", "Pagination offset", default=0, minimum=0),
        },
        [],
    ),
    _tool(
        "get_paper",
        "Enrichment & literature",
        "Fetch one Triticeae paper record by PubMed ID, including metadata used to verify citations.",
        {"pubmedid": _p("string", "PubMed ID (PMID)")},
        ["pubmedid"],
    ),
    # ------------------------------------------------------------------
    # Genomes, JBrowse & BLAST
    # ------------------------------------------------------------------
    _tool(
        "list_genomes",
        "Genomes, JBrowse & BLAST",
        "List reference genomes in the WheatOmics registry with assembly metadata, ploidy and annotation status.",
        {
            "ploidy": _p("string", "Filter by ploidy (e.g. AB, AABB, AABBDD)"),
            "annotation_status": _p("string", "Filter by annotation status"),
            "has_annotation": _p("boolean", "Only genomes with/without annotation"),
            "q": _p("string", "Keyword search over dataset names/species"),
            "include_hidden": _p("boolean", "Include hidden datasets", default=False),
            "limit": _p("integer", "Maximum rows", default=100, minimum=1, maximum=500),
            "offset": _p("integer", "Pagination offset", default=0, minimum=0),
        },
        [],
    ),
    _tool(
        "get_genome",
        "Genomes, JBrowse & BLAST",
        "Get one reference-genome record by dataset ID (assembly, ploidy, annotation and download links).",
        {"dataset_id": _p("string", "Genome dataset ID from list_genomes")},
        ["dataset_id"],
    ),
    _tool(
        "list_jbrowse_datasets",
        "Genomes, JBrowse & BLAST",
        "List JBrowse datasets and their track counts (for genome-browser links).",
        {},
        [],
    ),
    _tool(
        "submit_blast",
        "Genomes, JBrowse & BLAST",
        "Submit a BLAST search against wheat/Triticeae BLAST databases and return a job_id immediately "
        "(always asynchronous). Poll get_blast_status for progress and download links. Call "
        "list_blast_databases first to discover valid database names.",
        {
            "program": _p(
                "string",
                "BLAST program",
                default="blastp",
                enum=["blastp", "blastn", "blastx", "tblastn", "tblastx"],
            ),
            "database": _p("string", "Database name(s), comma-separated (max 20)"),
            "query": _p("string", "Query sequence(s) in FASTA format"),
            "evalue": _p("number", "E-value threshold (0-1000)", default=10.0),
            "max_target_seqs": _p("integer", "Maximum target sequences", default=1000, minimum=1, maximum=50000),
            "word_size": _p("integer", "Optional word size"),
            "matrix": _p("string", "Optional scoring matrix"),
            "outfmt": _p("string", "Result format", default="tabular", enum=["tabular", "traditional", "both"]),
        },
        ["database", "query"],
    ),
    _tool(
        "get_blast_status",
        "Genomes, JBrowse & BLAST",
        "Check a BLAST job (pending / running / done / error / stale) and get download links when finished.",
        {"job_id": _p("string", "Job ID returned by submit_blast (UUID)")},
        ["job_id"],
    ),
    _tool(
        "list_blast_databases",
        "Genomes, JBrowse & BLAST",
        "List BLAST databases grouped by protein/nucleotide and genome category. Use it to choose valid "
        "database names for submit_blast.",
        {
            "program": _p(
                "string",
                "Restrict to one program's databases",
                enum=["blastp", "blastn", "blastx", "tblastn", "tblastx"],
            ),
        },
        [],
    ),
]

#: Tools grouped for the documentation page (order preserved).
TOOL_GROUPS: list[dict] = []
for _spec in TOOL_SPECS:
    if not TOOL_GROUPS or TOOL_GROUPS[-1]["name"] != _spec["group"]:
        TOOL_GROUPS.append({"name": _spec["group"], "tools": []})
    TOOL_GROUPS[-1]["tools"].append(_spec)

#: MCP resources (read-only docs the client can fetch without a tool call).
RESOURCE_SPECS: list[dict] = [
    {
        "uri": "wheatomics://docs/modules",
        "name": "WheatOmics module & MCP tool catalog",
        "description": "JSON catalog: every platform module, its REST prefix, and the MCP tools that cover it.",
        "mimeType": "application/json",
    },
    {
        "uri": "wheatomics://docs/agent-guide",
        "name": "WheatOmics agent guide",
        "description": "Markdown guide: endpoints, tool conventions, mandatory live-verification rule and result-persistence convention.",
        "mimeType": "text/markdown",
    },
]
