<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab"><img src="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

自分のビジュアルルールを記述します。アートを生成します。すべての画像をそれらのルールに対して評価します。結果をバージョン管理された、監査可能なトレーニングデータとして出力し、次に、トレーニング済みのモデルを実際の制作ワークフローで活用し、最高の出力をコーパスに再投入します。

スタイルデータセットラボは、アートスタイルに関する記述と、実際にトレーニングに使用するデータセットを結びつけ、その後、制作プロセス全体を通してそのループを閉じます。プロジェクトにとって重要な要素（シルエットルール、パレットの制約、マテリアルの表現など）を定義します。パイプラインは候補を生成し、それらをルールに基づいて評価し、承認されたものを再現可能なデータセットにパッケージ化します。各レコードには、なぜそれが含まれたのかが説明されています。

次に、制作ワークベンチが引き継ぎます。プロジェクトの要件から生成指示をまとめ、ComfyUIで実行し、出力を評価し、表現シートや環境ボードを一括作成し、最良の結果を選択して、新しい候補として再取り込みます。このループは、生成、選択、レビュー、強化という流れで閉じられます。

## パイプライン

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Bind approved work to constitution rules
# (`sdlab bind` is a shorter alias for `canon-bind`)
sdlab canon-bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package
sdlab training-manifest create --profile character-style-lora
sdlab training-package build

# Compile a production brief and run it
sdlab brief compile --workflow character-portrait-set --subject kael_maren
sdlab run generate --brief brief_2026-04-16_001

# Critique, refine, batch-produce
sdlab critique --run run_2026-04-16_001
sdlab refine --run run_2026-04-16_001 --pick 001.png
sdlab batch generate --mode expression-sheet --subject kael_maren

# Select the best outputs and bring them back
sdlab select --run run_2026-04-16_001 --approve 001.png,003.png
sdlab reingest selected --selection selection_2026-04-16_001
```

最後のコマンドがポイントです。選択された出力は、他のすべてのものと同様に、同じレビュープロセスを経て再利用されます。コーパスが増加し、ルールは維持されます。

## カノンオーサリング

データセットパイプラインを実行する前に、`sdlab canon *`名前空間は、プロジェクトのカノンエンティティストアを、実際のトレーニングと制作で使用される3つのプロジェクションに変換し、変更してはならないエントリをロックします。

```bash
# Build three projections from the canon entity store:
#   dataset.jsonl  → training adapters
#   prompts/*.j2   → ComfyUI workflow invocation
#   context/*.md   → Role OS narrative dispatch
sdlab canon build --project my-project

# Freeze an entry so regeneration can't silently change it
sdlab canon freeze kael_maren --project my-project --reason "prologue portrait locked"

