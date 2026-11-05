<p align="center">
  <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
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

Escreva suas regras visuais. Gere arte. Avalie cada imagem com base nessas regras. Envie os resultados como dados de treinamento versionados e auditáveis — e, em seguida, coloque os modelos treinados em uso em fluxos de trabalho de produção reais e alimente os melhores resultados de volta ao seu corpus.

O Style Dataset Lab conecta o que você escreveu sobre seu estilo artístico ao conjunto de dados do qual você realmente treina, e, em seguida, fecha o ciclo até a produção. Você define uma constituição — regras de silhueta, restrições de paleta, linguagem de materiais, qualquer coisa que seja importante para o seu projeto. O pipeline gera candidatos, avalia-os com base nessas regras e empacota o trabalho aprovado em conjuntos de dados reproduzíveis, onde cada registro explica por que foi incluído.

Em seguida, o ambiente de trabalho de produção assume o controle: compile resumos de geração a partir da verdade do projeto, execute-os no ComfyUI, critique os resultados, produza em lote folhas de expressão e painéis de ambiente, selecione os melhores resultados e reimporte-os como novos candidatos. O ciclo se fecha: produzir, selecionar, revisar, aprimorar.

## O pipeline

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

Esse último comando é o ponto crucial. Os resultados selecionados retornam pelo mesmo processo de revisão que todos os outros. O corpus cresce e as regras permanecem válidas.

## O fluxo de ativos — exportações 3D como dados de treinamento

`sdlab ingest` aceita imagens básicas sem questionar. `sdlab asset ingest` exige um **contrato**.

Quando um ativo 3D passa pelo seu portão de aceitação, renderizá-lo novamente a partir de N ângulos fornece uma
visualização consistente *por construção* — uma propriedade que a difusão por visualização
não pode garantir. O fluxo de ativos aceita essas exportações como dados de treinamento com informações de procedência:

