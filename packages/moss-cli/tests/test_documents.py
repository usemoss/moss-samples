import pytest
import typer

from moss_cli.documents import _parse_csv_docs


def test_csv_keeps_newlines_inside_quoted_text() -> None:
    docs = _parse_csv_docs('id,text\ndoc1,"line one\nline two"\ndoc2,plain\n')
    assert len(docs) == 2
    assert docs[0].text == "line one\nline two"
    assert docs[1].text == "plain"


def test_csv_parses_metadata_and_embedding_columns() -> None:
    docs = _parse_csv_docs(
        "id,text,metadata,embedding\n"
        'doc1,hello,"{""topic"": ""ml""}","[0.1, 0.2]"\n'
        "doc2,world,,\n"
    )
    assert docs[0].metadata == {"topic": "ml"}
    assert docs[0].embedding == pytest.approx([0.1, 0.2])
    assert docs[1].metadata is None
    assert docs[1].embedding is None


def test_csv_header_is_trimmed() -> None:
    docs = _parse_csv_docs("id , text \ndoc1,hello\n")
    assert docs[0].id == "doc1"
    assert docs[0].text == "hello"


def test_csv_missing_column_reports_header_error() -> None:
    with pytest.raises(typer.BadParameter) as exc:
        _parse_csv_docs("id,body\ndoc1,hello\n")
    assert "text" in str(exc.value)


def test_csv_empty_content_is_rejected() -> None:
    with pytest.raises(typer.BadParameter):
        _parse_csv_docs("")


def test_csv_short_row_is_rejected() -> None:
    with pytest.raises(typer.BadParameter) as exc:
        _parse_csv_docs("id,text\ndoc1\n")
    assert "line 2" in str(exc.value)


def test_csv_invalid_metadata_reports_file_line_number() -> None:
    with pytest.raises(typer.BadParameter) as exc:
        _parse_csv_docs('id,text,metadata\ndoc1,"a\nb",not-json\n')
    assert "line 3" in str(exc.value)
