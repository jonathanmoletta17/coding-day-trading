from __future__ import annotations

"""
DSL v0.1-Core matcher.

Rules are deterministic and explicit:
1) Records are evaluated per stream_key (venue, instrument_id, source).
2) Segments are split at SEQUENCE_GAP / BOOK_RESET; matches cannot cross a split.
3) When a sub-expression yields multiple valid matches, the canonical choice is the
   lexicographically smallest (start_ts, end_ts, first_event_id, last_event_id).
4) Any unsupported syntax must raise DSLParseError (no silent degradation).
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.microstructure.book import tick_distance
from src.microstructure.models import EventRecord, parse_decimal, parse_int


class DSLParseError(ValueError):
    pass


@dataclass(frozen=True)
class PatternTemplate:
    name: str
    param_names: List[str]
    require_window_expr: str
    let_assignments: List[Tuple[str, str]]
    match_lines: List[str]
    start_rule: str
    end_rule: str
    emit_expr: str
    desc: str


@dataclass(frozen=True)
class PatternOccurrence:
    pattern: str
    stream_key: Tuple[str, str, str]
    start_ts: int
    end_ts: int
    emit: Dict[str, Any]
    evidence_event_ids: List[str]


class DSLParserV01:
    _pattern_header = re.compile(r"^PATTERN\s+([A-Za-z_][A-Za-z0-9_]*)\((.*?)\):\s*$")

    def parse(self, dsl_text: str) -> List[PatternTemplate]:
        lines = [ln.rstrip("\n") for ln in dsl_text.splitlines()]
        patterns: List[PatternTemplate] = []

        i = 0
        while i < len(lines):
            ln = lines[i].strip()
            if not ln:
                i += 1
                continue
            m = self._pattern_header.match(ln)
            if not m:
                raise DSLParseError(f"Unsupported top-level DSL line in v0.1-Core: {lines[i]}")
            name = m.group(1)
            param_names = [p.strip() for p in m.group(2).split(",") if p.strip()]
            i += 1

            require_expr = None
            let_assignments: List[Tuple[str, str]] = []
            match_lines: List[str] = []
            start_rule = None
            end_rule = None
            emit_expr = None
            desc = ""

            in_match = False
            while i < len(lines):
                raw = lines[i]
                stripped = raw.strip()
                if stripped.startswith("PATTERN ") and not in_match:
                    break
                if not stripped:
                    i += 1
                    continue

                if stripped.startswith("REQUIRE "):
                    if not re.match(
                        r"^REQUIRE\s+NO_EVENT\(SEQUENCE_GAP\|BOOK_RESET\)\s+WITHIN\s+.+$",
                        stripped,
                    ):
                        raise DSLParseError(f"Unsupported REQUIRE in v0.1-Core: {stripped}")
                    require_expr = stripped
                    i += 1
                    continue

                if stripped.startswith("LET "):
                    mlet = re.match(r"LET\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", stripped)
                    if not mlet:
                        raise DSLParseError(f"Invalid LET: {stripped}")
                    let_assignments.append((mlet.group(1), mlet.group(2).strip()))
                    i += 1
                    continue

                if stripped.startswith("MATCH "):
                    in_match = True
                    match_lines.append(stripped[len("MATCH ") :].rstrip())
                    i += 1
                    continue

                if in_match:
                    if stripped.startswith("START:"):
                        in_match = False
                        continue
                    match_lines.append(stripped)
                    i += 1
                    continue

                if stripped.startswith("START:"):
                    start_rule = stripped.split("START:", 1)[1].strip()
                    i += 1
                    continue

                if stripped.startswith("END:"):
                    end_rule = stripped.split("END:", 1)[1].strip()
                    i += 1
                    continue

                if stripped.startswith("EMIT "):
                    emit_expr = stripped[len("EMIT") :].strip()
                    i += 1
                    continue

                if stripped.startswith("DESC:"):
                    desc = stripped.split("DESC:", 1)[1].strip()
                    i += 1
                    continue

                raise DSLParseError(f"Unsupported DSL line in v0.1-Core: {raw}")

            if require_expr is None:
                raise DSLParseError(f"Missing REQUIRE for pattern {name}")
            if not match_lines:
                raise DSLParseError(f"Missing MATCH for pattern {name}")
            if start_rule is None or end_rule is None:
                raise DSLParseError(f"Missing START/END for pattern {name}")
            if emit_expr is None:
                raise DSLParseError(f"Missing EMIT for pattern {name}")

            patterns.append(
                PatternTemplate(
                    name=name,
                    param_names=param_names,
                    require_window_expr=require_expr,
                    let_assignments=let_assignments,
                    match_lines=match_lines,
                    start_rule=start_rule,
                    end_rule=end_rule,
                    emit_expr=emit_expr,
                    desc=desc,
                )
            )

        return patterns


class PatternEngineV01:
    def __init__(self, patterns: Sequence[PatternTemplate]):
        self._patterns: Dict[str, PatternTemplate] = {p.name: p for p in patterns}

    def run(
        self,
        records: Sequence[EventRecord],
        pattern_params: Dict[str, Dict[str, Any]],
        enabled_patterns: Optional[Sequence[str]] = None,
    ) -> List[PatternOccurrence]:
        if enabled_patterns is None:
            names = [p.name for p in self._patterns.values()]
        else:
            names = list(enabled_patterns)

        occurrences: List[PatternOccurrence] = []
        per_stream: Dict[Tuple[str, str, str], List[EventRecord]] = {}
        for r in records:
            per_stream.setdefault(r.envelope.stream_key(), []).append(r)

        for sk in sorted(per_stream.keys()):
            stream_records = list(per_stream[sk])
            stream_records.sort(key=lambda r: (r.envelope.ordering_key(), 0 if not r.is_derived else 1, r.envelope.event_id))
            segments = _split_stream_segments(stream_records)
            for seg, seg_end_barrier_ts in segments:
                for name in names:
                    tmpl = self._patterns.get(name)
                    if tmpl is None:
                        continue
                    bindings = pattern_params.get(name)
                    if bindings is None:
                        raise DSLParseError(f"Missing parameters for pattern {name}")
                    occurrences.extend(self._match_template(sk, seg, seg_end_barrier_ts, tmpl, bindings))

        occurrences.sort(key=lambda o: (o.stream_key, o.pattern, o.start_ts, o.end_ts))
        return occurrences

    def _match_template(
        self,
        stream_key: Tuple[str, str, str],
        segment: Sequence[EventRecord],
        segment_end_barrier_ts: Optional[int],
        tmpl: PatternTemplate,
        bindings: Dict[str, Any],
    ) -> List[PatternOccurrence]:
        require_within_ms = _eval_require_window_ms(tmpl.require_window_expr, bindings)
        match_expr = _normalize_match_expr(tmpl.match_lines)

        if match_expr.startswith("SEQUENCE "):
            raw = _match_sequence(segment, match_expr, tmpl, bindings, require_within_ms, segment_end_barrier_ts=segment_end_barrier_ts)
            return [_finalize_occurrence(stream_key, tmpl, bindings, r, tmpl.let_assignments) for r in raw]
        if match_expr.startswith("ALL_OF("):
            raw = _match_all_of(
                segment,
                match_expr,
                tmpl,
                bindings,
                require_within_ms,
                self._patterns,
                segment_end_barrier_ts=segment_end_barrier_ts,
            )
            return [_finalize_occurrence(stream_key, tmpl, bindings, r, tmpl.let_assignments) for r in raw]
        if match_expr.startswith("ANY_OF("):
            raw = _match_any_of(
                segment,
                match_expr,
                tmpl,
                bindings,
                require_within_ms,
                self._patterns,
                segment_end_barrier_ts=segment_end_barrier_ts,
            )
            return [_finalize_occurrence(stream_key, tmpl, bindings, r, tmpl.let_assignments) for r in raw]
        if match_expr.startswith("NONE_OF("):
            raise DSLParseError("v0.1-Core does not support NONE_OF as MATCH root")
        if match_expr.startswith("HOLD("):
            raise DSLParseError("v0.1-Core does not support HOLD(...) FOR ...")
        raise DSLParseError(f"Unsupported MATCH for pattern {tmpl.name} in v0.1-Core: {match_expr}")


@dataclass
class _RawOccurrence:
    start_ts: int
    end_ts: int
    first_record: EventRecord
    last_record: EventRecord
    bindings: Dict[str, Any]
    captures: Dict[str, List[_RecordProxy]]


class _StateProxy:
    __slots__ = ("_s",)

    def __init__(self, s: Any):
        object.__setattr__(self, "_s", s)

    def __getattribute__(self, name: str) -> Any:
        if name in {"_s"}:
            return object.__getattribute__(self, name)
        if name.startswith("_"):
            raise AttributeError(name)
        if name in {"touch_price", "level_size", "top_n", "tick_size"}:
            return getattr(object.__getattribute__(self, "_s"), name)
        if name in {"spread_ticks", "best_bid_price", "best_ask_price"}:
            return getattr(object.__getattribute__(self, "_s"), name)
        raise AttributeError(name)


class _RecordProxy:
    __slots__ = ("_r",)

    def __init__(self, r: EventRecord):
        object.__setattr__(self, "_r", r)

    def __getattribute__(self, name: str) -> Any:
        if name in {"_r"}:
            return object.__getattribute__(self, name)
        if name.startswith("_"):
            raise AttributeError(name)
        if name in {"side", "price", "new_size", "delta_size"}:
            return getattr(object.__getattribute__(self, "_r"), name)
        if name in {"event_type", "event_id", "instrument_id", "venue", "source", "ts_recv", "ts_event", "source_seq"}:
            env = object.__getattribute__(self, "_r").envelope
            return getattr(env, name)
        raise AttributeError(name)

    def effective_ts(self) -> int:
        return object.__getattribute__(self, "_r").effective_ts()


def _split_stream_segments(records: Sequence[EventRecord]) -> List[Tuple[List[EventRecord], Optional[int]]]:
    segments: List[Tuple[List[EventRecord], Optional[int]]] = []
    cur: List[EventRecord] = []
    for r in records:
        if r.envelope.event_type in ("SEQUENCE_GAP", "BOOK_RESET"):
            barrier_ts = r.effective_ts()
            if cur:
                segments.append((cur, barrier_ts))
                cur = []
            continue
        cur.append(r)
    if cur:
        segments.append((cur, None))
    return segments


def _normalize_match_expr(match_lines: Sequence[str]) -> str:
    return " ".join(ln.strip() for ln in match_lines if ln.strip())


def _eval_require_window_ms(require_expr: str, bindings: Dict[str, Any]) -> int:
    m = re.search(r"WITHIN\s+(.+)$", require_expr)
    if not m:
        raise DSLParseError(f"Invalid REQUIRE: {require_expr}")
    tail = m.group(1).strip()
    return _eval_window_expr_ms(tail, bindings)


def _eval_window_expr_ms(expr: str, bindings: Dict[str, Any]) -> int:
    s = expr.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()

    parts = [p.strip() for p in s.split("+")]
    if len(parts) == 1:
        tok = parts[0]
        if tok.endswith("ms") and tok[:-2].strip().isdigit():
            return int(tok[:-2].strip())
        if tok.isdigit():
            return int(tok)
        if tok in bindings:
            return int(bindings[tok])
        raise DSLParseError(f"Unresolved window token: {tok}")

    total = 0
    for p in parts:
        total += _eval_window_expr_ms(p, bindings)
    return total


def _extract_time_clause(expr: str, keyword: str, bindings: Dict[str, Any]) -> Optional[int]:
    m = re.search(rf"\b{re.escape(keyword)}\s+([A-Za-z0-9_]+)\b", expr)
    if not m:
        return None
    tok = m.group(1)
    if tok.endswith("ms") and tok[:-2].isdigit():
        return int(tok[:-2])
    if tok.isdigit():
        return int(tok)
    if tok in bindings:
        return int(bindings[tok])
    raise DSLParseError(f"Unresolved {keyword} token: {tok}")


def _extract_repeat(expr: str, bindings: Dict[str, Any]) -> Optional[int]:
    m = re.search(r"\bREPEAT>=\s*([A-Za-z0-9_]+)\b", expr)
    if not m:
        return None
    tok = m.group(1)
    if tok.isdigit():
        return int(tok)
    if tok in bindings:
        return int(bindings[tok])
    raise DSLParseError(f"Unresolved REPEAT token: {tok}")


def _extract_distinct(expr: str, bindings: Dict[str, Any]) -> Optional[Tuple[int, str]]:
    m = re.search(r"\bDISTINCT>=\s*([A-Za-z0-9_]+)\s+BY\s+([A-Za-z_][A-Za-z0-9_\.]*)\b", expr)
    if not m:
        return None
    tok = m.group(1)
    by = m.group(2)
    if tok.isdigit():
        return int(tok), by
    if tok in bindings:
        return int(bindings[tok]), by
    raise DSLParseError(f"Unresolved DISTINCT token: {tok}")


def _split_top_level_commas(s: str) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf).strip())
    return [x for x in out if x]


def _parse_event_binds(seq_expr: str) -> List[Tuple[str, str, str]]:
    binds: List[Tuple[str, str, str]] = []
    for m in re.finditer(r"\bEVENT\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Z_]+)\s+WHERE\s+", seq_expr):
        pass
    parts = seq_expr.split("EVENT ")
    for part in parts[1:]:
        frag = "EVENT " + part
        m = re.match(r"EVENT\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Z_]+)\s+WHERE\s+(.+)$", frag.strip())
        if not m:
            continue
        alias = m.group(1)
        etype = m.group(2)
        pred = m.group(3).strip()
        for kw in ("WITHIN", "MAX_GAP", "REPEAT>=", "DISTINCT>=", "AFTER"):
            idx = pred.find(f" {kw} ")
            if idx != -1:
                pred = pred[:idx].strip()
        binds.append((alias, etype, pred))
    return binds


def _match_sequence(
    segment: Sequence[EventRecord],
    expr: str,
    tmpl: PatternTemplate,
    bindings: Dict[str, Any],
    require_within_ms: int,
    *,
    segment_end_barrier_ts: Optional[int] = None,
    after_ts: Optional[int] = None,
    after_alias: Optional[str] = None,
) -> List[_RawOccurrence]:
    within_ms = _extract_time_clause(expr, "WITHIN", bindings)
    max_gap_ms = _extract_time_clause(expr, "MAX_GAP", bindings)
    repeat = _extract_repeat(expr, bindings)
    distinct = _extract_distinct(expr, bindings)

    binds = _parse_event_binds(expr)
    if not binds:
        raise DSLParseError(f"SEQUENCE has no EVENT binds: {expr}")

    if within_ms is None:
        within_ms = require_within_ms

    start_candidates = segment
    if after_ts is not None:
        start_candidates = [r for r in segment if r.effective_ts() >= after_ts]

    out: List[_RawOccurrence] = []

    for start_idx in range(len(start_candidates)):
        idx_in_seg = segment.index(start_candidates[start_idx])
        idx = idx_in_seg
        matched: List[EventRecord] = []
        cap: Dict[str, List[_RecordProxy]] = {}
        local_bindings: Dict[str, Any] = dict(bindings)

        ok = True
        want_cycles = repeat if repeat is not None else 1
        if want_cycles is not None and want_cycles <= 0:
            raise DSLParseError("REPEAT>= must be >= 1 in v0.1-Core")

        last_ts: Optional[int] = None

        def _accept(alias: str, r: EventRecord) -> None:
            nonlocal last_ts
            pr = _RecordProxy(r)
            local_bindings[alias] = pr
            cap.setdefault(alias, []).append(pr)
            matched.append(r)
            if last_ts is not None and max_gap_ms is not None:
                if (r.effective_ts() - last_ts) > max_gap_ms:
                    raise DSLParseError("MAX_GAP violated")
            last_ts = r.effective_ts()
            for let_name, let_expr in tmpl.let_assignments:
                if let_name in local_bindings:
                    continue
                if _expr_deps_satisfied(let_expr, local_bindings):
                    local_bindings[let_name] = _eval_expr(let_expr, local_bindings, cap, r)

        if segment_end_barrier_ts is not None:
            start_ts0 = segment[idx].effective_ts() if idx < len(segment) else None
            if start_ts0 is not None and (start_ts0 + require_within_ms) >= segment_end_barrier_ts:
                continue

        try:
            if len(binds) == 1 and repeat is not None:
                alias, etype, pred = binds[0]
                found_count = 0
                while idx < len(segment) and found_count < want_cycles:
                    r = segment[idx]
                    idx += 1
                    if r.envelope.event_type != etype:
                        continue
                    if not _eval_predicate(pred, alias=alias, record=r, bindings=local_bindings, captures=cap):
                        continue
                    if not matched:
                        start_ts = r.effective_ts()
                        if segment_end_barrier_ts is not None and (start_ts + require_within_ms) >= segment_end_barrier_ts:
                            ok = False
                            break
                    _accept(alias, r)
                    found_count += 1
                    if matched and within_ms is not None and (matched[-1].effective_ts() - matched[0].effective_ts()) > within_ms:
                        ok = False
                        break
                if found_count < want_cycles:
                    ok = False
            elif len(binds) == 1 and repeat is None and distinct is not None:
                alias, etype, pred = binds[0]
                want, by = distinct
                if "." not in by:
                    raise DSLParseError("DISTINCT BY must be alias.field in v0.1")
                a0, f0 = by.split(".", 1)
                if a0 != alias:
                    raise DSLParseError("DISTINCT BY alias must match EVENT alias in v0.1-Core")

                distinct_vals: set[str] = set()
                start_ts: Optional[int] = None
                while idx < len(segment) and len(distinct_vals) < want:
                    r = segment[idx]
                    idx += 1
                    if r.envelope.event_type != etype:
                        continue
                    if not _eval_predicate(pred, alias=alias, record=r, bindings=local_bindings, captures=cap):
                        continue
                    if start_ts is None:
                        start_ts = r.effective_ts()
                        if segment_end_barrier_ts is not None and (start_ts + require_within_ms) >= segment_end_barrier_ts:
                            ok = False
                            break
                    if within_ms is not None and (r.effective_ts() - start_ts) > within_ms:
                        ok = False
                        break
                    _accept(alias, r)
                    distinct_vals.add(str(getattr(_RecordProxy(r), f0)))

                if len(distinct_vals) < want:
                    ok = False
            else:
                for _cycle in range(want_cycles or 1):
                    for alias, etype, pred in binds:
                        found = False
                        while idx < len(segment):
                            r = segment[idx]
                            idx += 1
                            if r.envelope.event_type != etype:
                                continue
                            if not _eval_predicate(pred, alias=alias, record=r, bindings=local_bindings, captures=cap):
                                continue
                            if not matched:
                                start_ts = r.effective_ts()
                                if segment_end_barrier_ts is not None and (start_ts + require_within_ms) >= segment_end_barrier_ts:
                                    ok = False
                                    break
                            _accept(alias, r)
                            found = True
                            break
                        if not ok:
                            break
                        if not found:
                            ok = False
                            break
                    if not ok:
                        break
                    if matched and within_ms is not None and (matched[-1].effective_ts() - matched[0].effective_ts()) > within_ms:
                        ok = False
                        break
        except DSLParseError as e:
            if str(e) == "MAX_GAP violated":
                ok = False
            else:
                raise

        if not ok:
            continue

        start_ts = matched[0].effective_ts()
        end_ts = matched[-1].effective_ts()
        if within_ms is not None and (end_ts - start_ts) > within_ms:
            continue

        if distinct is not None:
            want, by = distinct
            if "." not in by:
                raise DSLParseError("DISTINCT BY must be alias.field in v0.1")
            a0, f0 = by.split(".", 1)
            vals = set()
            for pr in cap.get(a0, []):
                vals.add(str(getattr(pr, f0)))
            if len(vals) < want:
                continue

        out.append(
            _RawOccurrence(
                start_ts=start_ts,
                end_ts=end_ts,
                first_record=matched[0],
                last_record=matched[-1],
                bindings=local_bindings,
                captures=cap,
            )
        )

    return _dedupe_occurrences(out)


def _dedupe_occurrences(occ: List[_RawOccurrence]) -> List[_RawOccurrence]:
    seen: set[Tuple[int, int, str, str]] = set()
    out: List[_RawOccurrence] = []
    for o in occ:
        key = (o.start_ts, o.end_ts, o.first_record.envelope.event_id, o.last_record.envelope.event_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def _match_none_of_sequence(segment: Sequence[EventRecord], expr: str, window_start: int, bindings: Dict[str, Any]) -> bool:
    inner = expr[len("NONE_OF(") :].rstrip(")")
    inner = inner.strip()
    if not inner.startswith("SEQUENCE "):
        raise DSLParseError("NONE_OF only supports SEQUENCE in v0.1")
    within_ms = _extract_time_clause(inner, "WITHIN", bindings)
    if within_ms is None:
        raise DSLParseError("NONE_OF(SEQUENCE ...) must include WITHIN in v0.1")
    window_end = window_start + within_ms
    sub = [r for r in segment if window_start <= r.effective_ts() <= window_end]
    tmp = PatternTemplate(
        name="_noneof",
        param_names=[],
        require_window_expr="",
        let_assignments=[],
        match_lines=[],
        start_rule="",
        end_rule="",
        emit_expr="",
        desc="",
    )
    found = _match_sequence(sub, inner, tmp, bindings, within_ms, segment_end_barrier_ts=None)
    return len(found) == 0


def _match_all_of(
    segment: Sequence[EventRecord],
    expr: str,
    tmpl: PatternTemplate,
    bindings: Dict[str, Any],
    require_within_ms: int,
    patterns: Dict[str, PatternTemplate],
    *,
    segment_end_barrier_ts: Optional[int],
) -> List[_RawOccurrence]:
    inner = expr[len("ALL_OF(") :].rstrip(")")
    parts = _split_top_level_commas(inner)
    if not parts:
        return []

    anchor = parts[0]
    if anchor.startswith("PATTERN_REF "):
        anchors = _match_pattern_ref(segment, anchor, tmpl, bindings, require_within_ms, patterns, segment_end_barrier_ts=segment_end_barrier_ts)
    elif anchor.startswith("SEQUENCE "):
        anchors = _match_sequence(segment, anchor, tmpl, bindings, require_within_ms, segment_end_barrier_ts=segment_end_barrier_ts)
    else:
        raise DSLParseError(f"Unsupported ALL_OF anchor: {anchor}")

    out: List[_RawOccurrence] = []
    for a in anchors:
        ok = True
        current_end = a.end_ts
        b = dict(a.bindings)
        c = dict(a.captures)
        for part in parts[1:]:
            if part.startswith("NONE_OF("):
                if not _match_none_of_sequence(segment, part, window_start=a.start_ts, bindings=b):
                    ok = False
                    break
                continue
            if part.startswith("SEQUENCE "):
                m_after = re.search(r"\bAFTER\s+([A-Za-z_][A-Za-z0-9_]*)\.end\b", part)
                if m_after:
                    after_alias = m_after.group(1)
                    if after_alias not in b or not isinstance(b[after_alias], dict) or "end" not in b[after_alias]:
                        raise DSLParseError(f"AFTER refers to unknown alias: {after_alias}.end")
                    after_ts = int(b[after_alias]["end"])
                    part_clean = re.sub(r"\bAFTER\s+[A-Za-z_][A-Za-z0-9_]*\.end\b", "", part).strip()
                else:
                    after_ts = current_end
                    part_clean = part
                seqs = _match_sequence(
                    segment,
                    part_clean,
                    tmpl,
                    b,
                    require_within_ms,
                    segment_end_barrier_ts=segment_end_barrier_ts,
                    after_ts=after_ts,
                )
                if not seqs:
                    ok = False
                    break
                chosen = min(
                    seqs,
                    key=lambda x: (x.start_ts, x.end_ts, x.first_record.envelope.event_id, x.last_record.envelope.event_id),
                )
                current_end = max(current_end, chosen.end_ts)
                b.update(chosen.bindings)
                for k0, v0 in chosen.captures.items():
                    c.setdefault(k0, []).extend(v0)
                continue
            raise DSLParseError(f"Unsupported ALL_OF component: {part}")
        if ok:
            out.append(
                _RawOccurrence(
                    start_ts=a.start_ts,
                    end_ts=current_end,
                    first_record=a.first_record,
                    last_record=a.last_record,
                    bindings=b,
                    captures=c,
                )
            )
    return _dedupe_occurrences(out)


def _match_any_of(
    segment: Sequence[EventRecord],
    expr: str,
    tmpl: PatternTemplate,
    bindings: Dict[str, Any],
    require_within_ms: int,
    patterns: Dict[str, PatternTemplate],
    *,
    segment_end_barrier_ts: Optional[int],
) -> List[_RawOccurrence]:
    inner = expr[len("ANY_OF(") :].rstrip(")")
    parts = _split_top_level_commas(inner)
    out: List[_RawOccurrence] = []
    for part in parts:
        if part.startswith("SEQUENCE "):
            out.extend(_match_sequence(segment, part, tmpl, bindings, require_within_ms, segment_end_barrier_ts=segment_end_barrier_ts))
        elif part.startswith("PATTERN_REF "):
            out.extend(
                _match_pattern_ref(
                    segment,
                    part,
                    tmpl,
                    bindings,
                    require_within_ms,
                    patterns,
                    segment_end_barrier_ts=segment_end_barrier_ts,
                )
            )
    return _dedupe_occurrences(out)


def _match_pattern_ref(
    segment: Sequence[EventRecord],
    expr: str,
    tmpl: PatternTemplate,
    bindings: Dict[str, Any],
    require_within_ms: int,
    patterns: Dict[str, PatternTemplate],
    *,
    segment_end_barrier_ts: Optional[int],
) -> List[_RawOccurrence]:
    m = re.match(r"PATTERN_REF\s+([A-Za-z_][A-Za-z0-9_]*)\((.*?)\)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)$", expr)
    if not m:
        raise DSLParseError(f"Invalid PATTERN_REF: {expr}")
    target_name = m.group(1)
    alias = m.group(3)
    target = patterns.get(target_name)
    if target is None:
        raise DSLParseError(f"Unknown PATTERN_REF target: {target_name}")

    args = [a.strip() for a in _split_top_level_commas(m.group(2))] if m.group(2).strip() else []
    if len(args) != len(target.param_names):
        raise DSLParseError(f"PATTERN_REF {target_name} arity mismatch: {len(args)} != {len(target.param_names)}")

    target_bindings: Dict[str, Any] = {}
    for param_name, arg_expr in zip(target.param_names, args):
        target_bindings[param_name] = _eval_expr(arg_expr, dict(bindings), {}, None)

    require_within_ms_target = _eval_require_window_ms(target.require_window_expr, target_bindings)
    match_expr = _normalize_match_expr(target.match_lines)

    if not match_expr.startswith("SEQUENCE "):
        raise DSLParseError("v0.1 engine supports PATTERN_REF only for SEQUENCE-root patterns")
    raw = _match_sequence(
        segment,
        match_expr,
        target,
        target_bindings,
        require_within_ms_target,
        segment_end_barrier_ts=segment_end_barrier_ts,
    )

    out: List[_RawOccurrence] = []
    for r in raw:
        b = dict(bindings)
        b[alias] = {"start": r.start_ts, "end": r.end_ts}
        out.append(
            _RawOccurrence(
                start_ts=r.start_ts,
                end_ts=r.end_ts,
                first_record=r.first_record,
                last_record=r.last_record,
                bindings=b,
                captures=r.captures,
            )
        )
    return out


def _finalize_occurrence(
    stream_key: Tuple[str, str, str],
    tmpl: PatternTemplate,
    bindings: Dict[str, Any],
    raw: _RawOccurrence,
    lets: Sequence[Tuple[str, str]],
) -> PatternOccurrence:
    b = dict(raw.bindings)
    for name, expr in lets:
        if name in b:
            continue
        if _expr_deps_satisfied(expr, b):
            b[name] = _eval_expr(expr, b, raw.captures, raw.first_record)

    start_ts = _resolve_start_rule(tmpl.start_rule, raw)
    end_ts = _resolve_end_rule(tmpl.end_rule, raw)

    emit = _eval_emit(tmpl.emit_expr, raw, b)
    emit.setdefault("start_ts", start_ts)
    emit.setdefault("end_ts", end_ts)
    ev_ids: List[str] = []
    seen: set[str] = set()
    for eid in (raw.first_record.envelope.event_id, raw.last_record.envelope.event_id):
        if eid not in seen:
            seen.add(eid)
            ev_ids.append(eid)
    for plist in raw.captures.values():
        for pr in plist:
            try:
                eid = pr.event_id
            except Exception:
                continue
            if eid not in seen:
                seen.add(eid)
                ev_ids.append(eid)
    return PatternOccurrence(pattern=tmpl.name, stream_key=stream_key, start_ts=start_ts, end_ts=end_ts, emit=emit, evidence_event_ids=ev_ids)


def _resolve_start_rule(rule: str, raw: _RawOccurrence) -> int:
    if rule == "FIRST_MATCH_EVENT":
        return raw.start_ts
    if rule.endswith(".start") and rule[:-6] in raw.bindings:
        v = raw.bindings[rule[:-6]]
        if isinstance(v, dict) and "start" in v:
            return int(v["start"])
    return raw.start_ts


def _resolve_end_rule(rule: str, raw: _RawOccurrence) -> int:
    if rule == "LAST_MATCH_EVENT":
        return raw.end_ts
    if rule.endswith(".end") and rule[:-4] in raw.bindings:
        v = raw.bindings[rule[:-4]]
        if isinstance(v, dict) and "end" in v:
            return int(v["end"])
    return raw.end_ts


def _eval_emit(emit_expr: str, raw: _RawOccurrence, bindings: Dict[str, Any]) -> Dict[str, Any]:
    m = re.match(r"^\{\s*(.*)\s*\}$", emit_expr.strip())
    if not m:
        raise DSLParseError(f"Invalid EMIT: {emit_expr}")
    inner = m.group(1).strip()
    if not inner:
        return {}

    items = _split_top_level_commas(inner)
    out: Dict[str, Any] = {}
    base_ctx = dict(bindings)
    base_ctx["instrument_id"] = raw.first_record.envelope.instrument_id
    base_ctx["venue"] = raw.first_record.envelope.venue
    base_ctx["source"] = raw.first_record.envelope.source

    for item in items:
        if "=" in item:
            k, v = item.split("=", 1)
            key = k.strip()
            expr = v.strip()
            out[key] = _eval_expr(expr, base_ctx, raw.captures, raw.last_record)
        else:
            key = item.strip()
            if key in ("start_ts", "end_ts"):
                continue
            if key in base_ctx:
                out[key] = base_ctx[key]
            else:
                out[key] = _eval_expr(key, base_ctx, raw.captures, raw.last_record)
    return out


def _expr_deps_satisfied(expr: str, bindings: Dict[str, Any]) -> bool:
    toks = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expr))
    reserved = {"S_PRE", "S_POST", "tick_distance", "COUNT_DISTINCT", "TRUE", "FALSE", "AND", "OR", "NOT"}
    reserved |= {"touch_price", "level_size", "top_n", "spread_ticks", "best_bid_price", "best_ask_price"}
    for t in toks:
        if t in reserved:
            continue
        if t not in bindings and t not in ("BID", "ASK"):
            return False
    return True


def _eval_predicate(pred: str, *, alias: str, record: EventRecord, bindings: Dict[str, Any], captures: Dict[str, List[_RecordProxy]]) -> bool:
    if pred.strip() == "TRUE":
        return True
    v = _eval_expr(pred, bindings, captures, record, alias=alias)
    return bool(v)


def _eval_expr(
    expr: str,
    bindings: Dict[str, Any],
    captures: Dict[str, List[_RecordProxy]],
    record: Optional[EventRecord],
    *,
    alias: Optional[str] = None,
) -> Any:
    expr0 = expr.strip()
    expr0 = re.sub(r"\bAND\b", "and", expr0)
    expr0 = re.sub(r"\bOR\b", "or", expr0)
    expr0 = re.sub(r"\bNOT\b", "not", expr0)

    if expr0 in ("BID", "ASK"):
        return expr0
    if expr0.endswith("ms") and expr0[:-2].isdigit():
        return int(expr0[:-2])
    if expr0.isdigit():
        return int(expr0)

    env: Dict[str, Any] = dict(bindings)
    if alias is not None and record is not None:
        env[alias] = _RecordProxy(record)

    def S_PRE(rp: _RecordProxy) -> _StateProxy:
        if not isinstance(rp, _RecordProxy):
            raise DSLParseError("S_PRE expects an event alias in v0.1-Core")
        r0 = object.__getattribute__(rp, "_r")
        return _StateProxy(r0.pre_state)

    def S_POST(rp: _RecordProxy) -> _StateProxy:
        if not isinstance(rp, _RecordProxy):
            raise DSLParseError("S_POST expects an event alias in v0.1-Core")
        r0 = object.__getattribute__(rp, "_r")
        return _StateProxy(r0.post_state)

    if record is not None:
        env.setdefault("S_PRE", S_PRE)
        env.setdefault("S_POST", S_POST)
        env.setdefault("tick_distance", lambda a, b: tick_distance(a, b, _StateProxy(record.pre_state).tick_size))
    else:
        env.setdefault("S_PRE", S_PRE)
        env.setdefault("S_POST", S_POST)
        env.setdefault("tick_distance", lambda a, b: (_ for _ in ()).throw(DSLParseError("tick_distance requires state in v0.1-Core")))

    def _cap(alias_name: str, field_name: str) -> List[Any]:
        out: List[Any] = []
        for rec in captures.get(alias_name, []):
            out.append(getattr(rec, field_name))
        return out

    def COUNT_DISTINCT(vals: List[Any]) -> int:
        return len(set(str(v) for v in vals))

    env["_cap"] = _cap
    env["COUNT_DISTINCT"] = COUNT_DISTINCT

    expr1 = re.sub(
        r"\bCOUNT_DISTINCT\(\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        r"COUNT_DISTINCT(_cap('\1','\2'))",
        expr0,
    )

    try:
        code = compile(expr1, "<dsl-expr>", "eval")
        return eval(code, {"__builtins__": {}}, env)
    except Exception as e:
        raise DSLParseError(f"Failed to evaluate expr: {expr!r} -> {expr1!r}: {e}") from e
