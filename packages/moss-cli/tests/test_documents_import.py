import io
import json
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from moss_cli.commands import doc as doc_cmd
from moss_cli.documents import load_documents
from moss_cli.main import app

runner = CliRunner()
AUTH_OPTIONS = [
    "--project-id",
    "project-id",
    "--project-key",
    "project-key",
]


def _install_recording_client(monkeypatch, seen):
    class FakeClient:
        def __init__(self, project_id, project_key):
            seen["credentials"] = (project_id, project_key)

        async def add_docs(self, index_name, docs, options):
            seen.update(
                index_name=index_name,
                docs=docs,
                upsert=options.upsert if options else False,
            )
            return SimpleNamespace(
                job_id="job-123", index_name=index_name, doc_count=len(docs)
            )

    monkeypatch.setattr(doc_cmd, "MossClient", FakeClient)


def _invoke_import(path, *options, group="doc", json_output=False):
    args = [*AUTH_OPTIONS]
    if json_output:
        args.append("--json")
    args.extend([group, "import", "products", "--file", str(path), *options])
    return runner.invoke(app, args)


def test_load_mapped_csv_with_metadata_and_multiline_text(tmp_path):
    path = tmp_path / "products.csv"
    path.write_text(
        "sku,description,category,price\n"
        'A-100,"Lightweight trail\nrunning shoe",footwear,89.99\n'
        "A-200,Waterproof hiking boot,,129.99\n",
        encoding="utf-8",
    )

    docs = load_documents(
        str(path),
        id_column="sku",
        text_column="description",
        metadata_columns=["category", "price"],
    )

    assert [(doc.id, doc.text) for doc in docs] == [
        ("A-100", "Lightweight trail\nrunning shoe"),
        ("A-200", "Waterproof hiking boot"),
    ]
    assert docs[0].metadata == {"category": "footwear", "price": "89.99"}
    assert docs[1].metadata == {"price": "129.99"}


def test_load_mapped_wrapper_json_stringifies_metadata_values(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "sku": 100,
                        "body": "Trail shoe",
                        "price": 89.99,
                        "tags": ["trail", "lightweight"],
                        "details": {"color": "blue"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    docs = load_documents(
        str(path),
        id_column="sku",
        text_column="body",
        metadata_columns=["price", "tags", "details"],
    )

    assert docs[0].id == "100"
    assert docs[0].text == "Trail shoe"
    assert docs[0].metadata == {
        "price": "89.99",
        "tags": '["trail", "lightweight"]',
        "details": '{"color": "blue"}',
    }


def test_load_mapped_jsonl_allows_optional_metadata_fields(tmp_path):
    path = tmp_path / "products.jsonl"
    path.write_text(
        '{"sku":"A-1","body":"One","category":"shoes"}\n'
        '{"sku":"A-2","body":"Two"}\n',
        encoding="utf-8",
    )

    docs = load_documents(
        str(path),
        id_column="sku",
        text_column="body",
        metadata_columns=["category"],
    )

    assert docs[0].metadata == {"category": "shoes"}
    assert docs[1].metadata is None


def test_load_mapped_json_from_stdin(monkeypatch):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO('[{"doc_id":"one","body":"From stdin"}]'),
    )

    docs = load_documents("-", id_column="doc_id", text_column="body")

    assert [(doc.id, doc.text) for doc in docs] == [("one", "From stdin")]


def test_single_json_object_reports_expected_container(tmp_path):
    path = tmp_path / "document.json"
    path.write_text('{"id":"one","text":"Hello"}', encoding="utf-8")

    with pytest.raises(
        typer.BadParameter,
        match="Expected a JSON array or an object with a 'documents' or 'docs' array",
    ):
        load_documents(str(path))


def test_default_mapping_preserves_metadata_and_embedding(tmp_path):
    path = tmp_path / "documents.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "one",
                    "text": "Default format",
                    "metadata": {"rank": 1, "active": True, "skip": None},
                    "embedding": [0.1, 0.2],
                }
            ]
        ),
        encoding="utf-8",
    )

    docs = load_documents(str(path))

    assert docs[0].metadata == {"rank": "1", "active": "True"}
    assert list(docs[0].embedding) == pytest.approx([0.1, 0.2])


def test_default_csv_accepts_json_null_metadata_and_embedding(tmp_path):
    path = tmp_path / "documents.csv"
    path.write_text(
        "id,text,metadata,embedding\none,Hello,null,null\n", encoding="utf-8"
    )

    docs = load_documents(str(path))

    assert docs[0].metadata is None
    assert docs[0].embedding is None


