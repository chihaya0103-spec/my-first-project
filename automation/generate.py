"""Generate one SEO article per run with Claude and publish it into the static site.

Usage:
  python automation/generate.py            # next unpublished topic from topics.json
  python automation/generate.py --fixture  # render with sample data (no API call)
"""
import argparse
import datetime as dt
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://chihaya0103-spec.github.io/my-first-project/"
ARTICLES = ROOT / "articles"
TOPICS = ROOT / "automation" / "topics.json"
MODEL = "claude-opus-5-5"

NICHES = {
    "travel": {
        "label": "子連れ旅行",
        "theme": ("#f6efe6", "#fffaf3", "#2f2a25", "#7a6f64", "#e6dccf", "#e0794f", "#fff",
                  "#1d1a17", "#27231f", "#f1ebe3", "#b3a797", "#3a342e", "#ef8a5f", "#1d1a17"),
        "tools": [("子連れ旅行 持ち物チェックリスト（無料）", "../../"),
                  ("家族旅行 予算シミュレーター（無料）", "../../budget/")],
        "cta_title": "旅行のしおりも作りたい方へ",
        "cta_text": "行程表・予算表・持ち物リストがひとつになった「家族旅行のしおり」テンプレートを販売中。Excelで編集できる版と、すぐ印刷できるPDF版があります。",
        "cta_url": "https://chihayaaa.booth.pm/items/8988556",
        "product": "家族旅行のしおりテンプレート（行程表・予算表・持ち物リスト入り、Excel/PDF）",
        "disclaimer": "内容は一般的な目安です。交通機関や宿泊施設のルールは各公式サイトでご確認ください。",
    },
    "fukugyo": {
        "label": "副業と税金",
        "theme": ("#eef2f0", "#fbfdfc", "#1f2a26", "#5f6f69", "#d6dfdb", "#2f7d62", "#fff",
                  "#151b19", "#1d2522", "#e8efec", "#a3b3ad", "#2f3a36", "#56b48f", "#0f1513"),
        "tools": [("副業の確定申告いる？20万円ルールかんたんチェック（無料）", "../../fukugyo/")],
        "cta_title": "申告の準備を1年分ラクにする",
        "cta_text": "売上と経費を入れるだけで、月別の集計・年間の所得・20万円ルールの判定まで自動で出るExcelシートを販売しています。確定申告の時期にまとめて慌てないために。",
        "cta_url": "https://chihayaaa.booth.pm/items/8996283",
        "product": "副業の売上・経費を入れると月別集計と20万円ルール判定が自動で出るExcelシート",
        "disclaimer": "この記事は国税庁などの公開情報をもとにした一般的な解説です。個別の事情で判断は変わるため、最終的には税務署・市区町村・税理士にご確認ください。",
    },
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "description", "lead", "sections", "faq", "x_post"],
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "lead": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "paragraphs", "bullets"],
                "properties": {
                    "heading": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "faq": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["q", "a"],
                "properties": {"q": {"type": "string"}, "a": {"type": "string"}},
            },
        },
        "x_post": {"type": "string"},
    },
}

SYSTEM = """あなたは日本語で実用記事を書く編集者です。読者の検索意図に正面から答える、具体的で正確な記事を書きます。

方針:
- 検索した人が「この記事だけで解決した」と感じる内容にする。前置き・水増し・同じことの繰り返しは書かない。
- 具体例・手順・数字の目安を入れる。ただし不確かな数字や制度の細部は断定せず「目安」「〜の場合が多い」と書くか、公式情報での確認を促す。
- 税金・制度の話は国税庁・市区町村などの公式情報に沿う範囲で書き、架空の制度や条文を作らない。
- 宣伝臭くしない。商品は本文で押し売りせず、読者の役に立つ文脈でだけ一度触れる程度にする（販売ページへのリンクは別枠で入るので本文にURLは書かない）。
- 見出しは4〜6個。各見出しの本文は合計200〜400字程度。箇条書きが向く内容は bullets に入れる（不要なら空配列）。
- title は32字前後で検索キーワードを自然に含める。description は80〜110字。
- faq は検索で実際に聞かれそうな質問を3〜4個。
- x_post はX（旧Twitter）用の告知文。120字以内、ハッシュタグは2個まで、URLは書かない。
- HTMLやMarkdownの記号は使わず、プレーンテキストで書く。"""


def load_topics():
    return json.loads(TOPICS.read_text(encoding="utf-8"))


def next_topic():
    for t in load_topics():
        if not (ARTICLES / t["slug"] / "index.html").exists():
            return t
    return None


