<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
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

Escreva suas regras visuais. Gere arte. Avalie cada imagem com base nessas regras. Envie os resultados como dados de treinamento auditáveis e versionados — e, em seguida, coloque modelos treinados para trabalhar em fluxos de trabalho de produção reais e insira as melhores saídas de volta no seu corpus.

O Style Dataset Lab conecta o que você escreveu sobre seu estilo artístico ao conjunto de dados do qual você realmente treina, e então fecha o ciclo até a produção. Você define uma constituição — regras de silhueta, restrições de paleta, linguagem dos materiais, qualquer coisa que seja importante para o seu projeto. O pipeline gera candidatos, avalia-os com base nessas regras e empacota o trabalho aprovado em conjuntos de dados reproduzíveis, onde cada registro explica por que foi incluído.

Em seguida, a estação de trabalho de produção assume o controle: compile resumos de geração a partir da verdade do projeto, execute-os no ComfyUI, critique as saídas, produza em lote folhas de expressão e painéis de ambiente, selecione os melhores resultados e reintroduza-os como novos candidatos. O ciclo se fecha: produzir, selecionar, revisar, fortalecer.

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

Esse último comando é o ponto crucial. As saídas selecionadas retornam pelo mesmo processo de revisão que tudo o mais. O corpus cresce e as regras permanecem válidas.

## Criação do cânone

Before the dataset pipeline runs, the `sdlab canon *` namespace turns your project's canon entity store into the three projections training and production actually consume — and locks the entries that must not drift.

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

`canon build` é endereçável por conteúdo — sua saída é identificada por um `canon_sha` e armazenada em cache, de modo que uma versão inalterada é reconstruída instantaneamente. `canon freeze` registra cada estado contra uma compilação específica e adiciona a um `freeze-events.jsonl` histórico de auditoria: as entradas `frozen` rejeitam explicitamente a regeneração, as entradas `soft-advisory` rejeitam por padrão (ignorar com `--i-know`). `canon drift` recalcula o hash de cada entrada monitorada e sinaliza qualquer coisa que tenha sido alterada desde a última compilação limpa.

Fluxo de trabalho completo no manual: [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/) e [Two-LoRA stacking](handbook/two-lora-stacking/).

## O que ele produz

Sete artefatos de conjunto de dados e uma estação de trabalho de produção completa. Cada artefato está vinculado aos seus predecessores para que você possa rastrear qualquer registro de treinamento até a regra que o aprovou.

| Artefato | O que é |
|----------|-----------|
| **Snapshot** | Seleção de registros congelados com impressão digital da configuração. Cada inclusão tem uma razão explícita. |
| **Split** | Partição de treinamento/validação/teste onde as famílias de assuntos nunca cruzam os limites. |
| **Export package** | Conjunto de dados autônomo: manifesto, metadados, imagens, divisões, cartão do conjunto de dados, somas de verificação. |
| **Eval pack** | Tarefas de teste com reconhecimento do cânone: cobertura da faixa, desvio proibido, âncora/ouro, continuidade do assunto. |
| **Training package** | Layout pronto para treinamento via adaptadores (`diffusers-lora`, `generic-image-caption`). A mesma verdade, formato diferente. |
| **Eval scorecard** | Resultado de aprovação/reprovação por tarefa a partir da pontuação das saídas geradas em relação aos pacotes de avaliação. |
| **Implementation pack** | Exemplos de prompts, falhas conhecidas, testes de continuidade e orientação para reintrodução. |

A estação de trabalho de produção adiciona:

| Superfície | O que faz |
|---------|-------------|
| **Compiled brief** | Instrução de geração determinística a partir do perfil do fluxo de trabalho + verdade do projeto. |
| **Run** | Artefato de execução congelado: resumo + sementes + saídas do ComfyUI + manifesto. |
| **Critique** | Avaliação estruturada multidimensional das saídas da execução em relação ao cânone. |
| **Batch** | Produção coordenada multislot (folhas de expressão, painéis de ambiente, pacotes de silhueta). |
| **Selection** | Artefato de decisão criativa: quais saídas foram escolhidas, por quê e de onde vieram. |
| **Re-ingest** | As saídas selecionadas retornam como registros candidatos com toda a proveniência da geração. |

## Por que isso existe

Os dados de treinamento são o artefato de maior impacto em qualquer pipeline de IA visual. Mas, na maioria das vezes, os dados de treinamento são apenas uma pasta de imagens sem histórico, sem rastreamento de julgamento e sem conexão com as regras de estilo que deveriam ser seguidas.

