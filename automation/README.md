# AI記事の自動公開

毎朝6:17（日本時間）に GitHub Actions が動き、`topics.json` の未公開テーマから1本、Claude で記事を書いて `articles/` に公開します。

- 記事には関連する無料ツールと BOOTH 商品への導線が自動で入ります
- `articles/index.html`（記事一覧）と `sitemap.xml` も自動更新
- X 用の告知文は `automation/x_posts.md` にたまるので、コピペで投稿できます
- 本文が短い・URL/HTML混入などは品質チェックで止まり、公開されません

## 最初に1回だけやること

1. https://console.anthropic.com で API キーを作る（クレジットを少額チャージ。1記事あたり数十円程度）
2. GitHub のこのリポジトリ → Settings → Secrets and variables → Actions → New repository secret
   - Name: `ANTHROPIC_API_KEY` / Secret: 作ったキー
3. Actions タブ → 「Daily AI article」→ Run workflow で1本目をすぐ出せます

## テーマを増やす

`topics.json` に1行足すだけです。`niche` は `travel` か `fukugyo`。

## 手元で試す

```
pip install -r automation/requirements.txt
python automation/generate.py --fixture   # APIを使わずサンプルで表示確認
```
