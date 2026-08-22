# -*- coding: utf-8 -*-
"""実データの取得(ここだけネットを使う。エンジンはオフラインのまま)。

出所は二つとも公開データ。**食い違いを仕込まないため**、加工はせず
そのまま落とす。落とし先は既定でスクラッチパッド — 大きい生データを
リポジトリに置かないため。
"""
import sys
import urllib.request
from pathlib import Path

SOURCES = {
    "ibaraki.geojson":
        "https://www.geospatial.jp/ckan/dataset/"
        "9d25c0e6-6b5b-4a2a-9b6b-4b4b0a1f0e2f/resource/PLACEHOLDER",
    "ibaraki.csv":
        "https://www.geospatial.jp/ckan/dataset/"
        "b3e1a2b5-0178-4fb7-8c4e-931c156f7ebb/resource/"
        "dc682370-9364-4b16-a80d-3f8898e0abdf/download/.csv",
}
CATALOGUE = ("https://www.geospatial.jp/ckan/api/3/action/package_search"
             "?q={q}&rows=1")


def resolve_geojson(query: str = "指定緊急避難場所データ 茨城") -> str:
    """GeoJSON の URL は資源IDが変わるので、目録から引き直す。"""
    import json
    import urllib.parse

    url = CATALOGUE.format(q=urllib.parse.quote(query))
    with urllib.request.urlopen(url, timeout=60) as r:
        pkg = json.load(r)["result"]["results"][0]
    for res in pkg["resources"]:
        if str(res.get("format", "")).upper() == "GEOJSON":
            return res["url"]
    raise SystemExit("GeoJSON が目録に無い")


def main(dest: str) -> int:
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    urls = dict(SOURCES)
    urls["ibaraki.geojson"] = resolve_geojson()
    for name, url in urls.items():
        path = out / name
        print(f"取得: {name} <- {url[:80]}")
        urllib.request.urlretrieve(url, path)
        print(f"   {path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
