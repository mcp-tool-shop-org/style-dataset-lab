<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.md">English</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

अपने दृश्य नियमों को लिखें। कला उत्पन्न करें। प्रत्येक छवि का मूल्यांकन उन नियमों के आधार पर करें। परिणामों को संस्करणित और ऑडिट योग्य प्रशिक्षण डेटा के रूप में प्रस्तुत करें। फिर, प्रशिक्षित मॉडलों को वास्तविक उत्पादन प्रक्रियाओं में उपयोग करें और सर्वोत्तम परिणामों को वापस अपने डेटासेट में शामिल करें।

स्टाइल डेटासेट लैब आपके कलात्मक शैली के बारे में आपने जो कुछ भी लिखा है, उसे उस डेटासेट से जोड़ता है जिससे आप वास्तव में प्रशिक्षण लेते हैं। आप एक "संविधान" परिभाषित करते हैं - जैसे कि आकार के नियम, रंग पैलेट की सीमाएं, सामग्री का विवरण, या जो भी आपके प्रोजेक्ट के लिए महत्वपूर्ण है। यह प्रणाली संभावित विकल्पों को उत्पन्न करती है, उन्हें आपके द्वारा परिभाषित नियमों के आधार पर मूल्यांकन करती है, और स्वीकृत कार्यों को ऐसे डेटासेट में व्यवस्थित करती है जो पुन: प्रयोज्य हों, जहां प्रत्येक प्रविष्टि यह बताती है कि उसे क्यों शामिल किया गया है।

फिर उत्पादन कार्यक्षेत्र (प्रोडक्शन वर्कबेंच) सक्रिय होता है: यह प्रोजेक्ट की वास्तविकताओं से संकलित किए गए विवरणों को लेता है, उन्हें कॉमफीयूआई (ComfyUI) के माध्यम से संसाधित करता है, परिणामों की समीक्षा करता है, बड़ी संख्या में एक्सप्रेशन शीट और वातावरण संबंधी चित्र बनाता है, सर्वोत्तम परिणामों का चयन करता है, और उन्हें नए विकल्पों के रूप में फिर से उपयोग करता है। यह प्रक्रिया एक चक्र में चलती रहती है: उत्पादन, चयन, समीक्षा, और सुधार।

## पाइपलाइन।

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

"वह अंतिम आदेश महत्वपूर्ण है। चुने गए आउटपुट भी बाकी सब कुछ की तरह ही, उसी समीक्षा प्रक्रिया से गुजरते हैं। डेटा संग्रह लगातार बढ़ रहा है और नियम अभी भी लागू हैं।"

## यह क्या उत्पादित करता है।

सात डेटासेट संबंधी अभिलेखागार (आर्टिफैक्ट) और एक पूर्ण उत्पादन कार्यक्षेत्र उपलब्ध हैं। प्रत्येक अभिलेखागार अपने पूर्ववर्ती अभिलेखागार से जुड़ा हुआ है, जिससे आप किसी भी प्रशिक्षण रिकॉर्ड को उस नियम तक वापस खोज सकते हैं जिसने उसे स्वीकृत किया था।

