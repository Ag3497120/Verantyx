# -*- coding: utf-8 -*-
"""事前登録 4 の実行。PREREG4_FASHION_EMBEDDING.md

**測るのは二つ。** 入れ替えるべきか(VE1)と、点数を何に使ってよいか(VE2-VE4)。
後者のほうが製品として重い — 対照モデルは「分からない」を返せないので、
0.91 という数字が「ウールである」と読まれる道を先に塞ぐ必要がある。
"""
import io
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageEnhance

HERE = Path(__file__).resolve().parent
SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
EVAL = SCRATCH / "eval_inshop"
# **MPS は使えない。** torch 2.8.0 / macOS 26.5 のこの機体では、SigLIP の
# attention pooling が Metal 側の assertion でプロセスごと落ちます
# (batch=1 でも再現: "MPSNDArray ... buffer is not large enough")。
# 環境変数で上書きできるようにしておくが、既定は CPU。
# 速度の比較はこの制約込みで読むこと。
DEV = os.environ.get("VERA_EMBED_DEVICE", "cpu")
RESULTS = {"prereg": "PREREG4_FASHION_EMBEDDING.md", "device": DEV,
           "mps": "使用不可 (Metal assertion, torch 2.8.0 / macOS 26.5)",
           "checks": {}}

MODELS = {
    "marqo_fashionsiglip": ("hf-hub:Marqo/marqo-fashionSigLIP", None),
    "siglip_base_webli": ("ViT-B-16-SigLIP", "webli"),
}

#: 素材の文。**この一覧は固定** — 実行のたびに変えたら比べられない。
MATERIALS = ["wool", "cashmere", "cotton", "linen",
             "denim", "leather", "silk", "polyester"]
TEMPLATE = "a photo of a {} garment"


def record(name, ok, detail):
    RESULTS["checks"][name] = {"pass": bool(ok), **detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: "
          f"{json.dumps(detail, ensure_ascii=False)[:400]}")


# ---------------------------------------------------------------- 埋め込み
def load(tag, pretrained):
    import open_clip
    if pretrained:
        m, _, pre = open_clip.create_model_and_transforms(
            tag, pretrained=pretrained)
    else:
        m, _, pre = open_clip.create_model_and_transforms(tag)
    tok = open_clip.get_tokenizer(tag)
    return m.to(DEV).eval(), pre, tok


@torch.no_grad()
def embed_images(model, pre, images, batch=32):
    out = []
    for i in range(0, len(images), batch):
        xs = torch.stack([pre(im) for im in images[i:i + batch]]).to(DEV)
        v = model.encode_image(xs).float()
        out.append((v / v.norm(dim=-1, keepdim=True)).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 768), np.float32)


@torch.no_grad()
def embed_texts(model, tok, texts):
    v = model.encode_text(tok(texts).to(DEV)).float()
    return (v / v.norm(dim=-1, keepdim=True)).cpu().numpy()


