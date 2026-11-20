"""Measured behaviour from the turns: facts, not model guesses."""
WORDS_PER_SECOND = 2.3        # Egyptian Arabic speech, used when turns have no timestamps


def measure(turns) -> dict:
    turns = [t for t in turns if (t.text or "").strip()]
    if not turns:
        return {}
    timed = any(t.end > 0 for t in turns)
    talk = {"agent": 0.0, "customer": 0.0, "ivr": 0.0, "unknown": 0.0}
    words = {"agent": 0, "customer": 0}
    silences, overlaps, prev_end = [], 0, None
    for t in turns:
        n = len(t.text.split())
        dur = (t.end - t.start) if timed else n / WORDS_PER_SECOND
        talk[t.speaker if t.speaker in talk else "unknown"] += max(dur, 0)
        if t.speaker in words:
            words[t.speaker] += n
        if timed and prev_end is not None:
            gap = t.start - prev_end
            if gap > 0:
                silences.append(gap)
            elif gap < -0.3:
                overlaps += 1
        if timed:
            prev_end = max(prev_end or 0, t.end)
    spoken = talk["agent"] + talk["customer"]
    total = (turns[-1].end - turns[0].start) if timed else sum(talk.values())
    long_silences = [s for s in silences if s >= 5]
    return {
        "timed": timed,
        "duration_s": round(total, 1),
        "turns": len(turns),
        "agent_talk_share": round(talk["agent"] / spoken, 3) if spoken else None,
        "agent_talk_s": round(talk["agent"], 1), "customer_talk_s": round(talk["customer"], 1),
        "agent_words_per_min": round(60 * words["agent"] / talk["agent"], 1) if timed and talk["agent"] > 5 else None,
        "longest_silence_s": round(max(silences), 1) if silences else 0,
        "silences_over_5s": len(long_silences),
        "hold_s": round(sum(long_silences), 1),
        "overlaps": overlaps,
        "customer_turns": sum(t.speaker == "customer" for t in turns),
    }
