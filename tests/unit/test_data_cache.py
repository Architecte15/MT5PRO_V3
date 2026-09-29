import pandas as pd
from app.data.data_cache import DataCache


def test_cache_deduplicates_latest():
    idx = pd.date_range("2026-01-01", periods=2, freq="h")
    c=DataCache(); c.put("x", pd.DataFrame({"close":[1,2]}, index=idx))
    out=c.append("x", pd.DataFrame({"close":[3]}, index=[idx[1]]))
    assert len(out)==2 and out.loc[idx[1],"close"]==3
