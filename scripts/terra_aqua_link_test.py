"""Terra-MODIS -> Aqua-MODIS: the same held-out test as the shipped links (leave-one-year-out over 2003-2021, Aqua's
stable orbit). Rule fixed before running: passes only if the out-of-fold 90% band covers 88-95% of region-weeks AND
the out-of-fold region-month WAPE is no worse than the shipped headline link's (S-NPP -> Aqua, 0.0857)."""
import json

from godseye.config import get_config
from godseye.harmonize import archive
from godseye.harmonize.link import fit_link
from godseye.harmonize.series import paired_days, weekly_pairs

cfg = get_config()
h = cfg.harmonize
grid, avail = archive.load_record(cfg.processed_dir, h["metric"])
days = archive.in_window(paired_days(avail, "Terra-MODIS", "Aqua-MODIS"), [2003, 2021])
df = weekly_pairs(grid, days, "Terra-MODIS", "Aqua-MODIS", h["region_deg"], h["metric"])
link = fit_link(df, "Terra-MODIS", "Aqua-MODIS", False, h["region_deg"])
s = link.report["cv_scores"][link.method]
cov = link.report["band_coverage_out_of_fold"]
passed = 0.88 <= cov <= 0.95 and s["region_month_wape"] <= 0.0857
out = {"paired_days": len(days), "folds": len(link.report["folds"]), "method": link.method,
       "ratio": round(float(link.ratios()), 4), "cv_scores": link.report["cv_scores"],
       "band_coverage_out_of_fold": cov, "versus_global_ratio": link.report["versus_global_ratio"],
       "rule": "band coverage 0.88-0.95 and region-month WAPE <= 0.0857", "passes": passed}
print(json.dumps(out, indent=1, default=str))
(cfg.root / "reports" / "terra_aqua_link_test.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
