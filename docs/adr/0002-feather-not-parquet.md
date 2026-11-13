# Feather/zstd tables and numpy-only statistics

Windows Smart App Control on the demo laptop has blocked the pyarrow `_parquet` and `scipy.stats` DLLs before. Both import today, but a block in the middle of the demo can't be fixed live. So every table is feather (zstd) and every statistic (quantiles, bootstrap, calibration) is written in numpy. Any new compiled dependency must pass `python -c "import X"` on this machine first.
