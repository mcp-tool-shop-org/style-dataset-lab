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

Escreva suas regras visuais. Gere imagens. Avalie cada imagem com base nessas regras. Envie os resultados como dados de treinamento versionados e auditáveis, e então coloque os modelos treinados em operação em fluxos de trabalho de produção reais, e alimente os melhores resultados de volta para o seu conjunto de dados.

O Style Dataset Lab conecta o que você escreveu sobre o estilo da sua arte ao conjunto de dados que você realmente usa para treinamento. Você define uma estrutura – regras de silhueta, restrições de paleta, linguagem de materiais, o que for importante para o seu projeto. O processo gera candidatos, os avalia com base nessas regras e organiza as obras aprovadas em conjuntos de dados reproduzíveis, onde cada registro explica por que foi incluído.

Em seguida, a área de trabalho de produção assume o controle: compile as instruções de geração a partir da "verdade" do projeto, execute-as no ComfyUI, critique os resultados, produza em lote planilhas de expressões e painéis de ambiente, selecione os melhores resultados e reintroduza-os como novos candidatos. O ciclo se fecha: produza, selecione, revise, fortaleça.

## O processo

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

Essa última instrução é o ponto crucial. Os resultados selecionados passam pelo mesmo processo de revisão que tudo o mais. O conjunto de dados cresce e as regras permanecem válidas.

## O que ele produz

Sete artefatos do conjunto de dados e uma área de trabalho de produção completa. Cada artefato está vinculado aos seus predecessores, para que você possa rastrear qualquer registro de treinamento até a regra que o aprovou.

| Artefato | O que é |
|----------|-----------|
| **Snapshot** | Seleção de registros fixos com impressão digital de configuração. Cada inclusão tem uma razão explícita. |
| **Split** | Partição de treinamento/validação/teste, onde as famílias de elementos nunca ultrapassam as fronteiras. |
| **Export package** | Conjunto de dados autônomo: manifesto, metadados, imagens, divisões, descrição do conjunto de dados e checksums. |
| **Eval pack** | Tarefas de verificação compatíveis com as referências: cobertura de aspectos, prevenção de desvios indesejados, pontos de referência/referências, continuidade do sujeito. |
| **Training package** | Formato pronto para treinamento através de adaptadores (`diffusers-lora`, `generic-image-caption`). A mesma informação, em formato diferente. |
| **Eval scorecard** | Avaliação de aprovação/reprovação para cada tarefa, com base na avaliação das saídas geradas. |
| **Implementation pack** | Exemplos de prompts, falhas conhecidas, testes de continuidade e diretrizes para reintrodução. |

A área de trabalho de produção adiciona:

| Interface | O que ela faz |
|---------|-------------|
| **Compiled brief** | Geração determinística a partir do perfil do fluxo de trabalho + "verdade" do projeto. |
| **Run** | Artefato de execução congelado: instrução + sementes + resultados do ComfyUI + manifesto. |
| **Critique** | Avaliação estruturada e multidimensional dos resultados em relação ao padrão. |
| **Batch** | Produção coordenada em vários canais (planilhas de expressões, painéis de ambiente, pacotes de silhuetas). |
| **Selection** | Artefato de decisão criativa: quais resultados foram escolhidos, por quê e de onde vieram. |
| **Re-ingest** | Os resultados selecionados são retornados como registros candidatos com total rastreabilidade da geração. |

## Por que isso existe

Os dados de treinamento são o recurso mais valioso em qualquer pipeline de IA visual. No entanto, a maioria dos dados de treinamento é apenas uma pasta de imagens sem histórico, sem rastreamento de avaliação e sem conexão com as regras de estilo que deveria seguir.

O Style Dataset Lab torna essa conexão explícita. Sua estrutura define as regras. Sua rubrica define as dimensões de avaliação. Seus registros de curadoria documentam a avaliação. Seu cânone vinculante prova a conexão. E seu conjunto de dados carrega tudo isso como uma verdade estruturada, pesquisável e reproduzível.

O resultado prático: quando seu LoRA se desvia, você pode perguntar *por quê*. Quando sua próxima rodada de treinamento precisar de melhores dados, você saberá exatamente quais registros estão próximos do ideal e qual regra específica eles não cumpriram. Quando um novo membro da equipe perguntar qual é a linguagem visual do projeto, a resposta não é um quadro do Figma – é uma estrutura pesquisável com 1.182 exemplos classificados.

## Cinco domínios, regras reais

Não são modelos genéricos. Cada domínio é fornecido com regras de estrutura de produção, definições de categorias, rubricas de avaliação e vocabulário específico.

| Domínio | Aspectos | O que é avaliado. |
|--------|-------|-----------------|
| **game-art** | personagem, ambiente, acessório, interface do usuário, nave, interior, equipamento | Silhueta em escala de jogabilidade, identificação de facção, desgaste e envelhecimento. |
| **character-design** | retrato, corpo inteiro, vista de 360 graus, folha de expressões, pose de ação | Proporções, lógica de figurino, personalidade, clareza de gestos. |
| **creature-design** | conceito, ortográfico, estudo de detalhes, ação, referência de escala, habitat | Anatomia, lógica evolutiva, distinção de silhueta. |
| **architecture** | exterior, interior, paisagem urbana, detalhe estrutural, ruína, paisagem | Estrutura, consistência de materiais, perspectiva, coerência de época. |
| **vehicle-mech** | exterior, cockpit, componente, esquema, folha de silhuetas, variação de dano | Lógica mecânica, linguagem de design funcional, pontos de acesso, descrição de danos. |

