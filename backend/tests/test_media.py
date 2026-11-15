import io
import numpy as np
import pytest
from fastapi import UploadFile
from app.ai import speech_analyzer
from app.ai.scene_detector import detect_scenes
from app.ai.scene_scorer import ScoringWeights, score_scenes
from app.ai.video_perception import analyze_scene_visuals, hist_distance
from app.core.audio_processor import compute_keep_intervals, detect_silence, invert_intervals, load_audio_mono, rms_db
from app.core.file_validation import ValidationError, validate_name_and_mime, validate_video_content
from app.core.process import MediaError, run_media
from app.core.video_metadata import extract_metadata
from app.rendering.subtitle_renderer import build_ass, build_cues, clip_timeline, output_duration, resolve_font, to_srt
from app.utils.file_utils import ensure_within, safe_filename


def test_metadata_extraction(video_path, silent_video_path):
    m = extract_metadata(video_path)
    assert (m["width"], m["height"]) == (640, 360) and m["fps"] == 25.0 and abs(m["duration"] - 12.0) < 0.2
    assert m["video_codec"] == "h264" and m["audio_codec"] == "aac" and m["has_audio"]
    assert extract_metadata(silent_video_path)["has_audio"] is False


def test_metadata_rejects_non_media(tmp_path):
    f = tmp_path / "x.mp4"; f.write_bytes(b"not a video at all" * 100)
    with pytest.raises(ValidationError):
        validate_video_content(f)


def test_silence_detection_timestamps(video_path):
    sil = detect_silence(video_path, 12.0)
    assert len(sil) == 2
    assert abs(sil[0][0] - 3.0) < 0.15 and abs(sil[0][1] - 4.5) < 0.15
    assert abs(sil[1][0] - 7.5) < 0.15 and abs(sil[1][1] - 9.0) < 0.15
    act = invert_intervals(sil, 12.0)
    assert len(act) == 3 and abs(sum(b - a for a, b in act) + sum(b - a for a, b in sil) - 12.0) < 1e-6


def test_loudness_distinguishes_tone_and_silence(video_path):
    s = load_audio_mono(video_path)
    assert rms_db(s, 16000, 0.5, 2.5) > -30 and rms_db(s, 16000, 3.5, 4.2) < -60


def test_keep_intervals_pad_and_never_drop_quiet_speech():
    keep = compute_keep_intervals(0, 10, [(1.0, 3.0)], [], pad=0.2)
    assert keep == [(0.8, 3.2)]
    # quiet speech (no audio activity) present in the transcript is retained
    keep2 = compute_keep_intervals(0, 10, [(1.0, 3.0)], [(5.0, 6.0)], pad=0.2)
    assert (4.8, 6.2) in keep2 and len(keep2) == 2
    assert compute_keep_intervals(0, 10, [], [], 0.2) == []   # entirely silent scene


def test_scene_detection_finds_hard_cuts(video_path):
    sil = [tuple(x) for x in detect_silence(video_path, 12.0)]
    r = detect_scenes(video_path, 12.0, sil)
    sc = r["scenes"]
    assert len(sc) == 3
    for (a, b), s in zip([(0, 4), (4, 8), (8, 12)], sc):
        assert abs(s["start"] - a) < 0.2 and abs(s["end"] - b) < 0.2
    assert sc[0]["start"] == 0.0 and abs(sc[-1]["end"] - 12.0) < 1e-6
    assert all(x["end"] > x["start"] for x in sc) and all(sc[i]["end"] == sc[i + 1]["start"] for i in range(2))