| पुरातत्विक वस्तु। | यह क्या है। |
|----------|-----------|
| **Snapshot** | ठहरा हुआ रिकॉर्ड चयन, जिसमें कॉन्फ़िगरेशन की जानकारी शामिल है। प्रत्येक शामिल किए गए रिकॉर्ड का एक स्पष्ट कारण है। |
| **Split** | प्रशिक्षण (ट्रेन), मूल्यांकन (वैल), और परीक्षण (टेस्ट) डेटासेट को इस तरह विभाजित किया गया है कि किसी भी विषय परिवार के सदस्य इन विभाजनों के बीच न आएं। |
| **Export package** | स्वतंत्र डेटासेट: इसमें मैनिफेस्ट (manifest), मेटाडेटा (metadata), चित्र, डेटासेट के विभिन्न भाग, डेटासेट कार्ड और चेकसम (checksums) शामिल हैं। |
| **Eval pack** | कैनन (Canon) के मानकों के अनुरूप सत्यापन कार्य: लेन कवरेज, निषिद्ध विचलन, एंकर/गोल्ड, विषय की निरंतरता। |
| **Training package** | प्रशिक्षण के लिए तैयार लेआउट, जो एडेप्टर (`diffusers-lora`, `generic-image-caption`) के माध्यम से उपलब्ध है। एक ही जानकारी, लेकिन अलग प्रारूप में। |
| **Eval scorecard** | प्रत्येक कार्य के लिए, स्कोरिंग के आधार पर उत्पन्न परिणामों की तुलना मूल्यांकन पैकों से की जाती है, और यह निर्धारित किया जाता है कि परिणाम पास हुआ है या फेल। |
| **Implementation pack** | त्वरित उदाहरण, ज्ञात विफलताएं, निरंतरता परीक्षण, और पुनः उपयोग के लिए मार्गदर्शन। |

उत्पादन कार्यक्षेत्र में निम्नलिखित विशेषताएं शामिल हैं:

| सतह। | यह क्या करता है। |
|---------|-------------|
| **Compiled brief** | कार्यप्रवाह प्रोफाइल और परियोजना की वास्तविक जानकारी के आधार पर, एक निश्चित (निर्धारित) पीढ़ी निर्देश। |
| **Run** | फ्रीज किए गए निष्पादन कलाकृतियाँ: संक्षिप्त विवरण + बीज (seeds) + कॉमफीयूआई (ComfyUI) के आउटपुट + मैनिफेस्ट (manifest)। |
| **Critique** | "रन आउटपुट का मानकीकृत, बहु-आयामी मूल्यांकन, जो कि एक स्थापित मानक के आधार पर किया जाता है।" |
| **Batch** | समन्वित, बहु-स्लॉट उत्पादन (एक्सप्रेशन शीट, पर्यावरण संबंधी बोर्ड, सिल्हूट पैक)। |
| **Selection** | रचनात्मक निर्णय का दस्तावेज़: किन परिणामों का चयन किया गया, क्यों किया गया, और वे कहाँ से प्राप्त हुए। |
| **Re-ingest** | चयनित परिणाम "उम्मीदवार रिकॉर्ड" के रूप में वापस आते हैं, जिनमें पूरी जानकारी शामिल होती है कि वे कैसे उत्पन्न हुए। |

## यह क्यों मौजूद है?

प्रशिक्षण डेटा किसी भी विज़ुअल एआई प्रणाली में सबसे महत्वपूर्ण घटक होता है। लेकिन अधिकांश प्रशिक्षण डेटा छवियों का एक संग्रह होता है, जिसमें कोई पृष्ठभूमि जानकारी, कोई मूल्यांकन प्रक्रिया, और उन शैलीगत नियमों से कोई संबंध नहीं होता जिनका पालन करने की अपेक्षा की जाती थी।

स्टाइल डेटासेट लैब इस संबंध को स्पष्ट रूप से दर्शाता है। आपका संविधान नियमों को परिभाषित करता है। आपका मूल्यांकन मापदंड मूल्यांकन के आयामों को परिभाषित करता है। आपका क्यूरेशन रिकॉर्ड निर्णय को दर्ज करता है। आपका स्थापित सिद्धांत (कैनन) इस संबंध को प्रमाणित करता है। और आपका डेटासेट इन सभी तत्वों को संरचित, खोज योग्य और पुन: प्रस्तुत करने योग्य सत्य के रूप में आगे बढ़ाता है।

