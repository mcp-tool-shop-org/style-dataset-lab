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

विज़ुअल डेटासेट फैक्ट्री -- वीएलएम (VLM) के फाइन-ट्यूनिंग के लिए मल्टीमॉडल प्रशिक्षण डेटा उत्पन्न करें, क्यूरेट करें और निर्यात करें।

## यह क्या है

यह एक टूलकिट है जिसका उपयोग "**प्रशिक्षण योग्य दृश्य सत्य**" बनाने के लिए किया जाता है। प्रत्येक एसेट में तीन चीजें होती हैं:

1. **इमेज पिक्सेल** -- ComfyUI द्वारा उत्पन्न, जिसमें पूर्ण जानकारी (चेकपॉइंट, LoRA, सीड, सैंपलर, cfg) शामिल है।
2. **मानक व्याख्या** -- यह क्यों 'ऑन-स्टाइल' या 'ऑफ-स्टाइल' है, जो एक 'स्टाइल संविधान' पर आधारित है।
3. **गुणवत्ता मूल्यांकन** -- स्वीकृत/अस्वीकृत, जिसमें प्रत्येक आयाम के लिए स्कोर और संदर्भित नियम शामिल हैं।

आउटपुट [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) में जाता है ताकि 10 प्रारूपों में मल्टीमॉडल प्रशिक्षण डेटा उत्पन्न किया जा सके: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, RLHF जोड़े, DPO, कैप्शनिंग और वर्गीकरण।

## सुरक्षा मॉडल

**केवल स्थानीय।** style-dataset-lab, `localhost:8188` पर ComfyUI से संवाद करता है और कभी भी बाहरी नेटवर्क अनुरोध नहीं करता है। कोई टेलीमेट्री नहीं, कोई विश्लेषण नहीं, कोई डेटा संग्रह नहीं। इमेज जेनरेशन पूरी तरह से आपके GPU पर होता है। रिकॉर्ड और अन्य डेटा आपके फ़ाइल सिस्टम पर ही रहते हैं।

## डेटासेट आँकड़े

| मेट्रिक | मान |
|--------|-------|
| क्यूरेट किए गए रिकॉर्ड | 1,182 |
| कुल एसेट | 2,571 (893 स्वीकृत, 887 'पेंटरली' वेरिएंट) |
| प्रॉम्प्ट वेव्स | 28 |
| विज़ुअल श्रेणियां | 18 (पोशाक, जहाज, आंतरिक भाग, उपकरण, वातावरण, प्रजातियां, स्टेशन, संकेत, प्रकाश, माल, आर्किटेक्चर, जीव, सतह, दैनिक जीवन, ग्रह, क्षति/मरम्मत, एलियन जीव विज्ञान, वास्तविक विवरण) |
| जोड़े में तुलनाएं | 6 मानव + 71 सिंथेटिक |
| विभिन्न अस्वीकृति प्रकार | 30+ |
| पहचान पैकेज सिस्टम | नाम वाले पात्र, जिनमें गुट (faction) की जानकारी, रैंक और दृश्य संबंधी विशेषताएं शामिल हैं। |
| निर्यात प्रारूप | 10 ( `@mcptoolshop/repo-dataset` के माध्यम से) |

## इंस्टॉल करें

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

फिर एक प्रोजेक्ट को क्लोन करें या एक नया डेटासेट वर्कस्पेस इनिशियलाइज़ करें:

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## वर्कफ़्लो

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

## डायरेक्टरी संरचना

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
