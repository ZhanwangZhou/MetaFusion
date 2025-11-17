# utils/prompt_metadata.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

import dateparser
import spacy


# 全局 lazy load spaCy 模型，避免每次都重新加载
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        # 需要你提前跑过: python -m spacy download en_core_web_sm
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


@dataclass
class PromptMetadata:
    """我们从用户 query 里提取出来的结构化信息."""
    # 时间范围（如果只有一个时间点，就 start == end）
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None

    # 原文中识别到的地点短语（"Yosemite", "New York" 等）
    locations: List[str] = None

    # 用来当 tag / keyword 的词（比如 "dog", "wedding"）
    tags: List[str] = None

    # 原始 query 文本
    raw_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # datetime 转成 iso 字符串，方便打印 / json
        if self.start_ts:
            d["start_ts"] = self.start_ts.isoformat()
        if self.end_ts:
            d["end_ts"] = self.end_ts.isoformat()
        return d


class PromptMetadataExtractor:
    """
    从用户自然语言 prompt 中提取出:
    - 时间范围 (start_ts, end_ts)
    - 地点短语 (locations)
    - 关键词 tags (可以喂给 metadata 表里的 tags 字段)
    """

    def __init__(self):
        self.nlp = _get_nlp()

    # -------- 对外唯一入口 --------
    def extract(self, prompt: str) -> PromptMetadata:
        doc = self.nlp(prompt)

        locations = self._extract_locations(doc)
        start_ts, end_ts = self._extract_time_range(doc, prompt)
        tags = self._extract_tags(doc, locations)

        return PromptMetadata(
            start_ts=start_ts,
            end_ts=end_ts,
            locations=locations,
            tags=tags,
            raw_prompt=prompt,
        )

    # -------- 内部：地点提取 --------
    def _extract_locations(self, doc) -> List[str]:
        locs = []
        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC", "FAC"):
                text = ent.text.strip()
                if text and text not in locs:
                    locs.append(text)
        return locs

    # -------- 内部：时间范围提取 --------
    def _extract_time_range(self, doc, prompt: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        简单策略:
        - 找到第一个 DATE 类型的实体，用 dateparser 解析
        - 如果看起来像“某年某月”（e.g., June 2025），我们把范围扩展成整个月
        - 如果只解析出一个时间点，就 start == end
        """
        date_text = None
        for ent in doc.ents:
            if ent.label_ == "DATE":
                date_text = ent.text
                break

        if not date_text:
            # 尝试直接对整个 prompt 用 dateparser 再赌一把
            dt = dateparser.parse(prompt)
            return dt, dt

        dt = dateparser.parse(date_text)
        if not dt:
            return None, None

        # 非严格：判定是不是“某年某月”
        lower = date_text.lower()
        months = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ]
        if any(m in lower for m in months) and any(c.isdigit() for c in lower):
            # 构造这个月的起始和结束 (简化：假设都是 30 天)
            start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # 简单粗暴的 month+1 再减一点
            if dt.month == 12:
                end = dt.replace(year=dt.year + 1, month=1, day=1,
                                 hour=0, minute=0, second=0, microsecond=0)
            else:
                end = dt.replace(month=dt.month + 1, day=1,
                                 hour=0, minute=0, second=0, microsecond=0)
            return start, end

        # 否则就当单点时间
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt, dt

    # -------- 内部：tag 提取 --------
    def _extract_tags(self, doc, locations: List[str]) -> List[str]:
        """
        非常简单的 heuristic：
        - 用名词 (NOUN, PROPN) + 形容词 (ADJ) 做 tag
        - 排除已经识别为地点的词
        """
        loc_set = set(l.lower() for l in locations)
        tags = []

        for token in doc:
            if token.is_stop or token.is_punct or not token.text.strip():
                continue
            if token.pos_ not in ("NOUN", "PROPN", "ADJ"):
                continue

            text = token.lemma_.lower()
            if text in loc_set:
                continue
            if text not in tags:
                tags.append(text)

        return tags