def test_long_scene_is_split_at_pauses(tmp_path, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_scene_seconds", 5.0)
    monkeypatch.setattr("app.ai.scene_detector.detect_cuts", lambda p, t: [(0.0, 12.0)])
    r = detect_scenes(tmp_path / "x.mp4", 12.0, [(3.0, 4.5), (7.5, 9.0)])
    assert len(r["scenes"]) >= 3 and all(s["end"] - s["start"] <= 5.01 for s in r["scenes"])
    assert any(s["boundary_method"] == "pause" for s in r["scenes"])


def test_visual_features_are_measured(video_path, tmp_path):
    scenes = [{"scene_id": 0, "start": 0, "end": 4}, {"scene_id": 1, "start": 4, "end": 8}, {"scene_id": 2, "start": 8, "end": 12}]
    v = analyze_scene_visuals(video_path, scenes, tmp_path / "t", 25)
    assert v[0]["motion"] < 0.001 and v[2]["motion"] < 0.001      # flat colour: no motion
    assert v[1]["motion"] > 0.003                                  # testsrc2 moves
    assert all((tmp_path / "t" / x["thumbnail"]).exists() for x in v)
    d01 = hist_distance(v[0]["sig_mean"], v[1]["sig_mean"]); d02 = hist_distance(v[0]["sig_mean"], v[0]["sig_mean"])
    assert d01 > 0.3 and d02 < 1e-6
    assert 0 <= v[1]["focus_x"] <= 1


def _scenes():
    return [{"transcript": "intro greeting hello", "speech_density": 0.5, "motion": 0.01, "sig_mean": [1] + [0] * 127},
            {"transcript": "machine learning models learn patterns from data machine learning", "speech_density": 0.9, "motion": 0.05, "sig_mean": [0, 1] + [0] * 126},
            {"transcript": "", "speech_density": 0.1, "motion": 0.02, "sig_mean": [0, 0, 1] + [0] * 125}]


def test_scoring_range_ranking_and_explanations():
    sc = score_scenes(_scenes(), topic="machine learning")
    assert all(0 <= s["importance"] <= 100 for s in sc)
    assert max(sc, key=lambda s: s["importance"]) is sc[1]
    assert "contributed" in sc[1]["score_detail"]["explanation"]
    assert abs(sum(sc[1]["score_detail"]["weights_used"].values()) - 1) < 1e-3


def test_missing_features_are_excluded_not_treated_as_perfect():
    sc = score_scenes(_scenes(), topic=None)       # no topic -> topic_relevance missing
    assert "topic_relevance" in sc[0]["score_detail"]["missing"]
    assert "topic_relevance" not in sc[0]["score_detail"]["weights_used"]
    assert "renormalised" in sc[0]["score_detail"]["explanation"]
    nt = [{**s, "transcript": ""} for s in _scenes()]
    sc2 = score_scenes(nt)
    assert "speech_relevance" in sc2[0]["score_detail"]["missing"]


def test_weights_are_configurable():
    a = score_scenes(_scenes(), weights=ScoringWeights(speech_relevance=1, speech_activity=0, visual_activity=0, distinctiveness=0, topic_relevance=0))
    assert set(a[0]["score_detail"]["weights_used"]) == {"speech_relevance"}
    with pytest.raises(ValueError):
        ScoringWeights(speech_relevance=0, speech_activity=0, visual_activity=0, distinctiveness=0, topic_relevance=0)


# ---------- transcription integration (third-party model stubbed: no network in tests) ----------
def test_whisper_unavailable_is_reported_not_faked(monkeypatch, video_path):
    import faster_whisper
    def boom(*a, **k): raise OSError("cannot download model")
    monkeypatch.setattr(faster_whisper, "WhisperModel", boom)
    speech_analyzer._MODEL_CACHE.clear()
    r = speech_analyzer.transcribe_whisper(video_path)
    assert r["status"] == "unavailable" and r["segments"] == [] and "cannot download" in r["message"]


def test_whisper_result_mapping(monkeypatch, video_path):
    import faster_whisper
    class W:  # minimal stand-ins for faster-whisper's objects
        def __init__(s, w, st, en): s.word, s.start, s.end = w, st, en
    class Seg:
        def __init__(s): s.start, s.end, s.text, s.words = 0.5, 2.0, " hello world", [W(" hello", 0.5, 1.0), W(" world", 1.1, 2.0)]
    class Info: language = "en"
    class M:
        def __init__(s, *a, **k): pass
        def transcribe(s, path, **k): return iter([Seg()]), Info()
    monkeypatch.setattr(faster_whisper, "WhisperModel", M)
    speech_analyzer._MODEL_CACHE.clear()
    r = speech_analyzer.transcribe_whisper(video_path)
    assert r["status"] == "ok" and r["language"] == "en" and r["segments"][0]["words"][1] == {"w": "world", "start": 1.1, "end": 2.0}
    speech_analyzer._MODEL_CACHE.clear()


def test_srt_import_roundtrip():
    from tests.conftest import SRT
    segs = speech_analyzer.parse_srt(SRT)
    assert len(segs) == 3 and segs[1]["start"] == 4.6 and segs[1]["end"] == 7.4 and "important scenes" in segs[1]["text"]
    assert speech_analyzer.parse_srt("garbage") == []


# ---------- subtitles ----------
CLIPS = [{"scene_id": 0, "duration": 4.0, "segments": [{"start": 2.0, "end": 6.0}], "transition_in": {"duration": 0.0}},
         {"scene_id": 1, "duration": 3.0, "segments": [{"start": 10.0, "end": 13.0}], "transition_in": {"duration": 0.5}}]
TR = [{"start": 1.0, "end": 5.0, "text": "hello this is a test of subtitles", "words": []},
      {"start": 10.5, "end": 12.5, "text": "second clip text here now", "words": []}]


def test_subtitle_timeline_mapping_and_validity():
    assert output_duration(CLIPS) == 6.5
    tl = clip_timeline(CLIPS)
    assert tl[1]["out_start"] == 3.5
    cues = build_cues(TR, CLIPS)
    assert cues and all(0 <= c["start"] < c["end"] <= 6.5 + 1e-6 for c in cues)
    assert all(cues[i]["end"] <= cues[i + 1]["start"] + 1e-9 for i in range(len(cues) - 1))
    assert not any("hello" in c["text"] for c in cues), "words before the kept segment must be cut"
    srt = to_srt(cues)
    assert "-->" in srt and srt.startswith("1\n")


def test_ass_generation_styles_and_unicode():
    cues = [{"start": 0.0, "end": 1.0, "text": "નમસ્તે hello", "words": [{"w": "નમસ્તે", "start": 0.0, "end": 0.5}, {"w": "hello", "start": 0.5, "end": 1.0}]}]
    for style in ("classic", "bold", "animated", "karaoke"):
        ass, warn = build_ass(cues, 720, 1280, style, 60, "#FF8800", 0.72)
        assert "PlayResX: 720" in ass and "નમસ્તે" in ass and "Dialogue:" in ass
    k, _ = build_ass(cues, 720, 1280, "karaoke", 60, "#FFFFFF", 0.72)
    assert "\\kf" in k
    font, warn = resolve_font("નમસ્તે")
    assert warn is None or "Gujarati font" in warn      # honest warning when no Gujarati font is installed


# ---------- file validation / security ----------
def test_safe_filename_and_path_guard(tmp_path):
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("a b;rm -rf.mp4") == "a_b_rm_-rf.mp4"
    with pytest.raises(ValueError):
        ensure_within(tmp_path, tmp_path / ".." / "x")


def test_upload_name_and_mime_validation():
    ok = UploadFile(filename="clip.MP4", file=io.BytesIO(b"x"), headers={"content-type": "video/mp4"})
    assert validate_name_and_mime(ok) == "clip.MP4"
    with pytest.raises(ValidationError):
        validate_name_and_mime(UploadFile(filename="x.exe", file=io.BytesIO(b"x")))
    with pytest.raises(ValidationError):
        validate_name_and_mime(UploadFile(filename="x.mp4", file=io.BytesIO(b"x"), headers={"content-type": "text/html"}))


def test_only_media_binaries_may_run():
    with pytest.raises(MediaError):
        run_media(["bash", "-c", "echo hi"], timeout=5)
    with pytest.raises(MediaError):
        run_media(["/bin/ls"], timeout=5)
