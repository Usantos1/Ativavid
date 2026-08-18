"""Cache de transcrição invalida quando o arquivo fonte muda."""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HELPERS = REPO / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
from transcribe import transcript_cache_hit, write_source_signature


def test_same_source_hits(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"AAAA")
    out = tmp_path / "clip.json"
    out.write_text("{}", encoding="utf-8")
    write_source_signature(tmp_path, video)
    assert transcript_cache_hit(out, video) is True


def test_replaced_source_misses(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"AAAA")
    out = tmp_path / "clip.json"
    out.write_text("{}", encoding="utf-8")
    write_source_signature(tmp_path, video)
    time.sleep(1.05)
    video.write_bytes(b"BBBBBB")
    assert transcript_cache_hit(out, video) is False


def test_missing_transcript_misses(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"AAAA")
    assert transcript_cache_hit(tmp_path / "clip.json", video) is False


def test_legacy_source_without_signature_hits_and_adopts(tmp_path: Path):
    # Fonte não muda depois do import: transcript pré-1.88 (sem .srcsig)
    # é aproveitado e a assinatura atual é adotada.
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"AAAA")
    out = tmp_path / "clip.json"
    out.write_text("{}", encoding="utf-8")
    assert transcript_cache_hit(out, video) is True
    assert (tmp_path / "clip.srcsig").exists()


def test_legacy_cut_without_signature_misses(tmp_path: Path):
    # cut.mp4 é regravado a cada render: transcript de cut sem assinatura
    # pode ser de um corte antigo — nunca confiar (bug da legenda velha).
    video = tmp_path / "cut.mp4"
    video.write_bytes(b"AAAA")
    out = tmp_path / "cut.json"
    out.write_text("{}", encoding="utf-8")
    assert transcript_cache_hit(out, video) is False
