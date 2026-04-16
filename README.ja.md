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

承認済みの画像データを、バージョン管理された、レビューに基づいたデータセット、分割データ、エクスポートパッケージ、および評価用パッケージに変換します。

## これは何ですか？

**画像データ管理とデータセット生成のパイプライン**。プロジェクトのイメージを定義します。規定に基づいてデータを選別します。データ漏洩を防ぐための分割データセットを作成します。将来のモデル検証のための評価用パッケージを生成します。

このパイプラインは、以下の4つの成果物（アーティファクト）を生成します。

| 成果物 | 内容 |
|----------|-----------|
| **Snapshot** | 選択されたデータレコードの、不変で、フィンガープリントが付与されたもの。各データレコードの採用には、明確な理由が記録されています。 |
| **Split** | データ漏洩を防ぐための、トレーニングデータ/検証データ/テストデータの分割。同じ対象を含むデータレコードは、常に同じ分割に分類されます。 |
| **Export package** | 自己完結型のデータセット：マニフェスト、メタデータ、画像、分割データ、データセットの説明、およびチェックサム。 |
| **Eval pack** | 規定に準拠した検証タスク：表現の網羅性、許容されない変化、基準/正解データ、対象の一貫性。 |

このパイプライン内のすべてのデータには、以下の3つの情報が含まれています。

1. **生成履歴 (Provenance)**：完全な生成履歴（チェックポイント、LoRA、シード値、サンプラー、CFG値、実行時間）
2. **規定への適合性 (Canon binding)**：このデータが、どの規定に適合し、不適合であり、または部分的に適合しているか
3. **品質評価 (Quality judgment)**：承認/拒否/境界値、および各評価項目のスコア

ゲームアート、キャラクターデザイン、クリーチャーデザイン、アーキテクチャ、車両/メカのコンセプト、および、画像データの品質を維持する必要があるあらゆる分野で利用できます。

## クイックスタート

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

利用可能なドメイン：`game-art`、`character-design`、`creature-design`、`architecture`、`vehicle-mech`、または`generic`。

## コマンドラインインターフェース (CLI)

```bash
sdlab init <name> [--domain <domain>]     # Scaffold a new project
sdlab project doctor [--project <name>]   # Validate project config

sdlab generate <pack> [--project <name>]  # Generate candidates via ComfyUI
sdlab generate:identity <packet>          # Named-subject identity images
sdlab generate:controlnet                 # ControlNet-guided generation
sdlab generate:ipadapter                  # IP-Adapter reference-guided

sdlab curate <id> <status> <explanation>  # Record review judgment
sdlab compare <a> <b> <winner> <reason>   # Pairwise A-vs-B comparison
sdlab bind [--project <name>]             # Bind records to constitution rules
sdlab painterly [--project <name>]        # Post-processing style pass

sdlab snapshot create [--profile <name>]  # Create frozen dataset snapshot
sdlab snapshot list                       # List all snapshots
sdlab snapshot diff <a> <b>               # Compare two snapshots
sdlab eligibility audit                   # Audit record training eligibility
sdlab split build [--snapshot <id>]       # Build train/val/test split
sdlab split audit <id>                    # Audit split for leakage + balance
sdlab card generate                       # Generate dataset card (md + JSON)
sdlab export build [--snapshot <id>]      # Build versioned export package
sdlab eval-pack build                     # Build canon-aware eval pack
```

すべてのコマンドは、`--project <名前>`（デフォルト：`star-freight`）を受け入れます。

## プロジェクトモデル

各プロジェクトは、`projects/`ディレクトリ内の自己完結型のディレクトリであり、独自の規定、設定、およびデータが含まれています。

```
projects/
  my-project/
    project.json            Project identity + generation defaults
    constitution.json       Rules array with rationale templates
    lanes.json              Subject lanes with detection patterns
    rubric.json             Scoring dimensions + thresholds
    terminology.json        Group vocabulary + detection order
    canon/                  Style constitution (markdown)
    records/                Per-asset JSON (provenance + judgment + canon)
    inputs/prompts/         Prompt packs (JSON)
    outputs/                Generated images (gitignored)
    comparisons/            A-vs-B preference judgments
    snapshots/              Frozen dataset snapshots
    splits/                 Train/val/test partitions
    exports/                Versioned export packages
    eval-packs/             Canon-aware eval instruments
```

## パイプライン

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **規定の定義 (Define canon)**：スタイル規定とレビュー基準を記述します。
2. **生成 (Generate)**：ComfyUIが、完全な生成履歴を持つ候補データを生成します。
3. **選別 (Curate)**：各評価項目のスコアと、失敗モードに基づいて、承認または拒否を行います。
4. **関連付け (Bind)**：各データと、規定への適合性（適合/不適合/部分適合）を関連付けます。
5. **スナップショット (Snapshot)**：選択されたデータレコードを、不変で、フィンガープリントが付与された状態で凍結します。
6. **分割 (Split)**：対象の分離と、表現のバランスを考慮して、トレーニングデータ/検証データ/テストデータに分割します。
7. **エクスポート (Export)**：マニフェスト、メタデータ、画像、およびチェックサムを含む、自己完結型のパッケージを構築します。
8. **評価 (Eval)**：モデル検証のための、規定に準拠したテストツールを生成します。

