<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

視覚データセット作成のためのプロダクションパイプライン：基本ルールから構造化されたプロンプト、ComfyUIによる生成、そして厳選された、基本ルールに準拠したトレーニングデータまで。

## これは何ですか？

構造化された視覚トレーニングデータセットを構築するための**パイプライン**です。スタイルルール（基本ルール）を記述し、プロンプトを作成し、ComfyUIで生成し、各次元のスコアリングによる厳選を行い、判断を基本ルールに紐付け、`@mcptoolshop/repo-dataset` (https://github.com/mcp-tool-shop-org/repo-dataset) を使用して10種類の形式でエクスポートします。

このパイプラインは、特定のゲームに依存しません。各ゲームごとに、`games/<ゲーム名>/` の下にデータディレクトリが作成され、13個のスクリプトとテンプレートが共有されます。生成されるすべてのデータには、以下の3つの情報が含まれます。

1. **画像ピクセル**：ComfyUIによって生成され、完全な情報（チェックポイント、LoRA、シード値、サンプラー、CFG）が付与されています。
2. **規範的な説明**：なぜこの画像が特定のスタイルに合致しているか、または合致していないかを、スタイルに関する規定に基づいて説明します。
3. **品質評価**：各次元のスコアと参照ルールに基づいて、承認/却下の判断がなされます。

## セキュリティモデル

**ローカル環境のみ**。style-dataset-labは、`localhost:8188`で動作するComfyUIとのみ通信し、外部ネットワークへのアクセスは一切行いません。テレメトリー、分析、データ送信機能は一切ありません。画像生成はすべて、お客様のGPU上で行われます。記録データと規範データは、お客様のファイルシステム上に保存されます。

## このnpmパッケージに含まれるもの

`npm install @mcptoolshop/style-dataset-lab` を実行すると、以下のものが利用できます。

- **13個のスクリプト**：生成、厳選、比較、基本ルールへの紐付け、絵画風生成、同一性生成、ControlNet/IP-Adapter生成、一括厳選、移行
- **テンプレート**：`templates/` に、初期設定ファイル、レビュー基準、およびサンプルプロンプトが含まれています。

このnpmパッケージには、ゲームデータは含まれていません。Star Freightのサンプルデータが必要な場合は、リポジトリをクローンしてください（1,182件のデータ、28種類のプロンプト、18種類の視覚カテゴリ）。

## インストール

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

新しいゲームをテンプレートから開始するには：

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## モノレポの構造

このパイプラインは、`scripts/` と `templates/` にあります。各ゲームは、`games/<ゲーム名>/` に、それぞれの基本ルール、データ、およびアセットとともに配置されます。スクリプトは `--game <ゲーム名>` オプションを受け入れます（デフォルトは `star-freight`）。

```
style-dataset-lab/
  scripts/                  13 pipeline scripts (generate, curate, compare, etc.)
  templates/                Blank starting point for new games
    canon/                  Starter constitution + review rubric
    inputs/prompts/         Example prompt pack
  games/
    star-freight/           Star Freight example (1,182 records, repo-only)
      canon/                Style constitution, review rubric, species canon
      records/              Per-asset JSON (provenance + judgment + canon)
      comparisons/          A-vs-B preference judgments
      inputs/               Prompt packs, identity packets, references
      outputs/              Generated images (gitignored)
      exports/              repo-dataset output (gitignored)
    <your-game>/            Add more games with the same structure
```

## パイプラインのワークフロー

基本ルールからトレーニングデータのエクスポートまでの完全なパイプライン：

```bash
# 1. Write your canon -- style constitution + review rubric
#    (start from templates/ or write from scratch)

# 2. Create prompt packs in inputs/prompts/
#    (see templates/inputs/prompts/example-wave.json)

# 3. Start ComfyUI and generate candidates
npm run generate -- --game star-freight inputs/prompts/wave1.json
npm run generate -- --game star-freight inputs/prompts/wave1.json --dry-run

# 4. Generate identity-packet characters (named subjects)
npm run generate:identity -- --game star-freight inputs/identity-packets/wave27a.json

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- --game star-freight <asset_id> approved "explanation"
npm run curate -- --game star-freight <asset_id> rejected "explanation" --failures "too_clean"

# 6. Generate painterly variants of approved assets
npm run painterly -- --game star-freight

# 7. Bind canon explanations to curated assets
npm run canon-bind -- --game star-freight

# 8. Record pairwise comparisons
npm run compare -- --game star-freight <asset_a> <asset_b> a "A has better faction read"

# 9. Export training data via repo-dataset
repo-dataset visual generate ./games/star-freight --format trl
repo-dataset visual inspect ./games/star-freight
```

## 新しいゲームの追加

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## ゲームごとのディレクトリ構成

各 `games/<ゲーム名>/` ディレクトリには、以下のものが含まれます：

```
canon/                  Style constitution, review rubric, species canon, identity gates
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
```

## 生成設定

```yaml
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8
cfg: 2.0
sampler: dpmpp_sde
scheduler: karras
speed: ~9s per image (RTX 5080)
```

追加の生成モード：ControlNet（ポーズ/深度ガイド）、IP-Adapter（参照ベース）、IDパケット（名前付きキャラクターの一貫性）。

## 必要なもの

- `localhost:8188`で動作する[ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo チェックポイント + ClassipeintXL LoRA
- Node.js 20以上
- トレーニング用エクスポートのための[`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)

## ライセンス

MIT

---

開発：<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