```bash
# Validate an export's manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it: records, candidates, masks, channels, receipt
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

O diretório de exportação contém um manifesto `asset-source.json` (esquema **1.3.0**) declarando
seus canais, faixas de paleta, limites do portão, veredicto de aceitação, registro de estilo, como
as renderizações foram criadas e sua procedência de geração. O sdlab comprova cada declaração
em relação aos bytes reais e rejeita toda a ingestão em caso de violação — nada é registrado
com um manifesto inválido.

**A junção:** o sdlab fornece o mecanismo, o ativo fornece a semântica. O sdlab nunca faz ray tracing,
nunca renderiza e nunca aprende que um canal chamado "procedência" é especial. Ele comprova,
mede, registra e empacota. O que os números *significam* permanece com o ativo.

O que o contrato exige:

| estágio | o que é comprovado |
|---|---|
| **schema** | forma, IDs, faixas de paleta bem formadas e um veredicto de aceitação que é literalmente `"accepted"` |
| **containment** | cada caminho referenciado resolve *dentro* do diretório de exportação (é uma entrada não confiável) e existe |
| **encoding** | o IHDR de um PNG corresponde à sua codificação declarada; um cabeçalho NPY corresponde ao seu dtype e forma declarados. Um manifesto que "parece correto", mas discorda de seus bytes, é a classe de falha que este fluxo existe para impedir |
| **categorical** | PNGs indexados comprovam que PLTE ⊆ paleta declarada; canais filtrados por `nearest` recebem uma decodificação de pixel *exaustiva*; NPYs categóricos recebem uma varredura de valor exaustiva |
| **gates** | o portão de paleta é executado por renderização, a partir das próprias faixas e limites do manifesto — uma renderização com falha é rejeitada de forma clara e relatada, nunca admitida silenciosamente |

Os registros são armazenados **sem curadoria** (`judgment: null`) com `provenance.source: "asset"`, contendo
o bloco de aceitação literalmente, hashes por arquivo, câmera e orientação derivada, as
medidas do portão, o registro de estilo declarado e, por imagem, o quadro de geração + semente. Em seguida,
eles passam pelo mesmo processo de curadoria que todos os outros registros.

A ingestão também relata o que um manifesto *não* declarou — um registro de estilo desconhecido, uma
falta de `identity.subject_name`, ausência de procedência de geração — como **avisos** em vez de
falhas. Eles são incluídos no recibo e impressos no CLI. Uma lacuna sobre a qual ninguém é informado é uma lacuna
que ninguém pode preencher; e, como um manifesto pode *declarar* que suas renderizações são derivações determinísticas sem uma semente própria, o fluxo nunca relata uma lacuna em uma exportação que está
correta.

Contrato completo, a escada de validação e o raciocínio por trás de cada campo:
[docs/asset-lane-design.md](docs/asset-lane-design.md).

## Criação de conteúdo canônico

Antes que o pipeline do conjunto de dados seja executado, o namespace `sdlab canon *` transforma o armazenamento de entidades canônicas do seu projeto nas três projeções que o treinamento e a produção realmente usam — e bloqueia as entradas que não devem mudar.

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

Um modelo local também pode criar conteúdo canônico, mas nunca decide sobre ele. `sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>` solicita a um servidor compatível com OpenAI e com loopback apenas uma entrada canônica e prompts, e os grava com `status: "draft"`, `judgment: null` e o modelo de criação carimbado em cada saída. Uma versão preliminar não pode ser congelada até que uma pessoa a aprove: o portão de congelamento rejeita qualquer entrada criada por um modelo sem uma aprovação humana, um motivo e o hash do rascunho exato que foi aprovado.

`canon build` é endereçável por conteúdo — sua saída é indexada por um `canon_sha` e armazenada em cache, portanto, uma reconstrução canônica inalterada é feita instantaneamente. `canon freeze` testemunha cada congelamento em relação a uma versão específica e anexa a um rastreamento de auditoria `freeze-events.jsonl`: as entradas `frozen` rejeitam a regeneração diretamente, as entradas `soft-advisory` rejeitam por padrão (ignorar com `--i-know`). `canon drift` recalcula o hash de cada entrada monitorada e sinaliza qualquer coisa que tenha se movido desde a última construção limpa.

Fluxo de trabalho completo no manual: [Construção canônica](handbook/canon-build/), [Congelamento canônico](handbook/canon-freeze/) e [Empilhamento de duas LORAs](handbook/two-lora-stacking/).

## O que ele produz

Sete artefatos de conjunto de dados e um ambiente de trabalho de produção completo. Cada artefato está vinculado aos seus predecessores para que você possa rastrear qualquer registro de treinamento até a regra que o aprovou.

| Artefato | O que é |
|----------|-----------|
| **Snapshot** | Registro de seleção congelado com impressão digital de configuração. Cada inclusão tem uma razão explícita. |
| **Split** | Partição de treinamento/validação/teste onde as famílias de assuntos nunca cruzam as fronteiras. |
| **Export package** | Conjunto de dados autônomo: manifesto, metadados, imagens, divisões, cartão de conjunto de dados, somas de verificação. |
| **Eval pack** | Tarefas de teste com conhecimento do cânone: cobertura de faixa, desvio proibido, âncora/ouro, continuidade do assunto. |
| **Training package** | Layout pronto para treinamento por meio de adaptadores (`diffusers-lora`, `generic-image-caption`). A mesma verdade, formato diferente. |
| **Eval scorecard** | Aprovação/reprovação por tarefa, a partir da avaliação dos resultados gerados em relação aos pacotes de avaliação. |
| **Implementation pack** | Exemplos de prompts, falhas conhecidas, testes de continuidade e orientações para reprocessamento. |

O ambiente de produção adiciona:

| Superfície | O que faz |
|---------|-------------|
| **Compiled brief** | Instrução de geração determinística a partir do perfil do fluxo de trabalho + verdade do projeto. |
| **Run** | Artefato de execução congelado: resumo + sementes + resultados ComfyUI + manifesto. |
| **Critique** | Avaliação estruturada multidimensional dos resultados da execução em relação ao cânone. |
| **Batch** | Produção coordenada em vários slots (folhas de expressão, painéis de ambiente, pacotes de silhueta). |
| **Selection** | Artefato de decisão criativa: quais resultados foram escolhidos, por quê e de onde vieram. |
| **Re-ingest** | Os resultados selecionados são retornados como registros candidatos com a proveniência completa da geração. |

## Por que isso existe

Os dados de treinamento são o artefato de maior impacto em qualquer pipeline de IA visual. Mas a maioria dos dados de treinamento é uma pasta de imagens sem histórico, sem rastreamento de julgamento e sem conexão com as regras de estilo que deveriam ser seguidas.

O Style Dataset Lab torna a conexão explícita. Sua constituição define as regras. Sua rubrica define as dimensões de avaliação. Seus registros de curadoria registram o julgamento. Sua vinculação ao cânone comprova a conexão. E seu conjunto de dados carrega tudo isso para frente como uma verdade estruturada, pesquisável e reproduzível.

O resultado prático: quando seu LoRA se desvia, você pode perguntar *por quê*. Quando sua próxima rodada de treinamento precisar de dados melhores, você saberá exatamente quais registros estão próximos de falhar e qual regra específica eles não cumpriram. Quando um novo membro da equipe perguntar qual é a linguagem visual do projeto, a resposta não será um painel do Figma — será uma constituição pesquisável com 1.182 exemplos graduados.

## Comprovado na produção

Este não é um pipeline de demonstração. Duas LoRAs de estilo reais foram implementadas de ponta a ponta por meio dele — o mesmo ciclo cânone → curadoria → treinamento → implementação, em extremidades opostas do espectro de curadoria.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (design de criaturas) — um cânone de bestiário criado do zero, **~34% de aprovação** em 293 registros selecionados (169 rejeitados — o filtro rejeita com rigor). Implementado `tallow_fen_style_v3.safetensors` @ 1.5 em `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (design de conceito) — cânone denso e pré-formado, **~96% de aprovação** em 180 registros. Implementado `rustline_v3ckpt_1500.safetensors` @ 1.0 em `qwen-image`, reutilizado em um segundo projeto.

