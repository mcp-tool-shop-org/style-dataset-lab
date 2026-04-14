<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.md">English</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

एक विज़ुअल डेटासेट बनाने की प्रक्रिया -- जिसमें स्थापित नियमों से लेकर संरचित निर्देशों तक, फिर ComfyUI के माध्यम से सृजन और अंत में, सावधानीपूर्वक तैयार किए गए, नियमों के अनुरूप प्रशिक्षण डेटा शामिल है।

## यह क्या है

संरचित विज़ुअल प्रशिक्षण डेटासेट बनाने के लिए एक **प्रक्रिया**। आप शैली के नियम (नियम) लिखते हैं, निर्देशों को तैयार करते हैं, ComfyUI के साथ सामग्री उत्पन्न करते हैं, प्रत्येक आयाम के आधार पर मूल्यांकन करते हैं, निर्णयों को नियमों से जोड़ते हैं, और `@mcptoolshop/repo-dataset` ([https://github.com/mcp-tool-shop-org/repo-dataset](https://github.com/mcp-tool-shop-org/repo-dataset)) के माध्यम से 10 प्रारूपों में निर्यात करते हैं।

यह प्रक्रिया किसी विशेष गेम पर निर्भर नहीं है। प्रत्येक गेम के लिए `games/<नाम>/` के अंतर्गत एक अलग डेटा निर्देशिका होती है; 13 स्क्रिप्ट और खाली टेम्पलेट साझा किए जाते हैं। प्रत्येक उत्पन्न सामग्री में तीन चीजें होती हैं:

1. **इमेज पिक्सेल** -- ComfyUI द्वारा उत्पन्न, जिसमें पूर्ण जानकारी (चेकपॉइंट, LoRA, सीड, सैंपलर, cfg) शामिल है।
2. **मानक व्याख्या** -- यह क्यों 'ऑन-स्टाइल' या 'ऑफ-स्टाइल' है, जो एक 'स्टाइल संविधान' पर आधारित है।
3. **गुणवत्ता मूल्यांकन** -- स्वीकृत/अस्वीकृत, जिसमें प्रत्येक आयाम के लिए स्कोर और संदर्भित नियम शामिल हैं।

## सुरक्षा मॉडल

**केवल स्थानीय।** style-dataset-lab, `localhost:8188` पर ComfyUI से संवाद करता है और कभी भी बाहरी नेटवर्क अनुरोध नहीं करता है। कोई टेलीमेट्री नहीं, कोई विश्लेषण नहीं, कोई डेटा संग्रह नहीं। इमेज जेनरेशन पूरी तरह से आपके GPU पर होता है। रिकॉर्ड और अन्य डेटा आपके फ़ाइल सिस्टम पर ही रहते हैं।

## npm पैकेज में क्या शामिल है

`npm install @mcptoolshop/style-dataset-lab` आपको निम्नलिखित चीजें देता है:

- **13 स्क्रिप्ट** -- उत्पन्न करें, मूल्यांकन करें, तुलना करें, नियमों से जोड़ें, चित्रकारी शैली में बनाएं, पहचान बनाएं, ControlNet/IP-Adapter के साथ सामग्री बनाएं, बड़ी संख्या में मूल्यांकन करें, डेटा माइग्रेट करें।
- **खाली टेम्पलेट** -- शुरुआती दिशानिर्देश, मूल्यांकन मानदंड और उदाहरण निर्देशों का संग्रह `templates/` में।

npm पैकेज में **गेम डेटा शामिल नहीं** है। यदि आप Star Freight का उदाहरण चाहते हैं (1,182 रिकॉर्ड, 28 निर्देश सेट, 18 विज़ुअल श्रेणियां), तो रिपॉजिटरी को क्लोन करें।

## इंस्टॉल करें

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

टेम्पलेट से एक नया गेम शुरू करने के लिए:

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## मोनोरेपो संरचना

यह प्रक्रिया `scripts/` और `templates/` में मौजूद है। प्रत्येक गेम `games/<नाम>/` में अपनी-अपनी नियमों, रिकॉर्ड और सामग्री के साथ मौजूद होता है। स्क्रिप्ट `--game <नाम>` विकल्प स्वीकार करती हैं (डिफॉल्ट रूप से `star-freight` पर सेट)।

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

## प्रक्रिया का प्रवाह

नियमों से लेकर प्रशिक्षण डेटा के निर्यात तक, पूरी प्रक्रिया:

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

## एक नया गेम जोड़ना

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## प्रत्येक गेम निर्देशिका का लेआउट

प्रत्येक `games/<नाम>/` निर्देशिका में निम्नलिखित शामिल हैं:

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

## जेनरेशन सेटअप

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

अतिरिक्त जेनरेशन मोड: ControlNet (पोज़/गहराई-निर्देशित), IP-Adapter (संदर्भ-निर्देशित), और पहचान पैकेज (नाम वाले पात्रों की निरंतरता)।

## आवश्यकताएं

- `localhost:8188` पर चलने वाला [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo चेकपॉइंट + ClassipeintXL LoRA
- Node.js 20+
- प्रशिक्षण के लिए निर्यात के लिए [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)

## लाइसेंस

MIT

---

<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> द्वारा निर्मित।
