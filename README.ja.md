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

自分のビジュアルルールを記述します。アートを生成します。すべての画像をそれらのルールに対して評価します。結果をバージョン管理された、監査可能なトレーニングデータとして出力し、次に、トレーニングされたモデルを実際の運用ワークフローで使用し、最高の出力を自分のデータセットにフィードバックします。

スタイルデータセットラボは、アートスタイルについて記述した内容と、実際にトレーニングに使用するデータセットを結びつけ、その後、運用全体を通してそのループを閉じます。構成を定義します。シルエットルール、パレットの制約、マテリアルの言語など、プロジェクトにとって重要な要素を定義します。パイプラインは候補を生成し、それらをルールに対して評価し、承認されたものを再現可能なデータセットにパッケージ化します。各レコードには、なぜそれが含まれたのかが説明されています。

次に、運用ワークベンチが引き継ぎます。プロジェクトの要件から生成ブリーフをコンパイルし、それをComfyUIに適用し、出力を評価し、表現シートと環境ボードをバッチ処理で作成し、最良の結果を選択し、それらを新しい候補として再取り込みます。ループが閉じます。生成、選択、レビュー、強化。

## パイプライン

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab sheet outputs/candidates --project my-project   # HTML contact sheet to triage
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Already have images? Bring them in without generating anything
sdlab ingest ~/renders/wave1 --project my-project

# Measure what the pixels actually are — palette and texture, as numbers
sdlab measure outputs/candidates --project my-project

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

最後のコマンドがポイントです。選択された出力は、他のすべてのものと同様に、同じレビュープロセスを通過します。データセットは拡張され、ルールは維持されます。

## アセットの経路 — トレーニングデータとしての3Dエクスポート

`sdlab ingest`は、生の画像を信頼して受け入れます。`sdlab asset ingest`は、**契約**を受け入れます。

3Dアセットが受け入れゲートを通過した場合、N個の角度から再レンダリングすると、ビューの一貫性が*構造的に*保証されたターンアラウンドが得られます。これは、パービュー拡散では保証できない特性です。アセットの経路は、これらのエクスポートを、プロベナンス（来歴）情報を含むトレーニングデータとして受け入れます。

