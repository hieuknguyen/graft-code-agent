"""Shared declarations for built-in coding tools exposed by both AI adapters."""


def schema(name, description, properties, required=()):
    parameters = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = list(required)
    return {"name": name, "description": description, "parameters_json_schema": parameters}


CODING_TOOL_SCHEMAS = [
    schema("edit_file_ranges", "Edit up to 200 non-overlapping line ranges in one file up to 8 MB, using its remembered read version. All line numbers refer to the original snapshot. Complete candidate syntax is checked automatically and errors returned before any write.", {
        "path": {"type": "string"},
        "edits": {"type": "array", "items": {"type": "object", "properties": {
            "start_line": {"type": "integer", "description": "1-based first line, inclusive."},
            "end_line": {"type": "integer", "description": "Last line inclusive. start_line-1 inserts before start_line; total_lines+1/total_lines appends."},
            "new_text": {"type": "string", "description": "New complete lines; empty deletes range. Line separator is kept where required."},
        }, "required": ["start_line", "end_line", "new_text"]}},
        "description": {"type": "string"},
    }, ["path", "edits"]),
    schema("edit_file", "Preferred tool for a single exact replacement in an existing UTF-8 file. Read the relevant source with read_file/read_symbol first; the app remembers its version. Returns a pending edit card; never runs a shell or writes before application.", {
        "path": {"type": "string", "description": "Project-relative file path."},
        "old_text": {"type": "string", "description": "Exact source text occurring once, without read_file line-number prefixes."},
        "new_text": {"type": "string", "description": "Replacement text; empty removes old_text."},
        "description": {"type": "string", "description": "Short explanation of the change."},
    }, ["path", "old_text", "new_text"]),
    schema("find_files", "Find safe project paths by glob without reading their contents. Supports pagination.", {
        "pattern": {"type": "string", "description": "Project-relative glob, e.g. **/*.py or src/*service*.ts."},
        "max_results": {"type": "integer"}, "offset": {"type": "integer"},
    }, ["pattern"]),
    schema("list_symbols", "List Python (.py/.pyi) functions, classes and methods with source ranges and a file hash.", {
        "path": {"type": "string"},
    }, ["path"]),
    schema("read_symbol", "Read a Python (.py/.pyi) symbol including decorators. Specify parent to disambiguate methods. Reports truncation.", {
        "path": {"type": "string"}, "symbol": {"type": "string"},
        "parent": {"type": "string", "description": "Parent class, if needed to disambiguate."},
    }, ["path", "symbol"]),
    schema("check_syntax", "Inspect syntax of an existing file with the detected language's offline parser. Returns valid/invalid/unavailable and diagnostics. read_file and edit proposals already check syntax automatically; use this only for an explicit additional inspection. Does not run project code, types, builds or tests.", {
        "path": {"type": "string"},
    }, ["path"]),
    schema("propose_edit_file", "Prepare exact replacements in an existing UTF-8 file. Each old_text must match once; edits must not overlap. Never writes directly.", {
        "path": {"type": "string"},
        "expected_sha256": {"type": "string", "description": "Current file hash from a read tool."},
        "description": {"type": "string"},
        "edits": {"type": "array", "items": {
            "type": "object", "properties": {
                "old_text": {"type": "string"}, "new_text": {"type": "string"},
            }, "required": ["old_text", "new_text"],
        }},
    }, ["path", "edits", "expected_sha256"]),
]

GATEWAY_TOOL_NAMES = frozenset({
    "project_overview", "list_files", "search_project", "read_file",
    *(item["name"] for item in CODING_TOOL_SCHEMAS),
})