## Estrutura do projeto

Cada projeto é autônomo. Cinco arquivos de configuração JSON definem as regras; o resto é apenas dados.

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

## Propriedades de confiabilidade

Essas propriedades não são apenas desejáveis; elas são aplicadas.

- **Os snapshots são imutáveis.** A impressão digital de configuração (SHA-256) prova que nada foi alterado.
- **As divisões evitam vazamentos.** As famílias de elementos (por identidade, linhagem ou sufixo de ID) nunca ultrapassam as fronteiras das partições.
- **Os manifestos são contratos fixos.** Hash de exportação + impressão digital de configuração. Se algo mudar, crie um novo.
- **Os adaptadores não podem alterar a verdade.** Formato diferente, mesmos registros. Sem adições, sem remoções, sem reclassificações.
- **As saídas geradas são submetidas à revisão.** Sem atalhos. Curadoria e vinculação como tudo o mais.

## Star Freight

O repositório inclui um exemplo completo e funcional: 1.182 registros, 5 facções, 7 caminhos, 24 regras constitucionais, 892 ativos aprovados e 2 perfis de treinamento. Um cânone visual de RPG de ficção científica, totalmente organizado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos compatíveis

O projeto `sdlab` é o proprietário do conjunto de dados. A conversão de formatos é gerenciada pelo [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e outros. O `repo-dataset` é responsável pela renderização; ele nunca decide a inclusão de dados.

## Instalação

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requer Node.js 20 ou superior e o [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instalado localmente no endereço localhost:8188 para a geração.

### Experimente sem o ComfyUI

Você pode explorar toda a interface de geração — inspeção, curadoria, instantâneo, divisão, exportação — usando o projeto Star Freight incluso, sem instalar o ComfyUI ou baixar nenhum arquivo de peso do SDXL.

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

O comando `sdlab project doctor` valida todas as configurações do projeto (constituição, caminhos, critérios, terminologia) e informa a elegibilidade sem acessar a GPU. Qualquer comando que modifique o estado gerado aceita a opção `--dry-run` para visualizar o efeito primeiro.

Se você esquecer `--project`, a interface de linha de comando (CLI) volta para o primeiro projeto que encontra em `projects/` e exibe um aviso — use `--project` explicitamente para silenciá-lo.

### Retomando uma execução interrompida

Execuções longas de geração podem ser retomadas sem a necessidade de refazer o trabalho já concluído:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

Ambos os comandos funcionam porque cada slot escreve sua entrada de manifesto de forma atômica ao finalizar — um erro durante a execução nunca corrompe o estado parcial.

## Solução de problemas

Modos de falha comuns e soluções:

**`ECONNREFUSED 127.0.0.1:8188` em qualquer comando `sdlab generate` / `sdlab run generate` / `sdlab batch generate`**
O ComfyUI não está em execução. Inicie o ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`) e confirme com `curl http://127.0.0.1:8188/system_stats`. Para apontar para um host/porta diferente, defina `COMFY_URL=http://host:port`.

**`missing checkpoint` / `LoRA weight not found`**
O perfil do seu fluxo de trabalho nomeia um arquivo de modelo que não está na pasta `models/checkpoints/` ou `models/loras/` do ComfyUI. Abra `projects/<projeto>/workflows/profiles/<perfil>.json`, localize o campo `checkpoint` ou `lora` e, em seguida, baixe o arquivo de peso referenciado ou substitua-o por um que você já tenha. Execute novamente `sdlab project doctor --project <projeto>` para confirmar a correção.

**Erros do `sdlab project doctor`**
O Doctor retorna códigos de erro estruturados. Alguns comuns:
- `E_PROJECT_NOT_FOUND` — o diretório do projeto não existe em `projects/`. Verifique a ortografia.
- `E_CONFIG_INVALID` — um dos cinco arquivos de configuração JSON falhou na validação do esquema. O campo `hint` indica qual arquivo e campo estão incorretos.
- `E_RECORD_DRIFT` — a impressão digital de configuração de um registro não corresponde mais à sua origem. Reavalie ou redefina conforme sugerido na dica.

**`No --project specified, falling back to <name>`**
Um aviso leve. Use `--project <nome>` explicitamente para selecionar o projeto correto e silenciar o aviso.

**Problemas relacionados à renderização / Falta de memória na VRAM**
Consulte o arquivo `docs/internal/HANDOFF.md` para obter informações sobre o ajuste fino da remoção de ruído (denoise). Em resumo: diminua a intensidade da remoção de ruído, reduza o tamanho do lote ou utilize um modelo (checkpoint) menor no seu perfil de trabalho.

**Relatando erros**
Registre um problema em https://github.com/mcp-tool-shop-org/style-dataset-lab/issues, incluindo a versão do sdlab (`sdlab --version`), a versão do Node (`node -v`), o comando completo e a saída de erro formatada. Um modelo de relatório de erro preenche automaticamente os campos.

## Segurança

Funciona apenas localmente. Não há coleta de dados de uso, análises ou requisições externas. As imagens permanecem na sua GPU e no seu sistema de arquivos.

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