# Report drift on frozen entries since the last clean build
sdlab canon drift --project my-project
```

`canon build`はコンテンツアドレス指定であり、その出力は`canon_sha`でキー付けされ、キャッシュされます。そのため、変更されていないカノンは瞬時に再構築されます。`canon freeze`は、各フリーズを特定のビルドに対して記録し、`freeze-events.jsonl`監査トレイルに追加します。`frozen`エントリは完全に再生成を拒否し、`soft-advisory`エントリはデフォルトで拒否しますが（`--i-know`オプションで回避できます）。`canon drift`は、監視対象のすべてのエントリのハッシュを再計算し、最後のクリーンビルド以降に変更されたものをフラグします。

完全なワークフローについては、ハンドブックをご覧ください。[カノンビルド](handbook/canon-build/)、[カノンフリーズ](handbook/canon-freeze/)、および[Two-LoRAスタッキング](handbook/two-lora-stacking/)。

## 生成されるもの

7つのデータセット成果物と完全な制作ワークベンチ。各成果物は、その先行するものにリンクされており、トレーニングレコードを承認したルールまで追跡できます。

| 成果物 | 概要 |
|----------|-----------|
| **Snapshot** | 構成のフィンガープリントを持つフリーズされたレコード選択。すべての包含には明確な理由があります。 |
| **Split** | 被験者グループが境界を越えない、トレーニング/検証/テストの分割。 |
| **Export package** | 自己完結型のデータセット：マニフェスト、メタデータ、画像、分割、データセットカード、チェックサム。 |
| **Eval pack** | カノンを意識したテストタスク：レーンカバレッジ、禁止されたドリフト、アンカー/ゴールド、被験者の連続性。 |
| **Training package** | アダプター（`diffusers-lora`、`generic-image-caption`）を介したトレーナー対応のレイアウト。同じ情報でありながら、異なる形式です。 |
| **Eval scorecard** | 生成された出力を評価パックに対してスコアリングし、タスクごとの合格/不合格を判定します。 |
| **Implementation pack** | プロンプト例、既知の失敗、連続性テスト、および再取り込みガイダンス。 |

制作ワークベンチは以下を追加します：

| 表面 | 機能 |
|---------|-------------|
| **Compiled brief** | ワークフロープロファイルとプロジェクトの要件からの決定的な生成指示。 |
| **Run** | フリーズされた実行成果物：ブリーフィング+シード+ComfyUI出力+マニフェスト。 |
| **Critique** | カノンに対する実行出力の構造化された多次元評価。 |
| **Batch** | 調整されたマルチスロット制作（表現シート、環境ボード、シルエットパック）。 |
| **Selection** | クリエイティブな意思決定成果物：どの出力が選択され、その理由は何で、どこから来たのか。 |
| **Re-ingest** | 選択された出力は、完全な生成の来歴とともに、候補レコードとして返されます。 |

## このシステムが存在する理由

トレーニングデータは、あらゆるビジュアルAIパイプラインにおいて最も効果的な成果物です。しかし、ほとんどのトレーニングデータは、履歴も、判断の記録も、従うべきスタイルルールとの関連性もない、単なる画像のフォルダーにすぎません。

スタイルデータセットラボは、この関連性を明確にします。あなたの憲法がルールを定義します。あなたのルーブリックがスコアリングの次元を定義します。あなたのキュレーションが判断を記録します。あなたのカノンバインディングがその関連性を証明します。そして、あなたのデータセットは、それらすべてを構造化され、クエリ可能で、再現可能な情報として前進させます。

実用的な結果：LoRAがドリフトした場合、なぜそうなるのかを尋ねることができます。次のトレーニングラウンドにより良いデータが必要な場合、どのレコードがほぼ合格であり、どの単一のルールに失敗したかを正確に知ることができます。新しいチームメンバーがプロジェクトのビジュアル言語について質問した場合、答えはFigmaボードではなく、1,182件の評価された例を含む検索可能な憲法です。

## 5つのドメイン、実際のルール

プレースホルダーテンプレートではありません。各ドメインには、実運用レベルのカノン憲法ルール、レーン定義、スコアリングルーブリック、およびグループ語彙が付属しています。

| ドメイン | レーン | 評価対象となるもの |
|--------|-------|-----------------|
| **game-art** | キャラクター、環境、小道具、UI、船、インテリア、装備 | ゲームプレイ規模でのシルエット、派閥の識別、摩耗と経年変化 |
| **character-design** | ポートレート、全身像、ターンアラウンド、表現シート、アクションポーズ | プロポーション、衣装の論理、個性、ジェスチャーの明確さ |
| **creature-design** | コンセプト、オルソグラフィック、詳細な研究、アクション、スケール参照、生息地 | 解剖学、進化の論理、シルエットの区別 |
| **architecture** | 外観、内装、街並み、構造的な詳細、廃墟、風景 | 構造、マテリアルの整合性、視点、時代の整合性 |
| **vehicle-mech** | 外観、コックピット、コンポーネント、図面、シルエットシート、損傷バリアント | 機械的な論理、デザイン言語、アクセスポイント、損傷の物語 |

## プロジェクトの構造

各プロジェクトは独立しています。5つのJSON設定ファイルでルールを定義します。それ以外はすべてデータです。

```
projects/my-project/
  project.json           Identity + generation defaults
  constitution.json      Rules with rationale templates
  lanes.json             Subject lanes with detection patterns
  rubric.json            Scoring dimensions + thresholds
  terminology.json       Group vocabulary + detection order
  records/               Per-asset JSON (provenance + judgment + canon)
  snapshots/             Frozen dataset snapshots
  splits/                Train/val/test partitions
  exports/               Versioned export packages
  training/              Profiles, manifests, packages, eval runs, implementations
  workflows/             Workflow profiles + batch mode definitions
  briefs/                Compiled generation briefs
  runs/                  Execution artifacts (brief + outputs + manifest)
  batches/               Coordinated multi-slot productions
  selections/            Chosen outputs with reasons and provenance
  inbox/generated/       Re-ingested images awaiting review