O mesmo pipeline, dois perfis de produção: o filtro de curadoria é real (ele rejeita com rigor em assuntos abertos) e o cânone disciplinado gera alta aceitação.

## Cinco domínios, regras reais

Não são apenas modelos de exemplo. Cada domínio é fornecido com regras de constituição de nível de produção, definições de faixa, rubricas de avaliação e vocabulário de grupo.

| Domínio | Faixas | O que é avaliado |
|--------|-------|-----------------|
| **game-art** | personagem, ambiente, acessório, IU, nave, interior, equipamento | Silhueta na escala de jogabilidade, identificação de facção, desgaste e envelhecimento |
| **character-design** | retrato, corpo inteiro, rotação, folha de expressão, pose de ação | Proporções, lógica do traje, personalidade, clareza da linguagem corporal |
| **creature-design** | conceito, ortográfico, estudo de detalhes, ação, referência de escala, habitat | Anatomia, lógica evolutiva, distinção de silhueta |
| **architecture** | exterior, interior, paisagem urbana, detalhes estruturais, ruína, paisagem | Estrutura, consistência do material, perspectiva, coerência de época |
| **vehicle-mech** | exterior, cabine, componente, esquema, folha de silhueta, variante de dano | Lógica mecânica, linguagem de design, pontos de acesso, narrativa de dano |

## Estrutura do projeto

Cada projeto é autocontido. Cinco arquivos de configuração JSON definem as regras; tudo o mais são dados.

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

## Propriedades de confiança

Não são apenas aspirações. São aplicadas.

- **As capturas de tela são imutáveis.** A impressão digital da configuração (SHA-256) prova que nada mudou. Os IDs são reivindicados atomicamente, portanto, duas execuções simultâneas não podem se intercalar em um único diretório.
- **As divisões evitam vazamentos — e a verificação que confirma isso é independente.** As famílias de objetos (por identidade, linhagem ou ID normalizado) nunca cruzam os limites da partição, e uma segunda verificação rederiva a identidade do objeto do zero, em vez de reler o mapa que a própria divisão usou. Um cartão de conjunto de dados apenas afirma "vazamento: nenhum (verificado)" quando ambas as verificações são executadas e aprovadas; uma divisão anterior à segunda verificação afirma exatamente isso.
- **Os manifestos são contratos congelados.** Hash de exportação + impressão digital da configuração, e `validate` recalcula o hash de cada arquivo `checksums.txt` listado — portanto, substituir uma imagem dentro de uma exportação concluída é detectado, incluindo para manifestos criados antes que essa verificação existisse.
- **As execuções fixam seu gráfico exato.** Cada geração registra `comfy_workflow_sha` + hashes de conteúdo do modelo/LoRA + política de semente, para que uma onda possa ser reproduzida byte a byte. Os executores JS e Python são mantidos em um hash byte a byte por um teste que os inicia. O hash do modelo é opcional (`--hash-models`) e nunca é fabricado — um arquivo irresolvível registra `sha256: null` com uma nota.
- **Nenhum modelo verifica sua própria saída.** Os julgamentos registram `judged_by_model` e `generator_model`; um aviso é acionado se eles forem o mesmo modelo.
- **Um julgamento indica quem o fez.** `eligibility audit` distingue os julgamentos escritos por uma pessoa dos julgamentos gerados por um script em lote, para que uma justificativa que descreva uma categoria em vez de uma imagem não possa ser considerada como curadoria.
- **A medição não é o veredicto.** `sdlab measure` anexa números a um registro. Nunca define um julgamento, um ajuste ou uma aprovação — e onde uma medida é indefinida para uma imagem, registra `null` em vez de um número plausível.
- **Uma versão pode provar de onde veio cada imagem.** `sdlab verify --project <name>` percorre a cadeia offline para cada registro: o proprietário e a licença no registro, a entrada do cânone à qual estava vinculado (por hash), a licença de cada modelo e LoRA que o criou (ID SPDX, URL da licença, a data em que foi lido e o hash do arquivo) e o hash do fluxo de trabalho no manifesto da execução. Uma ligação ausente faz com que a verificação falhe, em vez de ser aprovada.
- **Os adaptadores não podem alterar a verdade.** Layout diferente, mesmos registros. Sem adições, sem remoções, sem reclassificação.
- **As saídas geradas entram novamente por meio da revisão.** Sem desvio. Curadoria e vinculação como tudo o mais. As imagens geradas externamente entram da mesma forma por meio de `sdlab ingest`, sem curadoria.
- **As falhas são visíveis.** Um registro ausente, uma imagem que não pode ser colocada ou uma legenda que não pode ser criada interrompe uma exportação ou pacote de treinamento, em vez de simplesmente reduzi-lo.

