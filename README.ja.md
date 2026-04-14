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

Visual dataset factory：VLMのファインチューニングのための、多様なトレーニングデータを生成、キュレーション、エクスポートします。

## これは何ですか？

「学習可能なビジュアル真実」を構築するためのツールキットです。各アセットには、以下の3つの情報が含まれています。

1. **画像ピクセル**：ComfyUIによって生成され、完全な情報（チェックポイント、LoRA、シード値、サンプラー、CFG）が付与されています。
2. **規範的な説明**：なぜこの画像が特定のスタイルに合致しているか、または合致していないかを、スタイルに関する規定に基づいて説明します。
3. **品質評価**：各次元のスコアと参照ルールに基づいて、承認/却下の判断がなされます。

生成されたデータは、[`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)に連携し、10種類の形式（TRL、LLaVA、Qwen2-VL、Axolotl、LLaMA-Factory、ShareGPT、RLHFペア、DPO、キャプション、分類）で、多様なトレーニングデータを作成します。

## セキュリティモデル

**ローカル環境のみ**。style-dataset-labは、`localhost:8188`で動作するComfyUIとのみ通信し、外部ネットワークへのアクセスは一切行いません。テレメトリー、分析、データ送信機能は一切ありません。画像生成はすべて、お客様のGPU上で行われます。記録データと規範データは、お客様のファイルシステム上に保存されます。

## データセットの統計

| 指標 | 値 |
|--------|-------|
| キュレーションされたデータ | 1,182 |
| 総アセット数 | 2,571件（承認済み：893件、ペインタリーバリアント：887件） |
| プロンプトの種類 | 28 |
| ビジュアルカテゴリ | 18種類（衣装、船、内装、装備、環境、生物、ステーション、標識、照明、貨物、アーキテクチャ、生物、表面、日常生活、惑星、損傷/修理、異星生物、生活感のあるディテール） |
| ペア比較 | 人間による評価：6件、合成データ：71件 |
| 拒否の種類 | 30+ |
| IDパケットシステム | 派閥、ランク、視覚的な特徴を持つ名前付きキャラクター |
| エクスポート形式 | 10種類（@mcptoolshop/repo-dataset経由） |

## インストール

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

次に、プロジェクトをクローンするか、新しいデータセットの作業領域を初期化します。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## ワークフロー

```bash
# 1. Start ComfyUI
# (point it at your checkpoint + LoRA setup)

# 2. Generate candidates from a prompt pack
npm run generate -- inputs/prompts/wave1.json
npm run generate -- inputs/prompts/wave1.json --dry-run

# 3. Generate identity-packet characters
npm run generate:identity -- inputs/identity-packets/wave27a-identity-spine.json

# 4. Generate painterly variants of approved assets
npm run painterly -- <asset_id>

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- <asset_id> approved "explanation" --scores "silhouette:0.9,palette:0.8"
npm run curate -- <asset_id> rejected "explanation" --failures "too_clean,wrong_material"

# 6. Bind canon explanations to assets
npm run canon-bind -- <asset_id>

# 7. Record pairwise comparisons
npm run compare -- <asset_a> <asset_b> a "A has better faction read because..."

# 8. Export training data via repo-dataset
npm run export
npm run inspect
npm run validate
```

## ディレクトリ構造

```
canon/                  Style constitution, review rubric, identity gates, species canon
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control/              ControlNet control images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines (faction DNA, rank, visual anchors)
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
scripts/                generate, curate, compare, canon-bind, painterly, identity gen
workflows/              Reusable ComfyUI workflow templates
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
