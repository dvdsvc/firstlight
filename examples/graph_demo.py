"""Run the original document-forest algorithm on a tiny synthetic XML table."""
from __future__ import annotations
import json
import tempfile
import zipfile
from pathlib import Path
from research.seeded_graph.seeded_document_forest import complete_document

def main():
    cells = [["A101", "120", "1"], ["A102", "130", "2"], ["A103", "140", "3"]]
    rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{s}</w:t></w:r></w:p></w:tc>" for s in row) + "</w:tr>" for row in cells)
    document = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl>' + rows + '</w:tbl></w:body></w:document>'
    state = {"samples": [{"id": "A101", "measure_events": [{"value": {"number": 120, "error": {"value": 1}}}]}, {"id": "A102", "measure_events": []}, {"id": "A103", "measure_events": []}]}
    config = json.loads((Path(__file__).parents[1] / "research/seeded_graph/seeded_document_forest_config.json").read_text())
    with tempfile.TemporaryDirectory(prefix="geochron-synthetic-") as tmp:
        d = Path(tmp);docx = d / "synthetic.docx";seed = d / "state.json"
        with zipfile.ZipFile(docx, "w") as z:z.writestr("word/document.xml", document)
        seed.write_text(json.dumps(state))
        result = complete_document("synthetic-table", docx, seed, config["candidate_threshold"], config["candidate_ratio"], config)
    assert result["status"] == "ok" and result["fixed_seed_channels"] == 1
    targets = {(x["sample"], x["number"], x["error"]) for x in result["candidate_forest"]}
    if ("A102", 130, 2) not in targets or ("A103", 140, 3) not in targets:
        raise RuntimeError("Synthetic target relationships were not proposed")
    print(json.dumps({"data_kind": "synthetic XML table and legacy seed JSON; not real-paper accuracy", "result": result}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