```

## 信頼性のためのプロパティ

これらは理想的なものではありません。強制的に適用されます。

- **スナップショットは不変です。** 設定のフィンガープリント（SHA-256）により、変更がないことが証明されます。
- **分割によってデータの漏洩を防ぎます。** サブジェクトファミリー（ID、系統、またはIDサフィックスによる）は、決してパーティション境界を越えません。
- **マニフェストは固定された契約です。** エクスポートハッシュ + 設定フィンガープリント。変更がある場合は、新しいものを生成します。
- **アダプターは真実を変更できません。** レイアウトは異なりますが、レコードは同じです。追加、削除、再分類はありません。
- **生成された出力は、レビューを通じて再度利用されます。** バイパスはありません。他のものと同様に、キュレーションとバインドを行います。

## スター・フレイト

このリポジトリには、完全な動作例が含まれています：1,182件のレコード、5つの派閥、7つのルート、24の憲法ルール、892個の承認済みアセット、2つのトレーニングプロファイル。洗練されたSF RPGのビジュアルカノンで、完全にキュレーションされています。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## 下流形式

`sdlab`がデータセットを所有します。フォーマット変換は[`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)によって処理されます：TRL、LLaVA、Qwen2-VL、JSONL、Parquetなど。`repo-dataset`はレンダリングを行い、データの選択は行いません。

## インストール

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Node.js 20+と、ローカルホストの8188ポートで動作する[ComfyUI](https://github.com/comfyanonymous/ComfyUI)が必要です（生成用）。

### ComfyUIなしで試す

バンドルされたスター・フレイトプロジェクトを使用して、完全な非生成機能（検査、キュレーション、スナップショット、分割、エクスポート）を、ComfyUIのインストールやSDXLウェイトのダウンロードなしで探索できます。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor`は、すべてのプロジェクト設定（憲法、ルート、ルーブリック、用語）を検証し、GPUに触れることなく有効性を報告します。生成された状態を変更するコマンドはすべて、最初に効果をプレビューするために`--dry-run`を受け入れます。

`--project`を忘れた場合、CLIは`projects/`の下で最初に見つかったプロジェクトにフォールバックし、警告を表示します。警告を抑制するには、`--project`を明示的に指定してください。

### 中断された実行の再開

長時間の生成実行は、完了した作業をやり直さずに再開できます。

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

両方のコマンドが機能するのは、各スロットが完了時にマニフェストエントリをアトミックに書き込むためです。実行中にクラッシュが発生しても、部分的な状態が破損することはありません。

## トラブルシューティング

一般的なエラーとその修正：

**`sdlab generate` / `sdlab run generate` / `sdlab batch generate`のいずれかで`ECONNREFUSED 127.0.0.1:8188`が発生した場合**
ComfyUIが実行されていません。ComfyUIを起動します（`python main.py --listen 127.0.0.1 --port 8188`）そして、`curl http://127.0.0.1:8188/system_stats`で確認してください。別のホスト/ポートを指定するには、`COMFY_URL=http://host:port`を設定します。

**`missing checkpoint` / `LoRA weight not found`**
ワークフロープロファイルで、ComfyUIの`models/checkpoints/`または`models/loras/`フォルダにないモデルファイルを指定しています。`projects/<project>/workflows/profiles/<profile>.json`を開き、`checkpoint`または`lora`フィールドを見つけて、参照されているウェイトをダウンロードするか、すでに持っているものと置き換えます。`sdlab project doctor --project <project>`を再実行して、修正を確認します。

**`sdlab project doctor`のエラー**
Doctorは構造化されたエラーコードを返します。一般的なもの：
- `E_PROJECT_NOT_FOUND` — プロジェクトディレクトリが`projects/`の下に存在しません。スペルを確認してください。
- `E_CONFIG_INVALID` — 5つのJSON設定ファイルのいずれかが、スキーマ検証に失敗しました。`hint`フィールドには、問題のあるファイルとフィールドの名前が表示されます。
- `E_RECORD_DRIFT` — レコードの設定フィンガープリントが、そのソースと一致しなくなりました。ヒントに従って、再キュレーションまたは再バインドしてください。

**`No --project specified, falling back to <name>`**
軽度の警告です。`--project <name>`を明示的に指定して、適切なプロジェクトを選択し、警告を抑制します。

**Painterly / VRAMのメモリ不足の問題**
`docs/internal/HANDOFF.md`を参照して、Painterlyのデノイズ調整に関する注意事項を確認してください。要するに：デノイズ強度を下げたり、バッチサイズを減らしたり、ワークフロープロファイルでより小さいチェックポイントに切り替えたりします。

**バグの報告**
https://github.com/mcp-tool-shop-org/style-dataset-lab/issues に、sdlabバージョン（`sdlab --version`）、Nodeバージョン（`node -v`）、完全なコマンド、および構造化されたエラー出力を添えて問題を報告してください。バグ報告テンプレートには、フィールドが事前に設定されています。

## セキュリティ

ローカルでのみ動作します。テレメトリ、分析、外部リクエストはありません。画像はGPUとファイルシステムにのみ保存されます。

## ライセンス

MIT

---

MCP Tool Shopによって作成されました。
