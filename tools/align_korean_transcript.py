import argparse
import re
import textwrap
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import List

import srt


MIN_DUR = 1.0
MAX_DUR = 7.0
GAP = 0.08
MAX_CHARS = 40
MAX_LINE = 22
DEFAULT_SPEAKER = "Mark Ritchie"
SPEAKER_LABELS = {
    "Mark Ritchie": "마크 리치",
    "Mark Minervini": "마크 미너비니",
    "Brandon": "브랜든",
    "Bob Weisman": "밥 와이스먼",
    "Questioner": "질문자",
}
SPEAKER_ALIASES = {
    "bob": "Bob Weisman",
    "bob weisman": "Bob Weisman",
    "밥 와이스먼": "Bob Weisman",
    "mark richie": "Mark Ritchie",
    "mark ritchie": "Mark Ritchie",
    "마크 리치": "Mark Ritchie",
    "mark minervini": "Mark Minervini",
    "마크 미너비니": "Mark Minervini",
    "brandon": "Brandon",
    "브랜든": "Brandon",
    "questioner": "Questioner",
    "질문자": "Questioner",
}
QUESTION_START_PATTERNS = (
    r"\basking about\b",
    r"\basking opinion on\b",
    r"\bquestion is asking\b",
    r"\bmy question\b",
    r"\bam i\b",
    r"\bi feel\b",
    r"\bif you're buying\b",
    r"\blooking also\b",
    r"\bcan you critique\b",
    r"\basking thoughts on\b",
)
QUESTION_END_PATTERNS = (
    r"\bthe first thing\b",
    r"\blisten\b",
    r"\bmy answer\b",
    r"\bi would say\b",
    r"\byeah\b",
    r"\bto your answer\b",
)
BRANDON_START_PATTERNS = (
    r"\bbrandon\?\b",
    r"\bbrandon, you want to\b",
    r"\bbrandon, are you reading\b",
    r"\bshort term trader brandon\b",
    r"\bi'll add\b",
    r"\bto mark's point\b",
    r"\bmark had asked me\b",
    r"\bmark i\b",
)
MARK_START_PATTERNS = (
    r"\bto brandon's point\b",
    r"\bas brandon said\b",
    r"\bbrandon pretty much covered it all\b",
    r"\bthe other one he was asking\b",
    r"\bwhat he was asking\b",
)


@dataclass
class TranscriptEntry:
    start: timedelta
    text: str
    speaker: str | None


@dataclass
class CaptionChunk:
    start: timedelta
    end: timedelta
    text: str
    speaker: str


def parse_timecode(raw: str) -> timedelta:
    parts = [int(part) for part in raw.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        hours = 0
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"Unsupported timecode: {raw}")
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def normalize_speaker(raw: str) -> str | None:
    key = raw.strip().rstrip(":").lower()
    return SPEAKER_ALIASES.get(key)


def strip_inline_speaker(text: str) -> tuple[str, str | None]:
    for pattern, speaker in (
        (r"^(브랜든|Brandon):?\s*", "Brandon"),
        (r"^(마크 리치|Mark Ritchie|Mark Richie):?\s*", "Mark Ritchie"),
        (r"^(마크 미너비니|Mark Minervini):?\s*", "Mark Minervini"),
        (r"^(밥 와이스먼|Bob Weisman|Bob):?\s*", "Bob Weisman"),
        (r"^(질문자|Questioner):?\s*", "Questioner"),
    ):
        if re.match(pattern, text, flags=re.IGNORECASE):
            return re.sub(pattern, "", text, flags=re.IGNORECASE).strip(), speaker
    return text, None


def parse_transcript(path: str) -> List[TranscriptEntry]:
    pattern = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$")
    entries: List[TranscriptEntry] = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip().lstrip("\ufeff")
            if not line:
                continue
            match = pattern.match(line)
            if not match:
                continue
            speaker = None
            text = match.group(2).strip()
            bracket_speaker = re.match(r"^\[(.+?)\]\s*(.+)$", text)
            if bracket_speaker:
                speaker = normalize_speaker(bracket_speaker.group(1))
                text = bracket_speaker.group(2).strip()
            text, inline_speaker = strip_inline_speaker(text)
            speaker = speaker or inline_speaker
            entries.append(TranscriptEntry(parse_timecode(match.group(1)), text, speaker))
    if not entries:
        raise SystemExit("No transcript entries were found.")
    return entries


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\n", " ").strip())


