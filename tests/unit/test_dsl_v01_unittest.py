"""
@category: test
@impact: moderate
@description: Unittests do engine DSL v01
"""

import unittest
from decimal import Decimal

from src.microstructure.dsl_v01 import DSLParserV01, PatternEngineV01
from src.microstructure.context_core import classify_context_core
from src.microstructure.models import BaseEvent
from src.microstructure.replay import ReplayEngineV01


DSL_V01 = """
PATTERN DepletionSequence(side, n_ticks, k, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT r: LIQUIDITY_REMOVE WHERE
      r.side == side AND
      tick_distance(r.price, S_PRE(r).touch_price(side)) <= n_ticks
  WITHIN window_ms REPEAT>= k
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, remove_count=k, distinct_prices=COUNT_DISTINCT(r.price) }
  DESC: Reduções repetidas de size exibido em níveis a ≤ n_ticks do touch do mesmo lado.

PATTERN MultiLevelErosion(side, n_ticks, min_levels, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT r: LIQUIDITY_REMOVE WHERE
      r.side == side AND
      tick_distance(r.price, S_PRE(r).touch_price(side)) <= n_ticks
  WITHIN window_ms DISTINCT>= min_levels BY r.price
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, levels=min_levels }
  DESC: Remoções distribuídas por múltiplos preços próximos ao touch.

PATTERN TouchRepriceWithoutPrint(side, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  LET p0 = S_PRE(e0).touch_price(side)
  MATCH ALL_OF(
    SEQUENCE T:
      EVENT e0: LEVEL_SET WHERE TRUE
      EVENT e1: LEVEL_SET WHERE S_POST(e1).touch_price(side) != p0
    WITHIN window_ms,
    NONE_OF(
      SEQUENCE Z:
        EVENT t: TRADE_PRINT WHERE t.price == p0
      WITHIN window_ms
    )
  )
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, touch_from=p0, touch_to=S_POST(e1).touch_price(side) }
  DESC: Alteração do touch observada via updates do book, sem prints no preço do touch anterior na janela.

PATTERN PrintClusterAtTouch(side, k, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT t: TRADE_PRINT WHERE t.price == S_PRE(t).touch_price(side)
  WITHIN window_ms REPEAT>= k
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, trade_count=k }
  DESC: Conjunto de prints ocorrendo no preço do touch do lado especificado no instante de cada print.

PATTERN LevelFlickerSequence(side, price, toggles, max_gap_ms, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT a: LIQUIDITY_ADD    WHERE a.side==side AND a.price==price
    EVENT r: LIQUIDITY_REMOVE WHERE r.side==side AND r.price==price
  WITHIN window_ms MAX_GAP max_gap_ms REPEAT>= toggles
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, price, toggles=toggles }
  DESC: Alternância rápida de aumentos e reduções do size exibido no mesmo nível.

PATTERN SpreadExpansionSequence(min_increase_ticks, window_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN window_ms
  MATCH SEQUENCE S:
    EVENT u: LEVEL_SET WHERE
      S_POST(u).spread_ticks >= S_PRE(u).spread_ticks + min_increase_ticks
  WITHIN window_ms
  START: FIRST_MATCH_EVENT
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, spread_delta_ticks=min_increase_ticks }
  DESC: Aumento do spread observado como mudança discreta do estado pré para o pós update.

PATTERN ReplenishAfterDepletionSequence(side, n_ticks, k_depl, w_depl_ms, k_add, w_rec_ms):
  REQUIRE NO_EVENT(SEQUENCE_GAP|BOOK_RESET) WITHIN (w_depl_ms + w_rec_ms)
  MATCH ALL_OF(
    PATTERN_REF DepletionSequence(side, n_ticks, k_depl, w_depl_ms) AS D,
    SEQUENCE R:
      EVENT a: LIQUIDITY_ADD WHERE
        a.side == side AND
        tick_distance(a.price, S_PRE(a).touch_price(side)) <= n_ticks
    WITHIN w_rec_ms REPEAT>= k_add AFTER D.end
  )
  START: D.start
  END:   LAST_MATCH_EVENT
  EMIT { start_ts, end_ts, instrument_id, side, depl_count=k_depl, add_count=k_add }
  DESC: Após uma sequência de remoções próximas ao touch, ocorrem adições na mesma zona dentro de janela posterior.
""".strip()