परिणामस्वरूप: जब आपका LoRA (लो-रैंक एडाप्टेशन) ठीक से काम नहीं करता, तो आप यह पता लगा सकते हैं कि *क्यों*। जब आपके अगले प्रशिक्षण दौर के लिए बेहतर डेटा की आवश्यकता होती है, तो आप सटीक रूप से जान सकते हैं कि कौन से डेटा रिकॉर्ड लगभग सही हैं और वे किस एक नियम का उल्लंघन करते हैं। जब कोई नया टीम सदस्य पूछता है कि परियोजना की दृश्य भाषा क्या है, तो उत्तर एक Figma बोर्ड नहीं होता है— बल्कि यह 1,182 वर्गीकृत उदाहरणों के साथ एक खोज योग्य संविधान होता है।

## पांच क्षेत्र, वास्तविक नियम।

ये केवल टेम्पलेट नहीं हैं। प्रत्येक डोमेन उच्च गुणवत्ता वाले नियमों, लेन (क्षेत्र) की परिभाषाओं, मूल्यांकन मापदंडों और समूह शब्दावली के साथ आता है।

| डोमेन। | सड़कें। | क्या चीज़ों का मूल्यांकन किया जाता है? |
|--------|-------|-----------------|
| **game-art** | चरित्र, वातावरण, वस्तु, यूआई (उपयोगकर्ता इंटरफ़ेस), जहाज, आंतरिक भाग, उपकरण। | गेमप्ले के पैमाने पर सिल्हूट, गुटों की जानकारी, और पहनने और उम्र बढ़ने के प्रभाव। |
| **character-design** | पोर्ट्रेट (चित्र), पूरे शरीर का चित्रण, विभिन्न कोणों से चित्रण, भावों का चित्रण, गतिशील मुद्रा में चित्रण। | अनुपात, वेशभूषा की तर्कसंगतता, व्यक्तित्व, और हाव-भाव की स्पष्टता। |
| **creature-design** | अवधारणा, वर्तनी संबंधी, विस्तृत अध्ययन, क्रिया, माप का संदर्भ, आवास। | शारीरिक संरचना, विकासवादी तर्क, और आकार की विशिष्टता। |
| **architecture** | बाहरी भाग, आंतरिक भाग, सड़क का दृश्य, संरचनात्मक विवरण, खंडहर, परिदृश्य। | संरचना, सामग्री की एकरूपता, दृष्टिकोण, युग के अनुरूपता। |
| **vehicle-mech** | बाहरी भाग, कॉकपिट, घटक, आरेख, सिल्हूट शीट, क्षति का प्रकार। | यांत्रिक तर्क, कार्यात्मक डिज़ाइन भाषा, पहुंच बिंदु, क्षति विवरण। |

## परियोजना की संरचना।

प्रत्येक परियोजना एक स्वतंत्र इकाई है। पाँच JSON कॉन्फ़िगरेशन फ़ाइलें नियमों को परिभाषित करती हैं; बाकी सब डेटा है।

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

## ट्रस्ट की संपत्ति।

ये केवल इच्छाएं नहीं हैं। ये लागू किए जाने वाले नियम हैं।

- **स्नैपशॉट अपरिवर्तनीय होते हैं।** कॉन्फ़िगरेशन फ़िंगरप्रिंट (SHA-256) यह साबित करता है कि कुछ भी नहीं बदला है।
- **विभाजन डेटा लीक को रोकते हैं।** विषय परिवार (पहचान, वंश या आईडी प्रत्यय के आधार पर) कभी भी विभाजन सीमाओं को पार नहीं करते हैं।
- **मैनिफेस्ट एक निश्चित अनुबंध होते हैं।** एक्सपोर्ट हैश + कॉन्फ़िगरेशन फ़िंगरप्रिंट। यदि कुछ भी बदलता है, तो एक नया बनाएं।
- **एडाप्टर सत्य को बदल नहीं सकते।** अलग लेआउट, लेकिन समान रिकॉर्ड। कोई अतिरिक्त जानकारी नहीं, कोई हटाने नहीं, और कोई पुन: वर्गीकरण नहीं।
- **उत्पन्न आउटपुट समीक्षा के माध्यम से फिर से आते हैं।** कोई शॉर्टकट नहीं। बाकी सब कुछ की तरह, इन्हें भी व्यवस्थित करें और बांधें।