O Style Dataset Lab torna a conexão explícita. Sua constituição define as regras. Seu rubrica define as dimensões de pontuação. Seus registros de curadoria registram o julgamento. Sua vinculação do cânone prova a conexão. E seu conjunto de dados carrega tudo isso para frente como uma verdade estruturada, pesquisável e reproduzível.

O resultado prático: quando seu LoRA se desvia, você pode perguntar *por quê*. Quando sua próxima rodada de treinamento precisar de melhores dados, você saberá exatamente quais registros estão próximos do ideal e qual regra única eles não cumpriram. Quando um novo membro da equipe perguntar qual é a linguagem visual do projeto, a resposta não será uma placa Figma — será uma constituição pesquisável com 1.182 exemplos graduados.

## Comprovado em produção

Este não é um fluxo de trabalho de demonstração. Duas LoRAs reais foram processadas integralmente através dele — o mesmo ciclo de criação → curadoria → treinamento → lançamento, em extremos opostos do espectro da curadoria.

- **[Tallow Fen](handbook/case-study-tallow-fen/)** (design de criaturas) — um bestiário criado do zero, com aproximadamente **34% de aprovação** em 293 registros selecionados (169 rejeitados — a barreira é rigorosa). Enviado `tallow_fen_style_v3.safetensors` @ 1.5 em `qwen-image`.
- **[Rustline](handbook/case-study-rustline/)** (design conceitual) — um conjunto de dados denso e pré-formatado, com aproximadamente **96% de aprovação** em 180 registros. Enviado `rustline_v3ckpt_1500.safetensors` @ 1.0 em `qwen-image`, reutilizado posteriormente por um segundo projeto.

O mesmo fluxo de trabalho, dois perfis de produção: a triagem da curadoria é real (rejeita rigorosamente temas abertos) e uma abordagem disciplinada na criação resulta em alta aceitação.

## Cinco domínios, regras reais

Não são apenas modelos de exemplo. Cada domínio é fornecido com regras de constituição de nível de produção, definições de faixa, rubricas de pontuação e vocabulário de grupo.

| Domínio | Faixas | O que é avaliado |
|--------|-------|-----------------|
| **game-art** | personagem, ambiente, adereço, interface do usuário, nave, interior, equipamento | Silhueta na escala de jogabilidade, leitura da facção, desgaste e envelhecimento |
| **character-design** | retrato, corpo inteiro, rotação, folha de expressão, pose de ação | Proporções, lógica do traje, personalidade, clareza dos gestos |
| **creature-design** | conceito, ortográfico, estudo de detalhes, ação, referência de escala, habitat | Anatomia, lógica evolutiva, distinção da silhueta |
| **architecture** | exterior, interior, paisagem urbana, detalhe estrutural, ruína, paisagem | Estrutura, consistência do material, perspectiva, coerência de época |
| **vehicle-mech** | exterior, cabine, componente, esquema, folha de silhueta, variante de dano | Lógica mecânica, linguagem de design, pontos de acesso, narrativa de danos |

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

Estas não são apenas aspirações. Elas são aplicadas.

- **Os snapshots são imutáveis.** A impressão digital da configuração (SHA-256) prova que nada foi alterado. Os IDs são reivindicados atomicamente, portanto, duas execuções simultâneas não podem se intercalar em um único diretório.
- **As divisões evitam vazamentos — e a verificação que confirma isso é independente.** As famílias de objetos (por identidade, linhagem ou ID normalizado) nunca cruzam os limites da partição, e uma segunda verificação rederiva a identidade do objeto do zero, em vez de reler o mapa que a própria divisão usou. Um cartão de conjunto de dados apenas afirma "vazamento: nenhum (verificado)" quando ambas as verificações são executadas e aprovadas; uma divisão anterior à segunda verificação indica exatamente isso.
- **Os manifestos são contratos congelados.** Hash de exportação + impressão digital da configuração, e `validate` recalcula o hash de cada arquivo que `checksums.txt` lista — portanto, substituir uma imagem dentro de uma exportação finalizada é detectado, incluindo para manifestos criados antes que essa verificação existisse.
- **As execuções fixam seu grafo exato.** Cada geração registra `comfy_workflow_sha` + hashes do conteúdo do modelo/LoRA + política de sementes, portanto, uma onda pode ser reproduzida byte a byte. Os executores JS e Python são mantidos em um hash idêntico por meio de um teste que os inicia. O hashing do modelo é opcional (`--hash-models`) e nunca fabricado — um arquivo irresolvível registra `sha256: null` com uma nota.
- **Nenhum modelo verifica sua própria saída.** Os julgamentos registram `judged_by_model` e `generator_model`; um aviso é acionado se eles forem o mesmo modelo.
- **Um julgamento indica quem o fez.** `eligibility audit` distingue os julgamentos escritos por uma pessoa dos julgamentos gerados por um script em lote, portanto, uma justificativa que descreve uma categoria em vez de uma imagem não pode ser considerada como curadoria.
- **A medição não é veredicto.** `sdlab measure` anexa números a um registro. Nunca define um julgamento, um ajuste ou uma aprovação — e onde uma medida é indefinida para uma imagem, registra `null` em vez de um número plausível.
- **Os adaptadores não podem alterar a verdade.** Layout diferente, os mesmos registros. Sem adições, sem remoções, sem reclassificações.
- **As saídas geradas entram novamente por meio da revisão.** Sem desvio. Curadoria e vinculação como tudo o mais. As imagens geradas externamente entram da mesma forma via `sdlab ingest`, sem curadoria.
- **As falhas são visíveis.** Um registro ausente, uma imagem que não pode ser colocada ou uma legenda que não pode ser criada interrompe uma exportação ou pacote de treinamento em vez de simplesmente reduzi-lo silenciosamente.

