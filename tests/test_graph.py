from graft.graph import CodebaseGraph


def test_default_scan_indexes_all_files_beyond_200(tmp_path):
    expected_files = set()
    for index in range(250):
        folder = tmp_path / "src" / f"package_{index // 50}"
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / f"module_{index}.py"
        source.write_text(f"def marker_{index}():\n    return {index}\n", encoding="utf-8")
        expected_files.add(source.relative_to(tmp_path).as_posix())

    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "dependency.py").write_text("def ignored():\n    pass\n", encoding="utf-8")

    graph = CodebaseGraph(str(tmp_path))
    graph.scan()

    assert set(graph.files) == expected_files
    assert graph.get_summary()["total_files"] == 250
    for index in range(250):
        matches = graph.find_symbol(f"marker_{index}")
        assert len(matches) == 1
        assert matches[0]["file"] == f"src/package_{index // 50}/module_{index}.py"
    assert graph.find_symbol("ignored") == []


def test_explicit_scan_limit_does_not_affect_next_default_scan(tmp_path):
    for index in range(5):
        (tmp_path / f"module_{index}.py").write_text(
            f"def marker_{index}():\n    return {index}\n", encoding="utf-8"
        )

    graph = CodebaseGraph(str(tmp_path))
    graph.scan(max_files=2)
    assert len(graph.files) == 2

    graph.scan()
    assert len(graph.files) == 5
    assert len(graph.symbol_index) == 5