## स्टार फ्रेट।

इस रिपॉजिटरी में एक पूर्ण, कार्यशील उदाहरण शामिल है: 1,182 रिकॉर्ड, 5 गुट, 7 मार्ग, 24 संवैधानिक नियम, 892 स्वीकृत संपत्तियां, 2 प्रशिक्षण प्रोफाइल। यह एक यथार्थवादी विज्ञान-फाई आरपीजी का दृश्य संग्रह है, जो पूरी तरह से तैयार किया गया है।

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## डाउनस्ट्रीम प्रारूप

`sdlab` के पास यह डेटासेट है। प्रारूप रूपांतरण [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) द्वारा संभाला जाता है: TRL, LLaVA, Qwen2-VL, JSONL, Parquet, और अन्य। `repo-dataset` डेटा प्रस्तुत करता है; यह कभी भी शामिल करने का निर्णय नहीं लेता है।

## इंस्टॉल करें

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

इसके लिए Node.js 20+ और [ComfyUI](https://github.com/comfyanonymous/ComfyUI) की आवश्यकता है, जो localhost:8188 पर चल रहा होना चाहिए, ताकि सामग्री उत्पन्न की जा सके।

### इसे बिना ComfyUI के आज़माएं।

आप "स्टार फ्रेट" नामक प्रोजेक्ट का उपयोग करके, बिना किसी भी अतिरिक्त सॉफ़्टवेयर को स्थापित किए या किसी भी एसडीएक्सएल फ़ाइल को डाउनलोड किए, "नॉन-जेनरेशन" (गैर-उत्पादन) की सभी सुविधाओं का पता लगा सकते हैं, जैसे कि निरीक्षण, चयन, स्नैपशॉट, विभाजन और निर्यात।

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab प्रोजेक्ट डॉक्टर` प्रत्येक प्रोजेक्ट कॉन्फ़िगरेशन (संरचना, चरण, मूल्यांकन मानदंड, शब्दावली) की जांच करता है और बिना ग्राफिक्स प्रोसेसिंग यूनिट (GPU) का उपयोग किए, परियोजना की पात्रता की रिपोर्ट देता है। कोई भी कमांड जो उत्पन्न डेटा को बदलता है, `--dry-run` विकल्प के साथ उपयोग किया जा सकता है ताकि पहले उसके प्रभाव को देखा जा सके।

यदि आप `--project` विकल्प को भूल जाते हैं, तो कमांड-लाइन इंटरफेस (CLI) `projects/` फ़ोल्डर के अंतर्गत पाए जाने वाले पहले प्रोजेक्ट का उपयोग करेगा और एक चेतावनी प्रदर्शित करेगा। इस चेतावनी को बंद करने के लिए, `--project` विकल्प को स्पष्ट रूप से निर्दिष्ट करें।

### अवरुद्ध प्रक्रिया को फिर से शुरू करना

लंबे समय तक चलने वाली प्रक्रियाओं को फिर से शुरू किया जा सकता है बिना पहले से किए गए काम को दोहराए:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

दोनों कमांड काम करते हैं क्योंकि प्रत्येक स्लॉट अपनी मैनिफेस्ट प्रविष्टि को पूरा होने पर एक साथ लिखता है - प्रक्रिया के बीच में होने वाली किसी भी खराबी से आंशिक स्थिति दूषित नहीं होती है।

## समस्या निवारण।

सामान्य खराबी के प्रकार और उनके समाधान:

`ECONNREFUSED 127.0.0.1:8188` - यह त्रुटि `sdlab generate`, `sdlab run generate` या `sdlab batch generate` कमांड चलाने के दौरान आ सकती है।

ComfyUI चल नहीं रहा है। ComfyUI को शुरू करें (`python main.py --listen 127.0.0.1 --port 8188`) और `curl http://127.0.0.1:8188/system_stats` कमांड से इसकी पुष्टि करें। यदि आप किसी अन्य होस्ट/पोर्ट का उपयोग करना चाहते हैं, तो `COMFY_URL=http://होस्ट:पोर्ट` सेट करें।

**`चेकपॉइंट गुम है` / `LoRA फ़ाइल नहीं मिली`**

आपके वर्कफ़्लो प्रोफाइल में एक मॉडल फ़ाइल का नाम दिया गया है जो ComfyUI के `models/checkpoints/` या `models/loras/` फ़ोल्डर में मौजूद नहीं है। `projects/<प्रोजेक्ट>/workflows/profiles/<प्रोफाइल>.json` फ़ाइल खोलें, `checkpoint` या `lora` फ़ील्ड ढूंढें, और या तो संदर्भित फ़ाइल को डाउनलोड करें या उसे उस फ़ाइल से बदल दें जो आपके पास पहले से है। सुधार की पुष्टि करने के लिए `sdlab project doctor --project <प्रोजेक्ट>` कमांड को फिर से चलाएं।

**`sdlab प्रोजेक्ट डॉक्टर` त्रुटियां**
डॉक्टर संरचित त्रुटि कोड लौटाता है। कुछ सामान्य त्रुटियां:
- `E_PROJECT_NOT_FOUND` — "projects/" फ़ोल्डर के अंतर्गत प्रोजेक्ट डायरेक्टरी मौजूद नहीं है। वर्तनी की जांच करें।
- `E_CONFIG_INVALID` — पांच JSON कॉन्फ़िगरेशन फ़ाइलों में से किसी एक में स्कीमा सत्यापन विफल हो गया है। "hint" फ़ील्ड में उस गलत फ़ाइल और फ़ील्ड का नाम दिया गया है।
- `E_RECORD_DRIFT` — किसी रिकॉर्ड के कॉन्फ़िगरेशन फ़िंगरप्रिंट अब उसके स्रोत से मेल नहीं खाते हैं। "hint" में दिए गए सुझाव के अनुसार, इसे फिर से व्यवस्थित करें या फिर से जोड़ें।

**`कोई प्रोजेक्ट निर्दिष्ट नहीं है, इसलिए डिफ़ॉल्ट रूप से <नाम> का उपयोग किया जा रहा है`**
यह एक चेतावनी संदेश है। सही प्रोजेक्ट का चयन करने और इस चेतावनी को बंद करने के लिए `--project <नाम>` विकल्प का स्पष्ट रूप से उपयोग करें।

**पेंटरली / वीआरएएम (VRAM) मेमोरी से बाहर होने की समस्याएँ**
"पेंटरली" डीनोइजिंग (denoise) के ट्यूनिंग नोट्स के लिए, `docs/internal/HANDOFF.md` देखें। संक्षेप में: डीनोइजिंग की शक्ति को कम करें, बैच का आकार घटाएं, या अपने वर्कफ़्लो प्रोफाइल में छोटे चेकपॉइंट का उपयोग करें।

**बग की रिपोर्ट करना**
https://github.com/mcp-tool-shop-org/style-dataset-lab/issues पर एक मुद्दा दर्ज करें, जिसमें आपके sdlab संस्करण (`sdlab --version`), नोड संस्करण (`node -v`), पूरा कमांड और संरचित त्रुटि आउटपुट शामिल हों। एक बग रिपोर्ट टेम्पलेट स्वचालित रूप से फ़ील्ड को भर देगा।

## सुरक्षा

यह केवल स्थानीय रूप से काम करता है। इसमें कोई टेलीमेट्री, कोई विश्लेषण और कोई बाहरी अनुरोध शामिल नहीं हैं। छवियां आपके GPU और फ़ाइल सिस्टम पर ही रहती हैं।

## लाइसेंस

एमआईटी (MIT)

---

<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> द्वारा निर्मित।