下流のフォーマット変換（TRL、LLaVA、Parquetなど）は、[`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)によって処理されます。`sdlab`がデータセットの真実性を管理し、`repo-dataset`がそれを特殊なフォーマットに変換します。

## ドメインテンプレート

各ドメインテンプレートには、表現の定義、規定、評価基準、および、その制作コンテキストに合わせた用語構造が含まれています。

| ドメイン | 表現 | 主要な考慮事項 |
|--------|-------|-------------|
| **game-art** | キャラクター、環境、小道具、UI、船、内装、装備 | ゲームプレイ時のシルエット、派閥の区別、摩耗/経年劣化 |
| **character-design** | ポートレート、全身像、アングル図、表情シート、アクションポーズ | プロポーションの正確性、衣装の論理性、キャラクターの表現、ジェスチャーの明瞭さ |
| **creature-design** | コンセプト、正投影図、詳細図、アクション、スケール参照、生息地 | 解剖学的な妥当性、進化論的な論理性、シルエットの区別 |
| **architecture** | 外観、内装、街並み、構造の詳細、廃墟、風景 | 構造的な妥当性、素材の一貫性、遠近感、時代への適合性 |
| **vehicle-mech** | 外観、コックピット、コンポーネント、設計図、シルエット図、損傷バリエーション | 機械的なロジック、機能的なデザイン言語、アクセスポイント、損害状況の説明 |

## データセットの生成

データセット全体の構成：スナップショット、分割、エクスポート、評価。

```
snapshot  -->  split  -->  export  -->  eval-pack
   |            |            |             |
  frozen     subject      package       canon-aware
  selection  isolation    (manifest,    test instruments
             + lane       metadata,     (4 task types)
             balance      images,
                          checksums,
                          card)
```

**スナップショット**は、選択されたレコードを決定的に固定します。すべてのデータは、その理由が追跡可能です。設定のフィンガープリントにより、再現性が確保されます。

**分割**は、レコードをトレーニング用、検証用、テスト用のデータセットに割り当てます。この際、被験者の同一性が保たれ（同じ被験者のデータが複数の分割に属さない）、各分割におけるデータのバランスが調整されます。シード値が設定された疑似乱数生成器を使用することで、同じシード値を使用した場合、常に同じ結果が得られます。

**エクスポートパッケージ**は、すべてが完結したパッケージです。内容：マニフェスト、metadata.jsonl、画像（シンボリックリンクまたはコピー）、分割データ、データセットの説明（Markdown形式とJSON形式）、およびBSD形式のチェックサム。データセットを最初から再構築するために必要なものがすべて含まれています。

**評価パッケージ**は、基準に準拠したテストツールであり、4つのタスクタイプ（レーンカバレッジ、禁止ドリフト、アンカー/ゴールド、被験者の一貫性）が含まれています。これにより、データセットの構成が、単にファイルをダンプするだけでなく、将来のモデル評価に役立つことを証明します。

`repo-dataset` ([https://github.com/mcp-tool-shop-org/repo-dataset](https://github.com/mcp-tool-shop-org/repo-dataset)) を使用して、下流の形式にエクスポートします（TRL、LLaVA、Qwen2-VL、JSONL、Parquetなど）。`repo-dataset` が形式の変換を処理し、`sdlab` がデータセットの正確性を保証します。

## Star Freightの例

完全な動作例については、リポジトリをクローンしてください。1,182件のレコード、28種類のプロンプト、5つの派閥、7つのレーン、24の憲法ルール、および、ハードなSF RPGから抽出された892件の承認済みアセットが含まれています。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab

# Validate the project
sdlab project doctor --project star-freight

# Run the full dataset spine
sdlab snapshot create --project star-freight    # 839 eligible records
sdlab split build --project star-freight        # ~80/10/10, zero leakage
sdlab export build --project star-freight       # package with checksums
sdlab eval-pack build --project star-freight    # 78 eval records
```

## v1.xからの移行

v2.0では、`games/`が`projects/`に、`--game`が`--project`に変更されました。

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## セキュリティモデル

**ローカル環境のみ。** `localhost:8188`で動作するComfyUIと通信します。テレメトリー、分析、外部へのリクエストは一切ありません。画像は、あなたのGPUとファイルシステムにのみ保存されます。

## 必要なもの

- `localhost:8188`で動作する[ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo チェックポイント + ClassipeintXL LoRA
- Node.js 20以上
- トレーニング用エクスポートのための[`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)

## ライセンス

MIT

---

開発：<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