```bash
# Validate an export's manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it: records, candidates, masks, channels, receipt
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

エクスポートディレクトリには、そのチャンネル、パレットバンド、ゲートの閾値、受け入れの判断、スタイル登録、レンダリングがどのように作成されたか、およびその生成のプロベナンスを宣言する`asset-source.json`マニフェスト（スキーマ**1.3.0**）が含まれています。sdlabは、すべての宣言を実際のバイトに対して検証し、違反があった場合は、すべてを拒否します。不良のマニフェストは登録されません。

**接合部：** sdlabはメカニズムを提供し、アセットはセマンティクスを提供します。sdlabは、決してレイキャストを行ったり、レンダリングを行ったり、チャンネルが「プロベナンス」であることは特別なことであるとは学習しません。sdlabは、検証、測定、登録、パッケージ化を行います。数値が*意味する*ものは、アセットに保持されます。

契約で強制されること：

| 段階 | 検証されること |
|---|---|
| **schema** | 形状、ID、適切に形成されたパレットバンド、および文字通り`"accepted"`である受け入れの判断 |
| **containment** | 参照されているすべてのパスは、エクスポートディレクトリ*内*に解決され（信頼できない入力です）、存在します。 |
| **encoding** | PNGのIHDRは、宣言されたエンコーディングと一致します。NPYヘッダーは、宣言されたdtypeと形状と一致します。「見た目は正しい」が、そのバイトと矛盾するマニフェストは、この経路が存在する理由である失敗ケースです。 |
| **categorical** | インデックス化されたPNGは、PLTE⊆宣言されたパレットであることを検証します。`nearest`でフィルタリングされたチャンネルは、*包括的な*ピクセルデコードを受けます。カテゴリカルなNPYは、包括的な値スキャンを受けます。 |
| **gates** | パレットゲートは、マニフェスト自体のバンドと閾値を使用して、レンダリングごとに実行されます。失敗したレンダリングは、明確に拒否され、レポートされます。静かに受け入れられることはありません。 |

レコードは**キュレーションされていない**（`judgment: null`）状態で、`provenance.source: "asset"`とともに保存され、
受け入れブロックを逐語的に、ファイルごとのハッシュ、カメラと派生した向き、ゲートの測定値、宣言されたスタイル登録、およびイメージごとの生成フレームとシードとともに保存されます。その後、他のすべてのレコードと同様に、同じキュレーション処理が行われます。

取り込みは、マニフェストが*宣言しなかった*ものもレポートします。不明なスタイル登録、欠落している`identity.subject_name`、欠落している生成プロベナンスなどを**通知**として、失敗ではなくレポートします。これらは、レシートに記録され、CLIに表示されます。誰にも伝えられないギャップは、誰にも埋められないギャップです。また、マニフェストは、そのレンダリングが独自のシードを持たない決定論的な派生であると*宣言できるため、この経路は、正しいエクスポートに関するギャップをレポートすることはありません。

完全な契約、検証ラダー、およびすべてのフィールドの背後にある理由：[docs/asset-lane-design.md](docs/asset-lane-design.md)。

## カノンオーサリング

データセットパイプラインが実行される前に、`sdlab canon *`名前空間は、プロジェクトのカノンエンティティストアを、トレーニングと運用が実際に使用する3つの投影に変換し、変更してはならないエントリをロックします。

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

ローカルモデルもカノンをドラフトできますが、最終的な決定を下すことはできません。`sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>`は、ループバック専用の、OpenAI互換のサーバーにカノンエントリとプロンプトを要求し、それらを`status: "draft"`、`judgment: null`、およびドラフトモデルとともにすべての出力に書き込みます。ドラフトは、人が承認するまで凍結できません。凍結ゲートは、人間の承認、理由、および承認された正確なドラフトのハッシュがない限り、モデルによってドラフトされたエントリを拒否します。

`canon build`はコンテンツアドレス指定可能です。その出力は、`canon_sha`でキーが付けられ、キャッシュされるため、変更されていないカノンは瞬時に再構築されます。`canon freeze`は、特定のビルドに対して各凍結を検証し、`freeze-events.jsonl`監査トレイルに追加します。`frozen`エントリは、再生成を完全に拒否します。`soft-advisory`エントリは、デフォルトで拒否します（`--i-know`でバイパスできます）。`canon drift`は、監視されているすべてのエントリのハッシュを再計算し、最後のクリーンビルド以降に移動したものをフラグします。

ハンドブックの完全なワークフロー：[カノンのビルド](handbook/canon-build/)、[カノンの凍結](handbook/canon-freeze/)、および[Two-LoRAスタッキング](handbook/two-lora-stacking/)。

## 生成されるもの

7つのデータセットアーティファクトと、完全な運用ワークベンチ。各アーティファクトは、その先行アーティファクトにリンクされているため、トレーニングレコードを承認したルールまで追跡できます。

| アーティファクト | 内容 |
|----------|-----------|
| **Snapshot** | 構成フィンガープリントを持つ、凍結されたレコード選択。すべての包含には、明示的な理由があります。 |
| **Split** | 被験者ファミリーが境界を越えない、トレーニング/検証/テストの分割。 |
| **Export package** | 自己完結型のデータセット：マニフェスト、メタデータ、画像、分割、データセットカード、チェックサム。 |
| **Eval pack** | カノンを考慮したテストタスク：レーンカバレッジ、許容されないドリフト、アンカー/ゴールド、被写体の連続性。 |
| **Training package** | アダプター（`diffusers-lora`、`generic-image-caption`）を介した、トレーニングに最適なレイアウト。同じ真実、異なる形式。 |
| **Eval scorecard** | 評価パックに対して生成された出力のスコアリングに基づいた、タスクごとの合格/不合格判定。 |
| **Implementation pack** | プロンプトの例、既知の失敗例、連続性テスト、および再取り込みのガイダンス。 |

本番環境のワークベンチに追加：

| 表面 | その機能 |
|---------|-------------|
| **Compiled brief** | ワークフロープロファイルとプロジェクトの真実から生成される、決定的な生成指示。 |
| **Run** | フリーズされた実行アーティファクト：概要 + シード + ComfyUI出力 + マニフェスト。 |
| **Critique** | 実行出力とカノンの間の、構造化された多次元評価。 |
| **Batch** | 調整されたマルチスロットによる本番環境（表現シート、環境ボード、シルエットパック）。 |
| **Selection** | クリエイティブな意思決定アーティファクト：どの出力が選択されたか、その理由、およびその出力の出所。 |
| **Re-ingest** | 選択された出力は、完全な生成の来歴とともに、候補レコードとして返されます。 |

## この機能が存在する理由

トレーニングデータは、あらゆるビジュアルAIパイプラインにおいて最も重要なアーティファクトです。しかし、ほとんどのトレーニングデータは、履歴、判断の記録、および本来従うべきスタイルルールとの関連性がない、単なる画像のフォルダーです。

スタイルデータセットラボは、この関連性を明確にします。あなたの憲法はルールを定義します。あなたのルーブリックは、スコアリングの次元を定義します。あなたのキュレーションは、判断を記録します。あなたのカノンバインディングは、その関連性を証明します。そして、あなたのデータセットは、それらすべてを構造化され、クエリ可能で、再現可能な真実として引き継ぎます。

実用的な結果：あなたのLoRAがドリフトした場合、その理由を尋ねることができます。次のトレーニングラウンドでより良いデータが必要な場合、どのレコードがほぼ失敗しており、どの単一のルールに違反したかを正確に知ることができます。新しいチームメンバーが、プロジェクトのビジュアル言語について尋ねた場合、その答えはFigmaボードではなく、1,182件の評価された例を含む、検索可能な憲法です。

## 本番環境で実証済み

これはデモパイプラインではありません。2つの実際のスタイルLoRAが、最初から最後までこれを使用して出荷されました。同じカノン→キュレーション→トレーニング→出荷のループを、キュレーションスペクトルの反対の端で実行しました。

- **[Tallow Fen](handbook/case-study-tallow-fen/)**（クリーチャーデザイン）—最初から作成されたベストiaryカノン、293件のキュレーションされたレコードのうち、約34％の承認率（169件は却下—ゲートは厳しく却下します）。`tallow_fen_style_v3.safetensors`を1.5で`qwen-image`に出荷。
- **[Rustline](handbook/case-study-rustline/)**（コンセプトデザイン）—密度が高く、事前に形成されたカノン、180件のレコードのうち、約96％の承認率。`rustline_v3ckpt_1500.safetensors`を1.0で`qwen-image`に出荷し、別のプロジェクトで再利用。

同じパイプライン、2つの本番環境プロファイル：キュレーションゲートは本物です（オープンなテーマについては厳しく却下します）。そして、厳格なカノンは高い受容率をもたらします。

## 5つのドメイン、実際のルール

プレースホルダーのテンプレートではありません。各ドメインには、本番環境で使用できる憲法ルール、レーン定義、スコアリングルーブリック、およびグループ語彙が付属しています。

| ドメイン | レーン | 評価対象 |
|--------|-------|-----------------|
| **game-art** | キャラクター、環境、小道具、UI、船、インテリア、装備 | ゲームプレイ規模でのシルエット、派閥の認識、摩耗と経年変化 |
| **character-design** | ポートレート、全身、ターンアラウンド、表現シート、アクションポーズ | プロポーション、衣装の論理、個性、ジェスチャーの明確さ |
| **creature-design** | コンセプト、オルソグラフィック、詳細な研究、アクション、スケール参照、生息地 | 解剖学、進化の論理、シルエットの区別 |
| **architecture** | 外観、内観、街並み、構造的な詳細、廃墟、風景 | 構造、材質の一貫性、視点、時代の一貫性 |
| **vehicle-mech** | 外観、コックピット、コンポーネント、図面、シルエットシート、損傷バリアント | 機械的な論理、デザイン言語、アクセスポイント、損傷の物語 |

## プロジェクト構造

各プロジェクトは独立しています。5つのJSON設定ファイルがルールを定義します。それ以外はすべてデータです。

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

## 信頼できるプロパティ

これらは理想的なものではありません。これらは強制されます。

- **スナップショットは不変です。** 設定フィンガープリント（SHA-256）は、変更がないことを証明します。IDはアトミックに割り当てられるため、2つの同時実行プロセスが1つのディレクトリに混ざることはありません。
- **分割は情報の漏洩を防ぎ、そのことを確認するチェックは独立しています。** サブジェクトファミリー（ID、系統、または正規化されたIDの接頭辞によって定義）は、決してパーティションの境界を越えません。2回目のチェックでは、分割自体で使用されたマップを再読み込みするのではなく、最初からサブジェクトIDを再導出します。データセットカードは、両方のチェックが実行され、合格した場合にのみ、「漏洩：なし（検証済み）」と主張します。2回目のチェックよりも前に作成された分割は、そのことを正確に示します。
- **マニフェストは固定された契約です。** エクスポートハッシュと設定フィンガープリントを組み合わせ、`validate`は、`checksums.txt`にリストされているすべてのファイルを再ハッシュします。したがって、完成したエクスポート内の画像を置き換えることは検出され、そのチェックが存在する前に作成されたマニフェストも同様です。
- **実行は、正確なグラフを固定します。** 各世代は、`comfy_workflow_sha` + モデル/LoRAコンテンツハッシュ + シードポリシーを記録するため、ウェーブはバイト単位で完全に再現可能です。JSとPythonのランナーは、両方を起動するテストによって、バイト単位で同一のハッシュになるように制限されます。モデルのハッシュ化はオプション（`--hash-models`）であり、偽造されることはありません。解決できないファイルは、注記とともに`sha256: null`を記録します。
- **モデルは、自身の出力を検証しません。** 評価は、`judged_by_model`と`generator_model`を記録します。これらが同じモデルである場合、警告が表示されます。
- **評価は、誰が作成したかを伝えます。** `eligibility audit`は、人が作成した評価と、一括スクリプトによって作成された評価を区別します。したがって、画像ではなくカテゴリを説明する根拠は、キュレーションとして合格しません。
- **測定は、評価ではありません。** `sdlab measure`は、レコードに数値を関連付けます。評価、適合、または承認を設定することはありません。また、画像に対して測定が定義されていない場合、妥当な数値ではなく、`null`を記録します。
- **リリースは、すべての画像の出所を証明できます。** `sdlab verify --project <name>`は、各レコードに対してオフラインでチェーンをたどります。レコードの所有者とライセンス、ハッシュによってバインドされた正典エントリ、すべてのモデルとLoRAのライセンス（SPDX ID、ライセンスURL、読み取り日時、ファイルハッシュ）、および実行マニフェスト内のワークフローハッシュです。リンクが欠落している場合、チェックは合格ではなく、失敗します。
- **アダプターは、真実を変更できません。** レイアウトは異なりますが、レコードは同じです。追加、削除、再分類はありません。
- **生成された出力は、レビューを通じて再入力されます。** バイパスはありません。他のものと同様に、キュレーションとバインドを行います。外部で生成された画像は、`sdlab ingest`を介して、キュレーションなしで同じ方法で入力されます。
- **失敗は可視化されます。** レコードが欠落している、配置できない画像がある、または作成できないキャプションがある場合、エクスポートまたはトレーニングパッケージは、静かに縮小されるのではなく、停止します。

## スター・フレイト

このリポジトリには、完全な動作例が含まれています。1,182件のレコード、5つの派閥、7つのレーン、24の憲法ルール、892件の承認されたアセット、2つのトレーニングプロファイル。完全にキュレーションされた、荒々しいSF RPGのビジュアルカノン。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## 下流の形式

`sdlab`がデータセットを所有します。形式変換は、[`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)によって処理されます。TRL、LLaVA、Qwen2-VL、JSONL、Parquetなど。`repo-dataset`はレンダリングします。組み込みを決定することはありません。