## Star Freight

O repositório inclui um exemplo completo e funcional: 1.182 registros, 5 facções, 7 rotas, 24 regras de constituição, 892 ativos aprovados, 2 perfis de treinamento. Um cânone visual de RPG de ficção científica sombrio, totalmente selecionado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos downstream

`sdlab` é o proprietário do conjunto de dados. A conversão de formato é tratada por [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e muito mais. `repo-dataset` renderiza; nunca decide a inclusão.

## Instalação

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requer Node.js 20+ e [ComfyUI](https://github.com/comfyanonymous/ComfyUI) no localhost:8188 para geração.

### Experimente sem o ComfyUI

Você pode explorar toda a funcionalidade não relacionada à geração — inspeção, curadoria, snapshot, divisão, exportação — usando o projeto Star Freight incluído, sem instalar o ComfyUI ou baixar quaisquer pesos SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` validates every project config (constitution, lanes, rubric, terminology) and reports eligibility without touching the GPU. Any command that mutates generated state accepts `--dry-run` to preview the effect first.

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

Ambos os comandos funcionam porque cada slot grava sua entrada de manifesto atomicamente ao terminar — uma falha no meio da execução nunca corrompe o estado parcial.

## Solução de problemas

Modos de falha comuns e soluções:

**`ECONNREFUSED 127.0.0.1:8188` em qualquer `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
O ComfyUI não está em execução. Inicie o ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e confirme com `curl http://127.0.0.1:8188/system_stats`. Para apontar para um host/porta diferente, defina `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
O perfil do seu fluxo de trabalho nomeia um arquivo de modelo que não está na pasta `models/checkpoints/` ou `models/loras/` do ComfyUI. Abra `projects/<project>/workflows/profiles/<profile>.json`, localize o campo `checkpoint` ou `lora` e baixe o peso referenciado ou substitua-o por um que você já tenha. Execute novamente `sdlab project doctor --project <project>` para confirmar a correção.

**Erros `sdlab project doctor`**
O Doctor retorna códigos de erro estruturados. Alguns comuns:
- `E_PROJECT_NOT_FOUND` — o diretório do projeto não existe em `projects/`. Verifique a ortografia.
- `E_CONFIG_INVALID` — um dos cinco arquivos de configuração JSON falhou na validação do esquema. O campo `hint` nomeia o arquivo e o campo com problemas.
- `E_RECORD_DRIFT` — a impressão digital da configuração de um registro não corresponde mais à sua fonte. Faça uma nova curadoria ou vincule novamente, conforme sugerido.

**Aviso `No --project specified, falling back to <name>`**
Um aviso suave. Passe `--project <name>` explicitamente para selecionar o projeto correto e silenciar o aviso.

**Painterly / VRAM out-of-memory issues**
See `docs/internal/HANDOFF.md` for the painterly denoise tuning notes. In short: lower the denoise strength, reduce batch size, or switch to a smaller checkpoint in your workflow profile.

**Reporting bugs**
File an issue at https://github.com/mcp-tool-shop-org/style-dataset-lab/issues with your sdlab version (`sdlab --version`), Node version (`node -v`), the full command, and the structured error output. A bug-report template prefills the fields.

## Segurança

Apenas local. Sem telemetria, sem análises, sem solicitações externas. As imagens permanecem em sua GPU e sistema de arquivos.

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
