import argparse
import json
import os
import re
import textwrap
from datetime import timedelta
from typing import List

import deepl
import srt
import torch
from deep_translator import GoogleTranslator
from openai import OpenAI, RateLimitError
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


CPS = 14.0
MIN_DUR = 1.0
MAX_DUR = 7.0
GAP = 0.10
DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_SPEAKER = "Mark Ritchie"
KOREAN_SPEAKER_LABELS = {
    "Mark Ritchie": "마크리치",
    "Brandon": "브랜든",
    "Questioner": "질문자",
}


class Segment:
    def __init__(self, start: timedelta, end: timedelta, text: str, speaker: str) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.speaker = speaker


GEMINI_SYS_PROMPT = (
    "You are a Korean subtitle writer for finance and stock-market Q&A video. "
    "Translate each English segment into natural Korean broadcast-style subtitles. "
    "Preserve ticker symbols in uppercase. Keep the tone polite and natural. "
    "When the speaker changes, we add labels separately, so return only translated text. "
    "Use concise idiomatic Korean and avoid literal phrasing."
)
QUESTION_START_PATTERNS = (
    r"\basking about\b",
    r"\basking opinion on\b",
    r"\bquestion is asking\b",
    r"\bmy question\b",
    r"\bam i\b",
    r"\bi feel\b",
    r"\bif you're buying\b",
    r"\blooking also\b",
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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\n", " ").strip())


def wrap_2lines(text: str, width: int = 22) -> str:
    chunks: List[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        chunks.extend(
            textwrap.wrap(
                paragraph,
                width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    if len(chunks) <= 2:
        return "\n".join(chunks)
    merged = " ".join(chunks)
    final_chunks = textwrap.wrap(
        merged,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\n".join(final_chunks[:2])


def retime_segments(segments: List[Segment], ko_texts: List[str]) -> List[srt.Subtitle]:
    out: List[srt.Subtitle] = []
    for index, (segment, ko_text) in enumerate(zip(segments, ko_texts), start=1):
        start = segment.start
        char_count = len(ko_text.replace("\n", ""))
        needed = max(MIN_DUR, min(MAX_DUR, char_count / CPS))
        source_duration = max(MIN_DUR, (segment.end - segment.start).total_seconds())
        target_duration = max(needed, min(MAX_DUR, source_duration))
        if index < len(segments):
            next_start = segments[index].start
            allowed = (next_start - timedelta(seconds=GAP)) - start
            duration = timedelta(seconds=MIN_DUR) if allowed.total_seconds() < MIN_DUR else min(timedelta(seconds=target_duration), allowed)
        else:
            duration = timedelta(seconds=target_duration)
        out.append(srt.Subtitle(index=index, start=start, end=start + duration, content=ko_text))
    return out


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def infer_speakers(subs: List[srt.Subtitle]) -> List[str]:
    speakers: List[str] = []
    current_speaker = DEFAULT_SPEAKER
    in_question = False

    for sub in subs:
        text = normalize_text(sub.content).lower()

        if matches_any(text, QUESTION_START_PATTERNS):
            in_question = True
        if in_question and matches_any(text, QUESTION_END_PATTERNS):
            in_question = False
            current_speaker = DEFAULT_SPEAKER

        if in_question:
            speakers.append("Questioner")
            continue

        if matches_any(text, BRANDON_START_PATTERNS):
            current_speaker = "Brandon"
        elif matches_any(text, MARK_START_PATTERNS):
            current_speaker = "Mark Ritchie"
        elif text.startswith("yeah") and current_speaker == "Brandon":
            current_speaker = "Brandon"
        elif text.startswith("yeah") and current_speaker == "Mark Ritchie":
            current_speaker = "Mark Ritchie"

        speakers.append(current_speaker)

    return speakers


def build_segments(subs: List[srt.Subtitle], speakers: List[str]) -> List[Segment]:
    segments: List[Segment] = []
    current_texts: List[str] = []
    current_start: timedelta | None = None
    current_end: timedelta | None = None
    current_speaker = ""

    def flush() -> None:
        nonlocal current_texts, current_start, current_end, current_speaker
        if not current_texts or current_start is None or current_end is None:
            return
        text = " ".join(current_texts).strip()
        segments.append(Segment(current_start, current_end, text, current_speaker))
        current_texts = []
        current_start = None
        current_end = None
        current_speaker = ""

    for sub, speaker in zip(subs, speakers):
        text = normalize_text(sub.content)
        if not text:
            continue

        if current_start is None:
            current_start = sub.start
            current_end = sub.end
            current_speaker = speaker
            current_texts = [text]
            continue

        gap = (sub.start - current_end).total_seconds() if current_end else 0.0
        merged_text = " ".join(current_texts)
        should_split = (
            speaker != current_speaker
            or gap > 0.75
        )
        if should_split:
            flush()
            current_start = sub.start
            current_end = sub.end
            current_speaker = speaker
            current_texts = [text]
            continue

        current_texts.append(text)
        current_end = sub.end
        merged_text = " ".join(current_texts)
        if (text.endswith((".", "?", "!")) and len(merged_text) > 80) or len(merged_text) > 340 or len(current_texts) >= 14:
            flush()

    flush()
    return segments


def clean_translation(text: str) -> str:
    text = text.strip()
    text = text.replace(" ,", ",").replace(" .", ".")
    text = re.sub(r"\s+([,.:;?!])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_tickers(text: str) -> List[str]:
    compact = re.sub(r"\b([A-Z]{2,4})\s+([A-Z])\b", r"\1\2", text)
    compact = re.sub(r"\b(?:[A-Z]\s+){1,4}[A-Z]\b", lambda match: match.group(0).replace(" ", ""), compact)
    return sorted(set(re.findall(r"\b[A-Z]{2,5}\b", compact)))


def ensure_tickers(source: str, translated: str) -> str:
    tickers = [ticker for ticker in extract_tickers(source) if ticker not in {"Q", "A"}]
    if not tickers:
        return translated
    missing = [ticker for ticker in tickers if ticker not in translated]
    if not missing:
        return translated
    prefix = " / ".join(missing)
    return f"{prefix} {translated}"


class LocalTranslator:
    def __init__(self, model_name: str) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, src_lang="eng_Latn")
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        self.model.eval()
        self.target_lang_id = self.tokenizer.convert_tokens_to_ids("kor_Hang")

    def translate_batch(self, texts: List[str], max_length: int = 256) -> List[str]:
        with torch.inference_mode():
            encoded = self.tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            )
            generated = self.model.generate(
                **encoded,
                forced_bos_token_id=self.target_lang_id,
                max_length=max_length,
                num_beams=4,
                length_penalty=0.9,
            )
        decoded = self.tokenizer.batch_decode(generated, skip_special_tokens=True)
        return [clean_translation(text) for text in decoded]


class GoogleWebTranslator:
    def __init__(self, fallback_model: str) -> None:
        self.translator = GoogleTranslator(source="en", target="ko")
        self.fallback_model = fallback_model
        self.local_fallback: LocalTranslator | None = None

    def get_local_fallback(self) -> LocalTranslator:
        if self.local_fallback is None:
            self.local_fallback = LocalTranslator(self.fallback_model)
        return self.local_fallback

    def translate_batch(self, texts: List[str], max_length: int = 256) -> List[str]:
        del max_length
        try:
            return [clean_translation(text) for text in self.translator.translate_batch(texts)]
        except Exception:
            translated: List[str] = []
            for text in texts:
                try:
                    translated_text = self.translator.translate(text)
                except Exception:
                    translated_text = self.get_local_fallback().translate_batch([text])[0]
                translated.append(clean_translation(translated_text))
            return translated


class DeepLTranslator:
    def __init__(self) -> None:
        api_key = os.getenv("DEEPL_API_KEY")
        if not api_key:
            raise SystemExit("Set DEEPL_API_KEY before using the deepl engine.")
        self.translator = deepl.Translator(
            api_key,
            server_url="https://api-free.deepl.com",
        )

    def translate_batch(self, texts: List[str], max_length: int = 256) -> List[str]:
        del max_length
        try:
            results = self.translator.translate_text(
                texts,
                source_lang="EN",
                target_lang="KO",
                preserve_formatting=True,
                split_sentences="nonewlines",
                context="Stock market Q&A video. Use natural Korean subtitle style. Keep tickers like PSTG and SHAK uppercase.",
            )
            if not isinstance(results, list):
                results = [results]
            return [clean_translation(result.text) for result in results]
        except Exception:
            translated: List[str] = []
            for text in texts:
                result = self.translator.translate_text(
                    text,
                    source_lang="EN",
                    target_lang="KO",
                    preserve_formatting=True,
                    split_sentences="nonewlines",
                    context="Stock market Q&A video. Use natural Korean subtitle style. Keep tickers like PSTG and SHAK uppercase.",
                )
                translated.append(clean_translation(result.text))
            return translated


class GeminiTranslator:
    def __init__(self, model_name: str) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise SystemExit("Set GEMINI_API_KEY before using the gemini engine.")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.model_name = model_name
        self.google_fallback = GoogleWebTranslator(DEFAULT_MODEL)

    def build_prompt(self, texts: List[str]) -> str:
        payload = [{"index": index + 1, "text": text} for index, text in enumerate(texts)]
        return (
            "Translate the following English subtitle segments into Korean.\n"
            "Return JSON only as an array of objects with keys index and text.\n"
            "Keep the same order and item count.\n"
            "Do not omit tickers such as PSTG or SHAK.\n\n"
            f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    def parse_response(self, content: str, expected_count: int) -> List[str]:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", content)
            content = re.sub(r"\n```$", "", content)
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Gemini response did not include a JSON array.")
        items = json.loads(content[start : end + 1])
        translated: List[str] = []
        for item in items[:expected_count]:
            translated.append(clean_translation(str(item.get("text", "")).strip() or "..."))
        while len(translated) < expected_count:
            translated.append("...")
        return translated

    def translate_single(self, text: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": GEMINI_SYS_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Translate this English subtitle segment into natural Korean. "
                            "Return only the translated Korean text.\n\n"
                            f"INPUT:\n{text}"
                        ),
                    },
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            return clean_translation(content)
        except RateLimitError:
            return self.google_fallback.translate_batch([text])[0]

    def translate_batch(self, texts: List[str], max_length: int = 256) -> List[str]:
        del max_length
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": GEMINI_SYS_PROMPT},
                    {"role": "user", "content": self.build_prompt(texts)},
                ],
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            return self.parse_response(content, len(texts))
        except RateLimitError:
            return self.google_fallback.translate_batch(texts)
        except Exception:
            if len(texts) == 1:
                return [self.translate_single(texts[0])]
            mid = max(1, len(texts) // 2)
            left = self.translate_batch(texts[:mid])
            right = self.translate_batch(texts[mid:])
            return left + right


def post_edit(text: str) -> str:
    replacements = {
        "브랜든 헤지패스": "브랜든",
        "마크 리치": "마크리치",
        "오른쪽 측면": "오른쪽(최근 구간)",
        "베이스": "베이스",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return text


def apply_speaker_labels(sources: List[str], translated: List[str], speakers: List[str]) -> List[str]:
    labeled: List[str] = []
    previous_speaker = ""

    for source, text, speaker in zip(sources, translated, speakers):
        text = post_edit(ensure_tickers(source, text))
        label = KOREAN_SPEAKER_LABELS.get(speaker, "")
        if label and label != previous_speaker:
            text = f"{label}: {text}"
            previous_speaker = label
        elif label:
            previous_speaker = label
        labeled.append(wrap_2lines(text))

    return labeled


def load_subtitles(path: str) -> List[srt.Subtitle]:
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return list(srt.parse(handle.read()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="input EN SRT")
    parser.add_argument("-o", "--output", default="ko.srt")
    parser.add_argument("--engine", choices=("google", "local", "gemini", "deepl"), default="google")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--batch-size", type=int, default=12)
    args = parser.parse_args()

    subs = load_subtitles(args.input)
    speakers = infer_speakers(subs)
    segments = build_segments(subs, speakers)
    if args.engine == "google":
        translator = GoogleWebTranslator(args.model)
    elif args.engine == "local":
        translator = LocalTranslator(args.model)
    elif args.engine == "deepl":
        translator = DeepLTranslator()
    else:
        translator = GeminiTranslator(args.gemini_model)

    translated: List[str] = []
    for start in range(0, len(segments), args.batch_size):
        batch = segments[start : start + args.batch_size]
        batch_texts = [segment.text for segment in batch]
        print(f"Translating batch {start + 1}-{start + len(batch)} / {len(segments)}")
        translated.extend(translator.translate_batch(batch_texts))

    source_texts = [segment.text for segment in segments]
    segment_speakers = [segment.speaker for segment in segments]
    labeled_texts = apply_speaker_labels(source_texts, translated, segment_speakers)
    output_subs = retime_segments(segments, labeled_texts)

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(srt.compose(output_subs))

    print(f"Wrote {args.output} (captions={len(output_subs)})")


if __name__ == "__main__":
    main()