def call_claude(topic):
    import anthropic

    niche = NICHES[topic["niche"]]
    prompt = (
        f"検索キーワード: {topic['keyword']}\n"
        f"記事の切り口: {topic['angle']}\n"
        f"ジャンル: {niche['label']}\n"
        f"サイトで販売している関連商品（本文で自然に触れてよい）: {niche['product']}\n"
        f"サイト内の無料ツール: {', '.join(name for name, _ in niche['tools'])}\n\n"
        "この条件で記事を1本書いてください。"
    )
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason != "end_turn":
        sys.exit(f"Generation stopped: {msg.stop_reason}")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return json.loads(text)


def validate(a):
    problems = []
    body = sum(len(p) for s in a["sections"] for p in s["paragraphs"] + s["bullets"])
    if body < 1500:
        problems.append(f"本文が短すぎます（{body}字）")
    if not 3 <= len(a["sections"]) <= 8:
        problems.append(f"見出し数が想定外です（{len(a['sections'])}）")
    if len(a["faq"]) < 2:
        problems.append("FAQが少なすぎます")
    if re.search(r"https?://|<[a-z]", json.dumps(a, ensure_ascii=False)):
        problems.append("本文にURLかHTMLが含まれています")
    if problems:
        sys.exit("品質チェックNG: " + " / ".join(problems))


def e(s):
    return html.escape(s, quote=True)


def render(topic, a, today):
    n = NICHES[topic["niche"]]
    t = n["theme"]
    url = f"{SITE}articles/{topic['slug']}/"
    secs = []
    for s in a["sections"]:
        parts = [f"<h2>{e(s['heading'])}</h2>"]
        parts += [f"<p>{e(p)}</p>" for p in s["paragraphs"]]
        if s["bullets"]:
            parts.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in s["bullets"]) + "</ul>")
        secs.append("\n".join(parts))
    faq = "\n".join(
        f"<details><summary>{e(f['q'])}</summary><p>{e(f['a'])}</p></details>" for f in a["faq"]
    )
    tools = "\n".join(
        f'<a class="tool" href="{href}">{e(name)} →</a>' for name, href in n["tools"]
    )
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Article", "headline": a["title"], "description": a["description"],
             "datePublished": today, "dateModified": today, "inLanguage": "ja",
             "author": {"@type": "Person", "name": "chihayaaa"}, "mainEntityOfPage": url},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": f["q"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in a["faq"]]},
        ],
    }
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(a['title'])}</title>
<meta name="description" content="{e(a['description'])}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{e(a['title'])}">
<meta property="og:description" content="{e(a['description'])}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<meta name="theme-color" content="{t[0]}">
<script type="application/ld+json">{ld_json}</script>
<style>
:root{{--bg:{t[0]};--card:{t[1]};--ink:{t[2]};--sub:{t[3]};--line:{t[4]};--accent:{t[5]};--accent-ink:{t[6]}}}
@media (prefers-color-scheme: dark){{:root{{--bg:{t[7]};--card:{t[8]};--ink:{t[9]};--sub:{t[10]};--line:{t[11]};--accent:{t[12]};--accent-ink:{t[13]}}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;line-height:1.8}}
.wrap{{max-width:680px;margin:0 auto;padding:20px 16px 80px}}
.crumb{{font-size:.8rem;color:var(--sub)}} .crumb a{{color:var(--sub)}}
h1{{font-size:1.45rem;line-height:1.4;margin:10px 0 6px}}
.date{{font-size:.8rem;color:var(--sub);margin:0 0 16px}}
.lead{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px}}
h2{{font-size:1.15rem;margin:32px 0 8px;padding-left:10px;border-left:4px solid var(--accent);line-height:1.45}}
ul{{padding-left:1.3em}} li{{margin:4px 0}}
.tools{{display:grid;gap:8px;margin:28px 0}}
.tool{{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;color:var(--ink);text-decoration:none;font-weight:bold}}
.cta{{background:var(--card);border:2px solid var(--accent);border-radius:16px;padding:18px 16px;margin:28px 0}}
.cta h2{{border:none;padding:0;margin:0 0 6px;font-size:1.05rem}}
.cta p{{margin:0 0 12px;font-size:.92rem;color:var(--sub)}}
.btn{{display:block;text-align:center;background:var(--accent);color:var(--accent-ink);text-decoration:none;font-weight:bold;padding:13px;border-radius:12px}}
details{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px 14px;margin-bottom:10px}}
summary{{font-weight:bold;cursor:pointer}}
footer{{color:var(--sub);font-size:.76rem;margin-top:32px;line-height:1.7}} footer a{{color:var(--sub)}}
</style>
</head>
<body>
<div class="wrap">
<nav class="crumb"><a href="../../">トップ</a> › <a href="../">記事一覧</a> › {e(n['label'])}</nav>
<h1>{e(a['title'])}</h1>
<p class="date">{today} 公開</p>
<p class="lead">{e(a['lead'])}</p>
{chr(10).join(secs)}
<div class="tools">
{tools}
</div>
<div class="cta">
  <h2>{e(n['cta_title'])}</h2>
  <p>{e(n['cta_text'])}</p>
  <a class="btn" href="{n['cta_url']}" target="_blank" rel="noopener">BOOTHで見てみる</a>