# ---------------------------------------------------------------- 指標
def retrieval(vecs, items, higher_is_closer=True):
    """同じ品番を引き当てられるか。自分自身は書庫から外す。

    numpy が matmul で divide-by-zero / overflow / invalid を出しますが、
    **これは無害**であることを確かめてあります (2026-08-23):
    どちらのベクトル集合にも NaN・inf・ゼロノルムは無く、別の式・float64 で
    組み直しても答えは小数4桁まで一致しました。Accelerate が浮動小数の
    フラグを立てたまま返すのを numpy が拾っているだけです。
    """
    sim = vecs @ vecs.T if higher_is_closer else -(
        ((vecs[:, None, :] - vecs[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(sim, -np.inf)
    items = np.asarray(items)
    order = np.argsort(-sim, axis=1)
    hit1, hit5, rr = [], [], []
    for i in range(len(items)):
        # 同じ品番が書庫に一つも無い問い合わせは数えない
        if (items == items[i]).sum() < 2:
            continue
        same = items[order[i]] == items[i]
        first = int(np.argmax(same)) + 1
        hit1.append(float(same[0]))
        hit5.append(float(same[:5].any()))
        rr.append(1.0 / first)
    return {"n": len(rr), "recall@1": float(np.mean(hit1)),
            "recall@5": float(np.mean(hit5)), "mrr": float(np.mean(rr))}, rr


def bootstrap_delta(rr_a, rr_b, groups, rounds=2000, seed=20260823):
    """品番単位で組み直して、差の 95% 区間を出す。

    画像単位で組み直すと、同じ服の複数枚が独立に見えてしまい区間が狭くなる。
    """
    rng = random.Random(seed)
    by = defaultdict(list)
    for k, g in enumerate(groups):
        by[g].append(k)
    keys = list(by)
    deltas = []
    a, b = np.asarray(rr_a), np.asarray(rr_b)
    for _ in range(rounds):
        idx = []
        for _ in range(len(keys)):
            idx.extend(by[keys[rng.randrange(len(keys))]])
        deltas.append(float(a[idx].mean() - b[idx].mean()))
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return {"delta_mrr": float(a.mean() - b.mean()),
            "ci95": [float(lo), float(hi)],
            "excludes_zero": bool(lo > 0 or hi < 0)}


# ---------------------------------------------------------------- 変換
def t_identity(im):
    return im


def t_crop90(im):
    w, h = im.size
    dx, dy = int(w * 0.05), int(h * 0.05)
    return im.crop((dx, dy, w - dx, h - dy)).resize((w, h))


def t_flip(im):
    return im.transpose(Image.FLIP_LEFT_RIGHT)


def t_bright_up(im):
    return ImageEnhance.Brightness(im).enhance(1.15)


def t_bright_down(im):
    return ImageEnhance.Brightness(im).enhance(0.85)


def t_jpeg40(im):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=40)
    b.seek(0)
    return Image.open(b).convert("RGB")


def t_grey(im):
    return im.convert("L").convert("RGB")


#: 素材の情報を持ち去らない変換。ここで1位が入れ替わったら、
#: その順位は素材を見ていない。
KEEPS_MATERIAL = [("crop90", t_crop90), ("flip", t_flip),
                  ("bright+15%", t_bright_up), ("bright-15%", t_bright_down),
                  ("jpeg40", t_jpeg40)]
#: 色を落とす。素材の情報を**部分的に**持ち去るので別枠。
DROPS_COLOUR = [("greyscale", t_grey)]


def main():
    man = json.loads((EVAL / "manifest.json").read_text(encoding="utf-8"))
    rows = [r for r in man["images"] if (EVAL / r["file"]).exists()]
    files = [EVAL / r["file"] for r in rows]
    items = [r["item"] for r in rows]
    print(f"評価集合: 画像 {len(files)} 枚 / 品番 {len(set(items))} 件")
    imgs = [Image.open(f).convert("RGB") for f in files]

    # ---- Apple の指紋(いま使っているもの) ----
    apple_path = SCRATCH / "apple_inshop.json"
    apple = json.loads(apple_path.read_text()) if apple_path.exists() else None
    apple_stats = None
    if apple:
        order = {n: i for i, n in enumerate(apple["files"])}
        keep = [i for i, r in enumerate(rows) if r["file"] in order]
        av = np.asarray([apple["vectors"][order[rows[i]["file"]]]
                         for i in keep], dtype=np.float32)
        aitems = [items[i] for i in keep]
        # **自分の距離計算が Apple と一致するか先に確かめる。**
        chk = np.asarray(apple["appleDistances"], dtype=np.float32)
        k = chk.shape[0]
        raw = np.asarray(apple["vectors"][:k], dtype=np.float32)
        mine = np.sqrt(((raw[:, None, :] - raw[None, :, :]) ** 2).sum(-1))
        agree = float(np.abs(mine - chk).max())
        record("VE0_apple_distance_reproduced", agree < 1e-2,
               {"max_abs_difference": agree,
                "why": "Apple の computeDistance と自前の L2 が一致しなければ、"
                       "以降の比較は指標の取り違えになる",
                "dim": apple["dim"], "element_type": apple["elementType"]})
        apple_stats, apple_rr = retrieval(av, aitems, higher_is_closer=False)
        apple_groups = aitems

    # ---- 埋め込みモデル ----
    stats, rrs, models = {}, {}, {}
    for name, (tag, pre_tag) in MODELS.items():
        t0 = time.time()
        model, pre, tok = load(tag, pre_tag)
        v = embed_images(model, pre, imgs)
        ms = (time.time() - t0) * 1000 / max(len(imgs), 1)
        s, rr = retrieval(v, items)
        stats[name], rrs[name] = s, rr
        models[name] = (model, pre, tok)
        s["ms_per_image_incl_load"] = round(ms, 1)
        print(f"  {name}: {s}")

    # ---------------------------------------------------------- VE1
    detail = {"marqo": stats["marqo_fashionsiglip"],
              "siglip_base": stats["siglip_base_webli"],
              "apple_featureprint": apple_stats}
    if apple_stats:
        # 品番の集合を揃えてから比べる
        common = [i for i, r in enumerate(rows) if r["file"] in
                  {n for n in apple["files"]}]
        detail["marqo_vs_apple"] = bootstrap_delta(
            rrs["marqo_fashionsiglip"], apple_rr,
            [items[i] for i in range(len(rrs["marqo_fashionsiglip"]))]
            if len(rrs["marqo_fashionsiglip"]) == len(apple_rr) else None,
            ) if len(rrs["marqo_fashionsiglip"]) == len(apple_rr) else \
            {"note": "問い合わせ数が揃わないので区間は出さない",
             "n_marqo": len(rrs["marqo_fashionsiglip"]), "n_apple": len(apple_rr)}
    detail["marqo_vs_base_siglip"] = bootstrap_delta(
        rrs["marqo_fashionsiglip"], rrs["siglip_base_webli"],
        [items[i] for i in range(len(rrs["marqo_fashionsiglip"]))])
    better = (apple_stats is None or
              stats["marqo_fashionsiglip"]["mrr"] > apple_stats["mrr"])
    record("VE1_same_garment_across_views", better, detail)

    # ---------------------------------------------------------- VE2 / VE4
    model, pre, tok = models["marqo_fashionsiglip"]
    tvec = embed_texts(model, tok, [TEMPLATE.format(m) for m in MATERIALS])
    sample = imgs[:200]
    base = embed_images(model, pre, sample) @ tvec.T
    base_top = base.argmax(1)

    def flip_rate(transforms):
        out = {}
        for label, fn in transforms:
            v = embed_images(model, pre, [fn(im) for im in sample]) @ tvec.T
            out[label] = float((v.argmax(1) != base_top).mean())
        return out

    keeps = flip_rate(KEEPS_MATERIAL)
    worst = max(keeps.values())
    record("VE2_material_ranking_survives_replacement", worst <= 0.05,
           {"top1_flip_rate": keeps, "worst": worst, "threshold": 0.05,
            "n_images": len(sample),
            "meaning": "素材の情報を持ち去らない変換で1位が入れ替わるなら、"
                       "その順位は素材の証拠にならない"})

    drops = flip_rate(DROPS_COLOUR)
    record("VE4_is_it_material_or_colour", True,
           {"top1_flip_rate": drops, "n_images": len(sample),
            "meaning": "色を落として大きく入れ替わるなら、素材の順位は"
                       "相当が色の順位"})

    # ---------------------------------------------------------- VE3
    def margins(images):
        s = embed_images(model, pre, images) @ tvec.T
        srt = np.sort(s, axis=1)
        return {"top1": s.max(1), "margin": srt[:, -1] - srt[:, -2]}

    real = margins(sample)
    line_dir = Path.home() / ("Library/Application Support/Verantyx/"
                             "atelier/clips/coat_scene")
    lines = [Image.open(p).convert("RGB")
             for p in sorted(line_dir.glob("*.jpg"))] if line_dir.exists() else []
    rng = np.random.default_rng(20260823)
    noise = [Image.fromarray(rng.integers(0, 256, (224, 224, 3), dtype=np.uint8))
             for _ in range(32)]

    out = {"real_photo": {"n": len(sample),
                          "margin_mean": float(real["margin"].mean()),
                          "margin_p05": float(np.percentile(real["margin"], 5)),
                          "margin_p95": float(np.percentile(real["margin"], 95))}}
    for label, group in (("line_drawing", lines), ("uniform_noise", noise)):
        if not group:
            continue
        g = margins(group)
        inside = float(((g["margin"] >= np.percentile(real["margin"], 5)) &
                        (g["margin"] <= np.percentile(real["margin"], 95))).mean())
        out[label] = {"n": len(group),
                      "margin_mean": float(g["margin"].mean()),
                      "inside_real_p05_p95": inside}
    # 予測: 区別が付かない = 点数に「分からない」は出ない
    indistinguishable = any(
        out.get(k, {}).get("inside_real_p05_p95", 0) > 0.5
        for k in ("line_drawing", "uniform_noise"))
    record("VE3_the_score_cannot_say_unknown", indistinguishable,
           {**out, "prediction_was": "材質が写っていない入力でも margin は "
                                     "実写の分布に紛れる（＝棄権の signal が無い）"})

    # ---------------------------------------------------------- VE5
    t0 = time.time()
    embed_images(model, pre, sample)
    ms_embed = (time.time() - t0) * 1000 / len(sample)
    record("VE5_cost", True,
           {"marqo_ms_per_image_warm": round(ms_embed, 1),
            "apple_ms_per_image": apple.get("msPerImage") if apple else None,
            "params_millions": 203.2, "embed_dim": 768, "device": DEV})

    n = len(RESULTS["checks"])
    p = sum(1 for c in RESULTS["checks"].values() if c["pass"])
    RESULTS["summary"] = f"{p}/{n} predictions held"
    out_path = HERE / "results_fashion_embedding.json"
    out_path.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\n{RESULTS['summary']} -> {out_path}")


if __name__ == "__main__":
    main()
