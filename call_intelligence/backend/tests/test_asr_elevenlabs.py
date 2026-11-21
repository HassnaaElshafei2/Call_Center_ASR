import math

from callintel.services.asr_elevenlabs import to_turns


def w(text, start, end, spk, lp=-0.1):
    return {"text": text, "start": start, "end": end, "type": "word", "speaker_id": spk, "logprob": lp}


def sp(start):
    return {"text": " ", "start": start, "end": start, "type": "spacing", "speaker_id": None}


def test_words_grouped_into_turns_by_speaker_and_pause():
    body = {"words": [
        w("أهلاً", 0.0, 0.4, "speaker_0"), sp(0.4), w("بيك", 0.5, 0.8, "speaker_0"),
        {"text": "(laughter)", "start": 0.8, "end": 1.0, "type": "audio_event", "speaker_id": "speaker_0"},
        w("عايز", 1.2, 1.5, "speaker_1"), sp(1.5), w("ألغي", 1.6, 2.0, "speaker_1"),
        w("لحظة", 5.0, 5.4, "speaker_1"),          # long pause -> new turn, same speaker
    ]}
    out = to_turns(body, "scribe_v1")
    assert [(t["speaker"], t["text"]) for t in out["turns"]] == [
        ("speaker_0", "أهلاً بيك"), ("speaker_1", "عايز ألغي"), ("speaker_1", "لحظة")]
    assert out["turns"][1]["start"] == 1.2 and out["turns"][1]["end"] == 2.0
    assert abs(out["turns"][0]["confidence"] - math.exp(-0.1)) < 1e-3
    assert out["duration"] == 5.4 and out["model"] == "ElevenLabs scribe_v1"


def test_multichannel_answer():
    body = {"transcripts": [
        {"channel_index": 0, "words": [w("ألو", 0.0, 0.3, None)]},
        {"channel_index": 1, "words": [w("أيوه", 0.5, 0.9, None)]}]}
    out = to_turns(body)
    assert [(t["speaker"], t["text"]) for t in out["turns"]] == [("channel_0", "ألو"), ("channel_1", "أيوه")]