## Star Freight

O repositório inclui um exemplo completo e funcional: 1.182 registros, 5 facções, 7 rotas, 24 regras de constituição, 892 ativos aprovados, 2 perfis de treinamento. Um cânone visual de RPG de ficção científica, totalmente organizado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos de saída

`sdlab` é o proprietário do conjunto de dados. A conversão de formato é tratada por [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e muito mais. `repo-dataset` renderiza; nunca decide a inclusão.

## Instalação

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requer Node.js 20+ e [ComfyUI](https://github.com/comfyanonymous/ComfyUI) em localhost:8188 para geração.

### Experimente sem ComfyUI

Você pode explorar toda a superfície não de geração — inspeção, curadoria, captura de tela, divisão, exportação — usando o projeto Star Freight incluído, sem instalar ComfyUI ou baixar quaisquer pesos SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` valida cada configuração de projeto (constituição, rotas, rubrica, terminologia) e relata a elegibilidade sem tocar na GPU. Qualquer comando que modifique o estado gerado aceita `--dry-run` para visualizar o efeito primeiro.

Se você esquecer `--project`, a CLI volta ao primeiro projeto que encontrar em `projects/` e imprime um aviso — passe `--project` explicitamente para silenciá-lo.

### Retomando uma execução interrompida

Execuções de geração longas podem ser retomadas sem refazer o trabalho concluído:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Ambos os comandos funcionam porque cada slot grava sua entrada de manifesto atomicamente quando termina — uma falha no meio da execução nunca corrompe o estado parcial.

## Solução de problemas

Modos de falha comuns e soluções:

**`ECONNREFUSED 127.0.0.1:8188` em qualquer `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
ComfyUI não está em execução. Inicie ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e confirme com `curl http://127.0.0.1:8188/system_stats`. Para apontar para um host/porta diferente, defina `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
O perfil de fluxo de trabalho nomeia um arquivo de modelo que não está na pasta `models/checkpoints/` ou `models/loras/` de ComfyUI. Abra `projects/<project>/workflows/profiles/<profile>.json`, localize o campo `checkpoint` ou `lora` e baixe o peso referenciado ou troque-o por um que você já tenha. Execute `sdlab project doctor --project <project>` novamente para confirmar a correção.

**Erros `sdlab project doctor`**
Doctor retorna códigos de erro estruturados. Alguns comuns:
- `E_PROJECT_NOT_FOUND` — o diretório do projeto não existe em `projects/`. Verifique a ortografia.
- `E_CONFIG_INVALID` — um dos cinco arquivos de configuração JSON falhou na validação do esquema. O campo `hint` nomeia o arquivo e o campo com problemas.
- `E_RECORD_DRIFT` — a impressão digital da configuração de um registro não corresponde mais à sua fonte. Reorganize ou redefina conforme a sugestão.

**`No --project specified, falling back to <name>`**
Um aviso suave. Passe `--project <name>` explicitamente para selecionar o projeto correto e silenciar o aviso.

**Problemas de memória VRAM / Painterly**
Consulte `docs/internal/HANDOFF.md` para obter as notas de ajuste de desfoque "painterly". Em resumo: diminua a força do desfoque, reduza o tamanho do lote ou altere para um ponto de verificação menor em seu perfil de fluxo de trabalho.

**Relatando bugs**
Crie um problema em https://github.com/mcp-tool-shop-org/style-dataset-lab/issues com sua versão do sdlab (`sdlab --version`), versão do Node (`node -v`), o comando completo e a saída de erro estruturada. Um modelo de relatório de bug preenche os campos.

## Segurança

Local por padrão. Sem telemetria, sem análise e sem solicitações externas da CLI `sdlab`: as imagens permanecem em sua GPU e sistema de arquivos, e `canon draft` recusa qualquer ponto de extremidade que não seja o loopback.

A única exceção é a opção de adesão voluntária. `scripts/colab/` contém kits de lançamento para executar um processo de renderização ou uma etapa de treinamento LoRA na sua própria conta do Google Colab. Eles carregam apenas os arquivos que você especificar, são executados dentro de um limite de gastos lido do saldo atual da sua conta Colab e encerram a própria sessão ao serem encerrados. Estes kits são **experimentais**: ainda não passaram por um teste completo em um ambiente real.

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