</div>
<h2>よくある疑問</h2>
{faq}
<footer>{e(n['disclaimer'])}<br><a href="../">記事一覧</a> ／ <a href="../../">子連れ旅行 持ち物チェックリスト</a> ／ <a href="../../fukugyo/">副業20万円ルールチェック</a><br>© chihayaaa</footer>
</div>
</body>
</html>
"""


def write_index():
    items = []
    for meta_path in ARTICLES.glob("*/meta.json"):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        items.append(m)
    items.sort(key=lambda m: m["date"], reverse=True)
    lis = "\n".join(
        f'<li><a href="{m["slug"]}/">{e(m["title"])}</a><small>{m["date"]} ・ {e(NICHES[m["niche"]]["label"])}</small></li>'
        for m in items
    )
    (ARTICLES / "index.html").write_text(f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>記事一覧｜子連れ旅行と副業のお役立ちメモ</title>
<meta name="description" content="子連れ旅行の準備や、会社員の副業と確定申告について、無料ツールとあわせて使える解説記事の一覧です。">
<link rel="canonical" href="{SITE}articles/">
<style>
:root{{--bg:#f6efe6;--card:#fffaf3;--ink:#2f2a25;--sub:#7a6f64;--line:#e6dccf;--accent:#e0794f}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1d1a17;--card:#27231f;--ink:#f1ebe3;--sub:#b3a797;--line:#3a342e;--accent:#ef8a5f}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;line-height:1.7}}
.wrap{{max-width:680px;margin:0 auto;padding:20px 16px 80px}}
h1{{font-size:1.4rem}} ul{{list-style:none;padding:0}}
li{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px}}
li a{{color:var(--ink);font-weight:bold;text-decoration:none}} li small{{display:block;color:var(--sub);font-size:.78rem}}
footer{{color:var(--sub);font-size:.78rem}} footer a{{color:var(--sub)}}
</style>
</head>
<body>
<div class="wrap">
<h1>記事一覧</h1>
<ul>
{lis}
</ul>
<footer><a href="../">子連れ旅行 持ち物チェックリスト</a> ／ <a href="../budget/">家族旅行 予算シミュレーター</a> ／ <a href="../fukugyo/">副業20万円ルールチェック</a><br>© chihayaaa</footer>
</div>
</body>
</html>
""", encoding="utf-8")


def update_sitemap(today):
    path = ROOT / "sitemap.xml"
    xml = path.read_text(encoding="utf-8")
    locs = re.findall(r"<loc>(.*?)</loc>", xml)
    wanted = [f"{SITE}articles/"] + [
        f"{SITE}articles/{p.parent.name}/" for p in sorted(ARTICLES.glob("*/meta.json"))
    ]
    add = "".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n" for u in wanted if u not in locs
    )
    if add:
        path.write_text(xml.replace("</urlset>", add + "</urlset>"), encoding="utf-8")


def fixture(topic):
    para = "ここにはサンプルの本文が入ります。" * 12
    return {
        "title": f"【サンプル】{topic['keyword']}のまとめ",
        "description": "動作確認用のサンプル記事です。" * 4,
        "lead": "動作確認用のリード文です。",
        "sections": [{"heading": f"見出し{i}", "paragraphs": [para, para], "bullets": ["項目A", "項目B"]}
                     for i in range(1, 5)],
        "faq": [{"q": "質問1？", "a": "回答1です。"}, {"q": "質問2？", "a": "回答2です。"}],
        "x_post": "サンプルの告知文です #テスト",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true", help="render sample data without calling the API")
    args = ap.parse_args()

    topic = next_topic()
    if topic is None:
        print("All topics are published. Add more to automation/topics.json.")
        return
    today = dt.date.today().isoformat()
    article = fixture(topic) if args.fixture else call_claude(topic)
    validate(article)

    out = ARTICLES / topic["slug"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(topic, article, today), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(
        {"slug": topic["slug"], "niche": topic["niche"], "title": article["title"], "date": today},
        ensure_ascii=False, indent=2), encoding="utf-8")
    write_index()
    update_sitemap(today)

    posts = ROOT / "automation" / "x_posts.md"
    with posts.open("a", encoding="utf-8") as f:
        f.write(f"\n## {today} {article['title']}\n{article['x_post']}\n{SITE}articles/{topic['slug']}/\n")
    print(f"Published: articles/{topic['slug']}/ — {article['title']}")


if __name__ == "__main__":
    main()
