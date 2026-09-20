from first_trade_postmortem import MINUTE, excursion_report, exit_mechanism, missing_opens, normalize


def test_normalize_dedupes_and_clips_confirmed_bars():
    rows=[["60000","1","3","0.5","2","0","0","0","1"],["0","1","2","0","1","0","0","0","1"],
          ["60000","1","4","0.4","3","0","0","0","1"],["120000","1","5","0.3","4","0","0","0","0"]]
    bars=normalize(rows,MINUTE,0,120000)
    assert [b["ot"] for b in bars]==[0,60000]
    assert bars[-1]["h"]==4.0


def test_missing_opens_detects_internal_gap():
    bars=[{"ot":0},{"ot":120000}]
    assert missing_opens(bars,0,180000,MINUTE)==[60000]


def test_long_excursion_reports_mfe_and_mae_in_r():
    trade={"entry":100.0,"stop":98.0,"target":104.0,"side":"LONG"}
    bars=[{"ot":0,"h":102.0,"l":99.0},{"ot":60000,"h":101.0,"l":98.5}]
    out=excursion_report(trade,bars)
    assert out["mfe_R"]==1.0
    assert out["mae_R_before_exit"]==0.75
    assert out["target_progress_fraction"]==0.5


def test_unaligned_stop_timestamp_proves_ticker_exit_path():
    out=exit_mechanism({"closed_ms":1234567})
    assert out["mechanism"]=="CURRENT_TICKER_STOP"
    assert out["closed_ms_aligned_to_minute"] is False


def run_all():
    tests=[test_normalize_dedupes_and_clips_confirmed_bars,test_missing_opens_detects_internal_gap,
           test_long_excursion_reports_mfe_and_mae_in_r,test_unaligned_stop_timestamp_proves_ticker_exit_path]
    for fn in tests:fn()
    print(f"FIRST_TRADE_POSTMORTEM_TEST=PASS cases={len(tests)} read_only=true")


if __name__=="__main__":run_all()