def _base_event(event_id: str, event_type: str, ts: int, payload: dict):
    base = {
        "event_id": event_id,
        "event_type": event_type,
        "instrument_id": "X",
        "venue": "V",
        "source": "depth",
        "ts_recv": ts,
        "ts_event": ts,
        "source_seq": ts,
    }
    base.update(payload)
    return BaseEvent.from_json(base)


class TestDSLv01(unittest.TestCase):
    def setUp(self):
        self.tick_sizes = {"X": Decimal("1")}
        self.patterns = DSLParserV01().parse(DSL_V01)

    def _replay(self, events):
        return ReplayEngineV01(tick_size_by_instrument=self.tick_sizes).replay(events)

    def test_replay_after_snapshot_and_derivation(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 2, {"side": "BID", "price": "100", "new_size": "9"}),
        ]
        rr = self._replay(events)
        derived_types = [d.envelope.event_type for d in rr.derived_events]
        self.assertIn("LIQUIDITY_REMOVE", derived_types)

    def test_replay_iter_records_ordered_matches_replay_records(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"], ["99", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 2, {"side": "BID", "price": "100", "new_size": "9"}),
            _base_event("l2", "LEVEL_SET", 3, {"side": "ASK", "price": "101", "new_size": "9"}),
            _base_event("l3", "LEVEL_SET", 4, {"side": "BID", "price": "100", "new_size": "10"}),
        ]
        engine = ReplayEngineV01(tick_size_by_instrument=self.tick_sizes)
        rr = engine.replay(events)
        ordered = list(engine.iter_records_ordered(events))

        def _key(r):
            return (r.envelope.stream_key(), r.envelope.ordering_key(), 0 if not r.is_derived else 1, r.envelope.event_id)

        rr_sorted = sorted(rr.records, key=_key)
        ordered_sorted = sorted(ordered, key=_key)

        self.assertEqual(len(rr_sorted), len(ordered_sorted))
        for a, b in zip(rr_sorted, ordered_sorted):
            self.assertEqual(a.envelope.event_type, b.envelope.event_type)
            self.assertEqual(a.envelope.event_id, b.envelope.event_id)
            self.assertEqual(a.is_derived, b.is_derived)

    def test_gap_requires_snapshot(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("g1", "SEQUENCE_GAP", 2, {}),
            _base_event("l1", "LEVEL_SET", 3, {"side": "BID", "price": "100", "new_size": "9"}),
        ]
        with self.assertRaises(ValueError):
            self._replay(events)

    def test_pattern_depletion_sequence(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"], ["99", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 10, {"side": "BID", "price": "100", "new_size": "9"}),
            _base_event("l2", "LEVEL_SET", 20, {"side": "BID", "price": "100", "new_size": "8"}),
        ]
        rr = self._replay(events)
        params = {"DepletionSequence": {"side": "BID", "n_ticks": 1, "k": 2, "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["DepletionSequence"])
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].emit["remove_count"], 2)

    def test_pattern_multi_level_erosion(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"], ["99", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 10, {"side": "BID", "price": "100", "new_size": "9"}),
            _base_event("l2", "LEVEL_SET", 20, {"side": "BID", "price": "99", "new_size": "9"}),
        ]
        rr = self._replay(events)
        params = {"MultiLevelErosion": {"side": "BID", "n_ticks": 2, "min_levels": 2, "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["MultiLevelErosion"])
        self.assertEqual(len(occ), 1)

    def test_pattern_touch_reprice_without_print(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"], ["99", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l0", "LEVEL_SET", 10, {"side": "ASK", "price": "102", "new_size": "5"}),
            _base_event("l1", "LEVEL_SET", 20, {"side": "BID", "price": "100", "new_size": "0"}),
        ]
        rr = self._replay(events)
        params = {"TouchRepriceWithoutPrint": {"side": "BID", "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["TouchRepriceWithoutPrint"])
        self.assertEqual(len(occ), 1)
        self.assertEqual(str(occ[0].emit["touch_from"]), "100")
        self.assertEqual(str(occ[0].emit["touch_to"]), "99")

    def test_pattern_print_cluster_at_touch(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("t1", "TRADE_PRINT", 10, {"price": "100", "size": "1"}),
            _base_event("t2", "TRADE_PRINT", 20, {"price": "100", "size": "1"}),
            _base_event("t3", "TRADE_PRINT", 30, {"price": "100", "size": "1"}),
        ]
        rr = self._replay(events)
        params = {"PrintClusterAtTouch": {"side": "BID", "k": 3, "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["PrintClusterAtTouch"])
        self.assertEqual(len(occ), 1)

    def test_pattern_level_flicker_sequence(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 10, {"side": "BID", "price": "100", "new_size": "11"}),
            _base_event("l2", "LEVEL_SET", 20, {"side": "BID", "price": "100", "new_size": "10"}),
            _base_event("l3", "LEVEL_SET", 30, {"side": "BID", "price": "100", "new_size": "11"}),
            _base_event("l4", "LEVEL_SET", 40, {"side": "BID", "price": "100", "new_size": "10"}),
        ]
        rr = self._replay(events)
        params = {
            "LevelFlickerSequence": {"side": "BID", "price": Decimal("100"), "toggles": 2, "max_gap_ms": 1000, "window_ms": 2000}
        }
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["LevelFlickerSequence"])
        self.assertEqual(len(occ), 1)

    def test_pattern_spread_expansion_sequence(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"], ["102", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 10, {"side": "ASK", "price": "101", "new_size": "0"}),
        ]
        rr = self._replay(events)
        params = {"SpreadExpansionSequence": {"min_increase_ticks": 1, "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["SpreadExpansionSequence"])
        self.assertEqual(len(occ), 1)

    def test_context_flags_unstable_segment(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"], ["102", "10"]], "depth_limit": 20},
            ),
            _base_event("l1", "LEVEL_SET", 10, {"side": "ASK", "price": "101", "new_size": "0"}),
        ]
        rr = self._replay(events)
        params = {"SpreadExpansionSequence": {"min_increase_ticks": 1, "window_ms": 1000}}
        occ = PatternEngineV01(self.patterns).run(rr.records, pattern_params=params, enabled_patterns=["SpreadExpansionSequence"])
        ctx = classify_context_core(rr.records, occ, lookback_ms=1000, profile="trader")
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["stability"], "UNSTABLE")
        self.assertTrue(ctx[0]["do_not_operate"])
        self.assertIn("spread_expansion", ctx[0]["patterns_detected"])

    def test_context_beginner_profile_hides_trader_fields(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            )
        ]
        rr = self._replay(events)
        ctx = classify_context_core(rr.records, [], lookback_ms=1000, profile="iniciante")
        self.assertEqual(len(ctx), 1)
        self.assertEqual(ctx[0]["stability"], "STABLE")
        self.assertEqual(ctx[0]["liquidity"], "ABSENT")
        self.assertEqual(ctx[0]["activity"], "COMPRESSED")
        self.assertFalse(ctx[0]["do_not_operate"])
        self.assertNotIn("evidence_event_ids", ctx[0])

    def test_pattern_replenish_after_depletion_sequence(self):
        events = [
            _base_event(
                "s1",
                "BOOK_SNAPSHOT",
                1,
                {"bids": [["100", "10"], ["99", "10"]], "asks": [["101", "10"]], "depth_limit": 20},
            ),
            _base_event("d1", "LEVEL_SET", 10, {"side": "BID", "price": "100", "new_size": "9"}),
            _base_event("d2", "LEVEL_SET", 20, {"side": "BID", "price": "100", "new_size": "8"}),
            _base_event("a1", "LEVEL_SET", 200, {"side": "BID", "price": "100", "new_size": "9"}),
            _base_event("a2", "LEVEL_SET", 210, {"side": "BID", "price": "100", "new_size": "10"}),
        ]
        rr = self._replay(events)
        params = {
            "ReplenishAfterDepletionSequence": {"side": "BID", "n_ticks": 1, "k_depl": 2, "w_depl_ms": 100, "k_add": 2, "w_rec_ms": 500}
        }
        occ = PatternEngineV01(self.patterns).run(
            rr.records, pattern_params=params, enabled_patterns=["ReplenishAfterDepletionSequence"]
        )
        self.assertEqual(len(occ), 1)


if __name__ == "__main__":
    unittest.main()