## インストール

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Node.js 20+と、ローカルホストの8188で実行される[ComfyUI](https://github.com/comfyanonymous/ComfyUI)が必要です。

### ComfyUIなしで試す

バンドルされたスター・フレイトプロジェクトを使用して、生成以外のすべての機能（検査、キュレーション、スナップショット、分割、エクスポート）を、ComfyUIをインストールしたり、SDXLの重みをダウンロードしたりせずに探索できます。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor`は、すべてのプロジェクト構成（憲法、レーン、ルーブリック、用語）を検証し、GPUに触れることなく、適格性を報告します。生成された状態を変更するコマンドは、最初に効果をプレビューするために、`--dry-run`を受け入れます。

`--project`を忘れた場合、CLIは、`projects/`の下にある最初に見つかったプロジェクトにフォールバックし、警告を表示します。警告を抑制するには、`--project`を明示的に渡します。

### 中断された実行を再開する

長い生成実行は、完了した作業をやり直さずに再開できます。

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

両方のコマンドは、各スロットが完了時にマニフェストエントリをアトミックに書き込むため機能します。実行中にクラッシュしても、部分的な状態が破損することはありません。

## トラブルシューティング

一般的な失敗モードと修正：

**`ECONNREFUSED 127.0.0.1:8188`が、任意の`sdlab generate` / `sdlab run generate` / `sdlab batch generate`で実行されていない**
ComfyUIが実行されていません。ComfyUI（`python main.py --listen 127.0.0.1 --port 8188`）を開始し、`curl http://127.0.0.1:8188/system_stats`で確認します。別のホスト/ポートを指定するには、`COMFY_URL=http://host:port`を設定します。

**`missing checkpoint` / `LoRA weight not found`**
ワークフロープロファイルで、ComfyUIの`models/checkpoints/`または`models/loras/`フォルダーにないモデルファイルを指定しています。`projects/<project>/workflows/profiles/<profile>.json`を開き、`checkpoint`または`lora`フィールドを見つけて、参照されている重みをダウンロードするか、すでに持っているものに置き換えます。`sdlab project doctor --project <project>`を再実行して、修正を確認します。

**`sdlab project doctor`エラー**
ドクターは、構造化されたエラーコードを返します。一般的なもの：
- `E_PROJECT_NOT_FOUND` — プロジェクトディレクトリが、`projects/`の下に存在しません。スペルを確認してください。
- `E_CONFIG_INVALID` — 5つのJSON構成ファイルのいずれかが、スキーマ検証に失敗しました。`hint`フィールドは、問題のあるファイルとフィールドの名前を示します。
- `E_RECORD_DRIFT` — レコードの構成フィンガープリントが、ソースと一致しなくなりました。ヒントに従って、再キュレーションまたは再バインドします。

**`No --project specified, falling back to <name>`**
ソフトな警告。正しいプロジェクトを明示的に選択し、警告を抑制するには、`--project <name>`を渡します。

**ペインタリー / VRAMのメモリ不足の問題**
`docs/internal/HANDOFF.md`を参照して、ペインタリーのデノイズ調整に関するメモを確認してください。要するに：デノイズ強度を下げ、バッチサイズを減らすか、ワークフロープロファイルでより小さいチェックポイントに切り替えます。

**バグの報告**
https://github.com/mcp-tool-shop-org/style-dataset-lab/issuesに、sdlabバージョン（`sdlab --version`）、Nodeバージョン（`node -v`）、完全なコマンド、および構造化されたエラー出力を記載して、問題を報告してください。バグ報告テンプレートは、フィールドを事前に設定します。

## セキュリティ

デフォルトではローカルです。テレメトリ、分析はなく、`sdlab` CLIから外部リクエストもありません。画像はGPUとファイルシステムに残り、`canon draft`はループバック以外のすべてのエンドポイントを拒否します。

唯一の例外は、オプトイン機能です。`scripts/colab/`には、お客様ご自身のGoogle Colabアカウントでレンダリングを実行したり、LoRAのトレーニングステップを実行したりするためのキットが含まれています。これらのキットは、指定されたファイルのみをアップロードし、お客様のColabアカウントの残高に基づいて設定された予算内で実行され、終了時にセッションを自動的に停止します。これらのキットは**実験段階**であり、まだ完全なテストは完了していません。

## ライセンス

マサチューセッツ工科大学

---

Built by <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