def test_default_mapping_preserves_empty_metadata_object(tmp_path):
    path = tmp_path / "documents.json"
    path.write_text('[{"id":"one","text":"Hello","metadata":{}}]', encoding="utf-8")

    docs = load_documents(str(path))

    assert docs[0].metadata == {}


@pytest.mark.parametrize("text_column", ["metadata", "embedding"])
def test_mapped_required_column_can_use_legacy_special_name(tmp_path, text_column):
    path = tmp_path / "documents.csv"
    path.write_text(f"id,{text_column}\none,Ordinary text\n", encoding="utf-8")

    docs = load_documents(str(path), text_column=text_column)

    assert docs[0].text == "Ordinary text"
    assert docs[0].metadata is None
    assert docs[0].embedding is None


def test_mapped_metadata_can_use_embedding_column_name(tmp_path):
    path = tmp_path / "documents.csv"
    path.write_text("id,text,embedding\none,Hello,source-value\n", encoding="utf-8")

    docs = load_documents(str(path), metadata_columns=["embedding"])

    assert docs[0].metadata == {"embedding": "source-value"}
    assert docs[0].embedding is None


def test_csv_with_utf8_bom_is_supported(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text("\ufeffid,text\none,Hello\n", encoding="utf-8")

    docs = load_documents(str(path))

    assert docs[0].id == "one"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "sku,description\nA-1,Hello\n",
            "mapped required column(s) not found: 'id', 'text'",
        ),
        ("id,text\n,Hello\n", "mapped ID column 'id' is blank"),
        ("id,text\nA-1,   \n", "mapped text column 'text' is blank"),
    ],
)
def test_csv_reports_actionable_required_column_errors(tmp_path, content, message):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(typer.BadParameter) as exc_info:
        load_documents(str(path), require_non_empty=True)
    assert message in str(exc_info.value)


def test_json_reports_missing_mapped_required_column(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[{"sku":"A-1"}]', encoding="utf-8")

    with pytest.raises(
        typer.BadParameter,
        match="Document at index 0: missing mapped text column 'body'",
    ):
        load_documents(str(path), id_column="sku", text_column="body")


def test_validate_keeps_aggregating_blank_text_and_duplicate_ids(tmp_path):
    path = tmp_path / "documents.csv"
    path.write_text(
        "id,text\nsame,\nsame,Hello\nother,   \n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--json", "validate", "--file", str(path)])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["doc_count"] == 3
    assert "Duplicate ID 'same' appears 2 times" in payload["issues"]
    assert "Document 0 (id='same'): empty text" in payload["issues"]
    assert "Document 2 (id='other'): empty text" in payload["issues"]


def test_missing_trailing_csv_value_is_not_stringified_as_none(tmp_path):
    path = tmp_path / "documents.csv"
    path.write_text("id,text\none\n", encoding="utf-8")

    with pytest.raises(
        typer.BadParameter, match="mapped text column 'text' has no value"
    ):
        load_documents(str(path))

    result = runner.invoke(app, ["--json", "validate", "--file", str(path)])
    assert result.exit_code == 1
    assert json.loads(result.output)["valid"] is False


@pytest.mark.parametrize(
    "suffix,content",
    [("csv", "id,text\none,Hello\n"), ("json", '[{"id":"one","text":"Hello"}]')],
)
def test_unknown_metadata_column_is_rejected(tmp_path, suffix, content):
    path = tmp_path / f"documents.{suffix}"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(
        typer.BadParameter, match=r"mapped metadata column\(s\) not found: 'missing'"
    ):
        load_documents(str(path), metadata_columns=["missing"])


def test_invalid_metadata_and_embedding_are_rejected(tmp_path):
    metadata_path = tmp_path / "metadata.csv"
    metadata_path.write_text("id,text,metadata\none,Hello,not-json\n", encoding="utf-8")
    embedding_path = tmp_path / "embedding.json"
    embedding_path.write_text(
        '[{"id":"one","text":"Hello","embedding":[0.1,true]}]',
        encoding="utf-8",
    )

    with pytest.raises(typer.BadParameter, match="invalid JSON in 'metadata' column"):
        load_documents(str(metadata_path))
    with pytest.raises(
        typer.BadParameter, match="'embedding' must be a JSON array of numbers"
    ):
        load_documents(str(embedding_path))