def infer_default_speaker(video_title: str | None, source_srt: str) -> str:
    haystack = " ".join(part for part in [video_title or "", source_srt] if part).lower()
    if "mark minervini" in haystack:
        return "Mark Minervini"
    if "mark ritchie" in haystack:
        return "Mark Ritchie"
    return DEFAULT_SPEAKER


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def infer_speakers(subs: List[srt.Subtitle], default_speaker: str) -> List[str]:
    speakers: List[str] = []
    current_speaker = default_speaker
    in_question = False

    for sub in subs:
        text = normalize_text(sub.content).lower()

        if matches_any(text, QUESTION_START_PATTERNS):
            in_question = True
        if in_question and matches_any(text, QUESTION_END_PATTERNS):
            in_question = False
            current_speaker = default_speaker

        if in_question:
            speakers.append("Questioner")
            continue

        if matches_any(text, BRANDON_START_PATTERNS):
            current_speaker = "Brandon"
        elif matches_any(text, MARK_START_PATTERNS):
            current_speaker = "Mark Ritchie"

        speakers.append(current_speaker)

    return speakers


def split_clauses(text: str) -> List[str]:
    text = normalize_text(text)
    if not text:
        return []

    parts = re.split(r"(?<=[.!?])\s+|(?<=[다요죠니다])\s+", text)
    clauses: List[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= MAX_CHARS:
            clauses.append(part)
            continue

        subparts = re.split(r"(?<=[,;:])\s+|(?<=\))\s+|(?<=\])\s+", part)
        buffer = ""
        for subpart in subparts:
            subpart = subpart.strip()
            if not subpart:
                continue
            proposal = f"{buffer} {subpart}".strip()
            if buffer and len(proposal) > MAX_CHARS:
                clauses.append(buffer)
                buffer = subpart
            else:
                buffer = proposal
        if buffer:
            clauses.append(buffer)
    return clauses


def pack_clauses(clauses: List[str]) -> List[str]:
    captions: List[str] = []
    buffer = ""
    for clause in clauses:
        proposal = f"{buffer} {clause}".strip()
        if buffer and len(proposal) > MAX_CHARS:
            captions.append(buffer)
            buffer = clause
        else:
            buffer = proposal
    if buffer:
        captions.append(buffer)
    return captions or [""]


def wrap_caption(text: str) -> List[str]:
    wrapped = textwrap.wrap(
        text,
        width=MAX_LINE,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not wrapped:
        return [""]

    blocks: List[str] = []
    start_index = 0
    if len(wrapped) > 1 and len(wrapped) % 2 == 1:
        blocks.append(wrapped[0])
        start_index = 1
    blocks.extend("\n".join(wrapped[index:index + 2]) for index in range(start_index, len(wrapped), 2))
    return blocks


def dominant_speaker(speakers: List[str]) -> str:
    if not speakers:
        return DEFAULT_SPEAKER
    counts = Counter(speakers)
    return counts.most_common(1)[0][0]


def infer_entry_speaker(
    entry: TranscriptEntry,
    dominant: str,
    previous: str,
    default_speaker: str,
) -> str:
    if entry.speaker:
        return entry.speaker
    return previous or dominant or default_speaker


def build_chunks(
    entries: List[TranscriptEntry],
    subs: List[srt.Subtitle],
    speakers: List[str],
    default_speaker: str,
) -> List[CaptionChunk]:
    chunks: List[CaptionChunk] = []
    last_end = subs[-1].end if subs else timedelta()
    previous_speaker = default_speaker

    for index, entry in enumerate(entries):
        next_start = entries[index + 1].start if index + 1 < len(entries) else last_end
        seg_subs: List[srt.Subtitle] = []
        seg_speakers: List[str] = []
        for sub, speaker in zip(subs, speakers):
            if entry.start <= sub.start < next_start:
                seg_subs.append(sub)
                seg_speakers.append(speaker)

        seg_start = seg_subs[0].start if seg_subs else entry.start
        seg_end = seg_subs[-1].end if seg_subs else next_start
        if seg_end <= seg_start:
            seg_end = seg_start + timedelta(seconds=MIN_DUR)
        seg_speaker = infer_entry_speaker(entry, dominant_speaker(seg_speakers), previous_speaker, default_speaker)
        previous_speaker = seg_speaker

        pieces = pack_clauses(split_clauses(entry.text))
        duration = max(MIN_DUR, (seg_end - seg_start).total_seconds())
        weights = [max(1, len(piece.replace(" ", ""))) for piece in pieces]
        total_weight = sum(weights)
        cursor = seg_start

        for piece_index, piece in enumerate(pieces):
            remaining = (seg_end - cursor).total_seconds()
            if piece_index == len(pieces) - 1:
                piece_end = seg_end
            else:
                fraction = weights[piece_index] / total_weight
                alloc = max(MIN_DUR, duration * fraction)
                min_future = MIN_DUR * (len(pieces) - piece_index - 1)
                alloc = min(alloc, max(MIN_DUR, remaining - min_future))
                piece_end = cursor + timedelta(seconds=alloc)

            display_blocks = wrap_caption(piece)
            block_weights = [
                max(1, len(block.replace("\n", "").replace(" ", "")))
                for block in display_blocks
            ]
            block_total_weight = sum(block_weights)
            block_cursor = cursor
            piece_duration = max(MIN_DUR, (piece_end - cursor).total_seconds())

            for block_index, block in enumerate(display_blocks):
                block_remaining = (piece_end - block_cursor).total_seconds()
                if block_index == len(display_blocks) - 1:
                    block_end = piece_end
                else:
                    block_fraction = block_weights[block_index] / block_total_weight
                    block_alloc = max(MIN_DUR, piece_duration * block_fraction)
                    min_future = MIN_DUR * (len(display_blocks) - block_index - 1)
                    block_alloc = min(block_alloc, max(MIN_DUR, block_remaining - min_future))
                    block_end = block_cursor + timedelta(seconds=block_alloc)

                chunks.append(CaptionChunk(block_cursor, block_end, block, seg_speaker))
                block_cursor = block_end + timedelta(seconds=GAP)

            cursor = piece_end + timedelta(seconds=GAP)

    return chunks


def apply_speaker_labels(chunks: List[CaptionChunk]) -> List[srt.Subtitle]:
    out: List[srt.Subtitle] = []
    previous_speaker = ""
    for index, chunk in enumerate(chunks, start=1):
        text = chunk.text
        label = SPEAKER_LABELS.get(chunk.speaker, "")
        if label and label != previous_speaker:
            first_line, *rest = text.splitlines()
            text = "\n".join([f"{label}: {first_line}"] + rest)
            previous_speaker = label
        elif label:
            previous_speaker = label
        out.append(srt.Subtitle(index=index, start=chunk.start, end=chunk.end, content=text))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", help="Korean transcript with coarse timestamps")
    parser.add_argument("--source-srt", default="en.srt")
    parser.add_argument("--video-title", default="")
    parser.add_argument("-o", "--output", default="ko.from_gemini.srt")
    args = parser.parse_args()

    entries = parse_transcript(args.transcript)
    with open(args.source_srt, "r", encoding="utf-8", errors="ignore") as handle:
        subs = list(srt.parse(handle.read()))
    default_speaker = infer_default_speaker(args.video_title, args.source_srt)
    speakers = infer_speakers(subs, default_speaker)
    chunks = build_chunks(entries, subs, speakers, default_speaker)
    labeled = apply_speaker_labels(chunks)

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(srt.compose(labeled))

    print(f"Wrote {args.output} (captions={len(labeled)})")


if __name__ == "__main__":
    main()
