import codecs

import pytest

from app.services.file_processor import FileProcessor


def test_sparse_utf8_characters_take_precedence_over_a_legacy_guess(tmp_path, monkeypatch):
    path = tmp_path / "themes.csv"
    path.write_bytes("id,name\n1,Western\u00a0\n2,Western\n".encode())
    monkeypatch.setattr(
        "app.services.file_processor.chardet.detect",
        lambda _sample: {"encoding": "ISO-8859-1", "confidence": 0.99},
    )
    processor = FileProcessor()

    assert processor._detect_encoding(str(path)) == "utf-8"
    frame, truncated = processor._read_file_ex(str(path), ".csv")

    assert frame["name"].to_list() == ["Western", "Western"]
    assert not truncated


def test_windows_1252_currency_accents_and_quotes_use_legacy_fallback(tmp_path):
    path = tmp_path / "customers.csv"
    value = "Café £ “special”"
    path.write_bytes(f"id,name\n1,{value}\n".encode("cp1252"))
    processor = FileProcessor()

    encoding = processor._detect_encoding(str(path))
    frame, _truncated = processor._read_file_ex(str(path), ".csv")

    assert encoding.lower() != "utf-8"
    assert frame["name"].to_list() == [value]


@pytest.mark.parametrize(
    "marker,source_encoding,expected",
    [
        (codecs.BOM_UTF8, "utf-8", "utf-8-sig"),
        (codecs.BOM_UTF16_LE, "utf-16-le", "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16-be", "utf-16"),
        (codecs.BOM_UTF32_LE, "utf-32-le", "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32-be", "utf-32"),
    ],
)
def test_bom_marked_files_preserve_encoding_and_remove_bom_from_headers(
    tmp_path, monkeypatch, marker, source_encoding, expected
):
    path = tmp_path / "bom.csv"
    path.write_bytes(marker + "id,name\n1,Café\n".encode(source_encoding))
    monkeypatch.setattr(
        "app.services.file_processor.chardet.detect",
        lambda _sample: {"encoding": "ISO-8859-1", "confidence": 0.99},
    )
    processor = FileProcessor()

    assert processor._detect_encoding(str(path)) == expected
    frame, _truncated = processor._read_file_ex(str(path), ".csv")

    assert frame.columns == ["id", "name"]
    assert frame["name"].to_list() == ["Café"]


def test_utf8_character_split_at_validation_chunk_boundary_is_preserved(tmp_path):
    path = tmp_path / "boundary.csv"
    prefix = b"id,name\n1,"
    path.write_bytes(prefix + b"A" * (128_000 - len(prefix) - 1) + "é\n".encode())
    processor = FileProcessor()

    assert processor._detect_encoding(str(path)) == "utf-8"
    frame, _truncated = processor._read_file_ex(str(path), ".csv")

    assert frame["name"][0].endswith("é")
    assert "\ufffd" not in frame["name"][0]


def test_legacy_character_after_initial_sample_is_detected(tmp_path, monkeypatch):
    path = tmp_path / "late-legacy.csv"
    path.write_bytes(b"id,name\n" + b"1,ASCII\n" * 20_000 + "2,Café £\n".encode("cp1252"))
    samples = []

    def detect(sample):
        samples.append(sample)
        assert b"\xa3" in sample
        return {"encoding": "cp1252", "confidence": 0.99}

    monkeypatch.setattr("app.services.file_processor.chardet.detect", detect)
    processor = FileProcessor()

    assert processor._detect_encoding(str(path)) == "cp1252"
    frame, _truncated = processor._read_file_ex(str(path), ".csv")

    assert samples
    assert frame["name"][-1] == "Café £"


def test_incomplete_utf8_character_at_end_uses_legacy_fallback(tmp_path, monkeypatch):
    path = tmp_path / "incomplete.csv"
    path.write_bytes(b"id,name\n" + b"1,ASCII\n" * 20_000 + b"2,\xc3")

    def detect(sample):
        assert b"\xc3" in sample
        return {"encoding": "cp1252", "confidence": 0.99}

    monkeypatch.setattr("app.services.file_processor.chardet.detect", detect)

    assert FileProcessor()._detect_encoding(str(path)) == "cp1252"


def test_nul_marked_files_use_encoding_detector(tmp_path, monkeypatch):
    path = tmp_path / "without-bom.csv"
    path.write_bytes("id,name\n1,Cafe\n".encode("utf-16-le"))
    samples = []

    def detect(sample):
        samples.append(sample)
        return {"encoding": "utf-16-le", "confidence": 0.99}

    monkeypatch.setattr("app.services.file_processor.chardet.detect", detect)
    processor = FileProcessor()

    assert processor._detect_encoding(str(path)) == "utf-16-le"
    frame, _truncated = processor._read_file_ex(str(path), ".csv")

    assert samples and b"\x00" in samples[0]
    assert frame.columns == ["id", "name"]
    assert frame["name"].to_list() == ["Cafe"]