def test_duplicate_csv_headers_are_rejected(tmp_path):
    path = tmp_path / "duplicate.csv"
    path.write_text("id,text,text\none,Hello,Again\n", encoding="utf-8")

    with pytest.raises(typer.BadParameter, match=r"duplicate column\(s\): 'text'"):
        load_documents(str(path))


@pytest.mark.parametrize("command_group", ["doc", "documents"])
def test_import_command_maps_columns_for_both_command_names(
    monkeypatch, tmp_path, command_group
):
    path = tmp_path / "products.csv"
    path.write_text(
        "sku,description,category,price\n" "A-100,Trail shoe,footwear,89.99\n",
        encoding="utf-8",
    )
    seen = {}
    _install_recording_client(monkeypatch, seen)

    result = _invoke_import(
        path,
        "--id-column",
        "sku",
        "--text-column",
        "description",
        "--metadata-columns",
        "category,price",
        "--upsert",
        group=command_group,
    )

    assert result.exit_code == 0, result.output
    assert seen["credentials"] == ("project-id", "project-key")
    assert seen["index_name"] == "products"
    assert seen["upsert"] is True
    assert seen["docs"][0].id == "A-100"
    assert seen["docs"][0].text == "Trail shoe"
    assert seen["docs"][0].metadata == {
        "category": "footwear",
        "price": "89.99",
    }
    assert "Importing 1 document(s)" in result.output
    assert "job-123" in result.output


def test_import_command_supports_repeated_metadata_flags_and_wait(
    monkeypatch, tmp_path
):
    path = tmp_path / "products.csv"
    path.write_text(
        "sku,description,category,price\nA-100,Trail shoe,footwear,89.99\n",
        encoding="utf-8",
    )
    seen = {}
    _install_recording_client(monkeypatch, seen)

    async def fake_wait_for_job(client, job_id, poll_interval, json_mode, timeout):
        seen["wait"] = (job_id, poll_interval, json_mode, timeout)

    monkeypatch.setattr(doc_cmd, "wait_for_job", fake_wait_for_job)

    result = _invoke_import(
        path,
        "--id-column",
        "sku",
        "--text-column",
        "description",
        "--metadata-column",
        "category",
        "--metadata-column",
        "price",
        "--wait",
        "--poll-interval",
        "0.25",
        "--timeout",
        "3",
    )

    assert result.exit_code == 0, result.output
    assert seen["docs"][0].metadata == {
        "category": "footwear",
        "price": "89.99",
    }
    assert seen["wait"] == ("job-123", 0.25, False, 3.0)


def test_import_without_mapping_preserves_standard_metadata(monkeypatch, tmp_path):
    path = tmp_path / "documents.json"
    path.write_text(
        '[{"id":"one","text":"Hello","metadata":{"topic":"intro"}}]',
        encoding="utf-8",
    )
    seen = {}
    _install_recording_client(monkeypatch, seen)

    result = _invoke_import(path)

    assert result.exit_code == 0, result.output
    assert seen["docs"][0].metadata == {"topic": "intro"}


def test_import_json_output_is_machine_readable(monkeypatch, tmp_path):
    path = tmp_path / "documents.json"
    path.write_text('[{"id":"one","text":"Hello"}]', encoding="utf-8")
    seen = {}
    _install_recording_client(monkeypatch, seen)

    result = _invoke_import(path, group="documents", json_output=True)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "job_id": "job-123",
        "index_name": "products",
        "doc_count": 1,
    }


def test_import_rejects_empty_input_before_creating_client(monkeypatch, tmp_path):
    path = tmp_path / "documents.json"
    path.write_text("[]", encoding="utf-8")

    class UnexpectedClient:
        def __init__(self, project_id, project_key):
            raise AssertionError("client should not be created for invalid input")

    monkeypatch.setattr(doc_cmd, "MossClient", UnexpectedClient)

    result = _invoke_import(path, "--metadata-column", "category", group="documents")

    assert result.exit_code != 0
    assert "No documents found in" in result.output


def test_doc_add_remains_backward_compatible(monkeypatch, tmp_path):
    path = tmp_path / "documents.json"
    path.write_text('[{"id":"one","text":"Hello"}]', encoding="utf-8")
    seen = {}
    _install_recording_client(monkeypatch, seen)

    result = runner.invoke(
        app, [*AUTH_OPTIONS, "doc", "add", "products", "-f", str(path)]
    )

    assert result.exit_code == 0, result.output
    assert [(doc.id, doc.text) for doc in seen["docs"]] == [("one", "Hello")]
