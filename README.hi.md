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

अपनी दृश्य नियम लिखें। कला उत्पन्न करें। प्रत्येक छवि का उन नियमों के अनुसार मूल्यांकन करें। परिणामों को संस्करणित, ऑडिट करने योग्य प्रशिक्षण डेटा के रूप में प्रस्तुत करें — फिर प्रशिक्षित मॉडल को वास्तविक उत्पादन वर्कफ़्लो में उपयोग करें और सर्वोत्तम आउटपुट को वापस अपने डेटासेट में फीड करें।

स्टाइल डेटासेट लैब आपके कला शैली के बारे में आपने जो कुछ भी लिखा है, उसे उस डेटासेट से जोड़ता है जिससे आप वास्तव में प्रशिक्षण लेते हैं, और फिर उत्पादन प्रक्रिया के अंत तक इस चक्र को पूरा करता है। आप एक संविधान परिभाषित करते हैं — सिल्हूट नियम, रंग पैलेट की सीमाएँ, सामग्री भाषा, या आपके प्रोजेक्ट के लिए जो भी महत्वपूर्ण हो। पाइपलाइन संभावित विकल्पों को उत्पन्न करती है, उनका उन नियमों के अनुसार मूल्यांकन करती है, और स्वीकृत कार्यों को पुनरुत्पादनीय डेटासेट में पैकेज करती है, जहाँ प्रत्येक रिकॉर्ड यह बताता है कि इसे क्यों शामिल किया गया था।

फिर उत्पादन वर्कबेंच कार्यभार संभालता है: प्रोजेक्ट की वास्तविकता से पीढ़ी संबंधी संक्षिप्त विवरण संकलित करें, उन्हें ComfyUI के माध्यम से चलाएं, आउटपुट का मूल्यांकन करें, अभिव्यक्ति शीट और पर्यावरण बोर्ड को बैच में तैयार करें, सर्वोत्तम परिणामों का चयन करें, और उन्हें नए संभावित विकल्पों के रूप में फिर से शामिल करें। चक्र पूरा होता है: उत्पन्न करें, चुनें, समीक्षा करें, मजबूत बनाएं।

## पाइपलाइन

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

यह अंतिम कमांड ही महत्वपूर्ण है। चयनित आउटपुट अन्य सभी चीज़ों की तरह समान समीक्षा प्रक्रिया से गुजरते हैं। डेटासेट बढ़ता है और नियम बने रहते हैं।

## मानक सामग्री निर्माण

डेटासेट पाइपलाइन चलने से पहले, `sdlab canon *` नेमस्पेस आपके प्रोजेक्ट के मानक इकाई भंडार को उन तीन अनुमानों में बदल देता है जिनका वास्तव में प्रशिक्षण और उत्पादन में उपयोग किया जाता है — और उन प्रविष्टियों को लॉक कर देता है जिन्हें बदला नहीं जाना चाहिए।

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

`canon build` सामग्री-आधारित है — इसका आउटपुट `canon_sha` द्वारा कुंजीबद्ध होता है और कैश किया जाता है, इसलिए अपरिवर्तित मानक का पुनर्निर्माण तुरंत हो जाता है। `canon freeze` प्रत्येक फ़्रीज़ को एक विशिष्ट बिल्ड के विरुद्ध प्रमाणित करता है और इसे `freeze-events.jsonl` ऑडिट ट्रेल में जोड़ता है: `frozen` प्रविष्टियाँ सीधे पुनरुत्पादन से इनकार करती हैं, `soft-advisory` प्रविष्टियाँ डिफ़ॉल्ट रूप से इनकार करती हैं ( `--i-know` के साथ बाईपास करें)। `canon drift` प्रत्येक देखी गई प्रविष्टि के हैश की फिर से गणना करता है और पिछली स्वच्छ बिल्ड के बाद से बदली हुई किसी भी चीज़ को चिह्नित करता है।

हैंडबुक में संपूर्ण वर्कफ़्लो: [Canon build](handbook/canon-build/), [Canon freeze](handbook/canon-freeze/), और [Two-LoRA stacking](handbook/two-lora-stacking/)।

## यह क्या उत्पन्न करता है

सात डेटासेट कलाकृतियाँ और एक पूर्ण उत्पादन वर्कबेंच। प्रत्येक कलाकृति अपने पूर्ववर्तियों से जुड़ी होती है ताकि आप किसी भी प्रशिक्षण रिकॉर्ड को उस नियम तक ट्रेस कर सकें जिसने इसे स्वीकृत किया था।

| कलाकृति | यह क्या है |
|----------|-----------|
| **Snapshot** | कॉन्फ़िगरेशन फ़िंगरप्रिंट के साथ जमे हुए रिकॉर्ड का चयन। प्रत्येक समावेश का एक स्पष्ट कारण होता है। |
| **Split** | प्रशिक्षण/मान्यकरण/परीक्षण विभाजन जहाँ विषय परिवार कभी भी सीमाओं को पार नहीं करते हैं। |
| **Export package** | स्व-निहित डेटासेट: मेनिफ़ेस्ट, मेटाडेटा, छवियाँ, स्प्लिट्स, डेटासेट कार्ड, चेकसम। |
| **Eval pack** | मानक-जागरूक परीक्षण कार्य: लेन कवरेज, निषिद्ध विचलन, एंकर/गोल्ड, विषय निरंतरता। |
| **Training package** | ट्रेनर-तैयार लेआउट एडेप्टर के माध्यम से (`diffusers-lora`, `generic-image-caption`)। समान सत्य, अलग प्रारूप। |
| **Eval scorecard** | जनरेट किए गए आउटपुट का मूल्यांकन पैक के विरुद्ध करने पर प्रति-कार्य पास/फेल। |
| **Implementation pack** | संकेत उदाहरण, ज्ञात विफलताएँ, निरंतरता परीक्षण और पुन: समावेश मार्गदर्शन। |

उत्पादन वर्कबेंच निम्नलिखित जोड़ता है:

| सतह | यह क्या करता है |
|---------|-------------|
| **Compiled brief** | वर्कफ़्लो प्रोफ़ाइल + प्रोजेक्ट की वास्तविकता से नियतात्मक पीढ़ी निर्देश। |
| **Run** | जमे हुए निष्पादन कलाकृति: संक्षिप्त विवरण + बीज + ComfyUI आउटपुट + मेनिफ़ेस्ट। |
| **Critique** | मानक के विरुद्ध रन आउटपुट का संरचित बहु-आयामी मूल्यांकन। |
| **Batch** | समन्वित बहु-स्लॉट उत्पादन (अभिव्यक्ति शीट, पर्यावरण बोर्ड, सिल्हूट पैक)। |
| **Selection** | रचनात्मक निर्णय कलाकृति: किन आउटपुट को चुना गया, क्यों और वे कहाँ से आए। |
| **Re-ingest** | चयनित आउटपुट पूर्ण पीढ़ी के मूल के साथ उम्मीदवार रिकॉर्ड के रूप में वापस आते हैं। |

## यह क्यों मौजूद है

प्रशिक्षण डेटा किसी भी दृश्य AI पाइपलाइन में सबसे महत्वपूर्ण कलाकृति है। लेकिन अधिकांश प्रशिक्षण डेटा छवियों का एक फ़ोल्डर होता है जिसमें कोई इतिहास, कोई निर्णय प्रक्रिया और उस शैली के नियमों से कोई संबंध नहीं होता है जिनका पालन करने वाला था।

स्टाइल डेटासेट लैब कनेक्शन को स्पष्ट करता है। आपका संविधान नियमों को परिभाषित करता है। आपकी रुब्रिक स्कोरिंग आयामों को परिभाषित करती है। आपके क्यूरेशन रिकॉर्ड निर्णय को दर्ज करते हैं। आपका मानक बंधन कनेक्शन साबित करता है। और आपका डेटासेट उन सभी को संरचित, क्वेरेबल, पुनरुत्पादनीय सत्य के रूप में आगे बढ़ाता है।

व्यावहारिक परिणाम: जब आपका LoRA भटकता है, तो आप *क्यों* पूछ सकते हैं। जब आपके अगले प्रशिक्षण दौर में बेहतर डेटा की आवश्यकता होती है, तो आपको पता होता है कि कौन से रिकॉर्ड लगभग विफल रहे और उन्होंने किस एकल नियम का उल्लंघन किया। जब एक नया टीम सदस्य पूछता है कि प्रोजेक्ट की दृश्य भाषा क्या है, तो उत्तर फ़िग्मा बोर्ड नहीं है — यह 1,182 वर्गीकृत उदाहरणों के साथ एक खोज योग्य संविधान है।

## पाँच डोमेन, वास्तविक नियम

कोई प्लेसहोल्डर टेम्पलेट नहीं। प्रत्येक डोमेन उत्पादन-ग्रेड संविधान नियमों, लेन परिभाषाओं, स्कोरिंग रुब्रिक और समूह शब्दावली के साथ आता है।

| डोमेन | लेन | क्या मूल्यांकन किया जाता है |
|--------|-------|-----------------|
| **game-art** | चरित्र, पर्यावरण, प्रॉप, UI, जहाज, आंतरिक भाग, उपकरण | गेमप्ले पैमाने पर सिल्हूट, गुट पढ़ना, पहनना और उम्र बढ़ना |
| **character-design** | पोर्ट्रेट, पूर्ण शरीर, टर्नअराउंड, अभिव्यक्ति शीट, एक्शन पोज़ | अनुपात, पोशाक तर्क, व्यक्तित्व, हावभाव स्पष्टता |
| **creature-design** | अवधारणा, ऑर्थोग्राफिक, विवरण अध्ययन, क्रिया, पैमाने संदर्भ, आवास | शरीर रचना विज्ञान, विकासवादी तर्क, सिल्हूट भेद |
| **architecture** | बाहरी भाग, आंतरिक भाग, सड़क दृश्य, संरचनात्मक विवरण, खंडहर, परिदृश्य | संरचना, सामग्री स्थिरता, परिप्रेक्ष्य, युग सामंजस्य |
| **vehicle-mech** | बाहरी भाग, कॉकपिट, घटक, आरेख, सिल्हूट शीट, क्षति भिन्नता | यांत्रिक तर्क, डिजाइन भाषा, पहुंच बिंदु, क्षति कथा |

## परियोजना संरचना

प्रत्येक परियोजना स्वयंपूर्ण है। पाँच JSON कॉन्फ़िगरेशन फ़ाइलें नियमों को परिभाषित करती हैं; बाकी सब डेटा है।

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

## विश्वसनीयता गुण

ये केवल आकांक्षात्मक नहीं हैं। इन्हें लागू किया जाता है।

- **स्नैपशॉट अपरिवर्तनीय होते हैं।** कॉन्फ़िगरेशन फ़िंगरप्रिंट (SHA-256) साबित करता है कि कुछ भी नहीं बदला।
- **विभाजन रिसाव को रोकते हैं।** विषय परिवार (पहचान, वंश या आईडी प्रत्यय के अनुसार) कभी भी विभाजन सीमाओं को पार नहीं करते हैं।
- **मैनिफेस्ट जमे हुए अनुबंध हैं।** निर्यात हैश + कॉन्फ़िगरेशन फ़िंगरप्रिंट। यदि कुछ भी बदलता है, तो एक नया बनाएं।
- **एडेप्टर सत्य को परिवर्तित नहीं कर सकते।** अलग लेआउट, समान रिकॉर्ड। कोई अतिरिक्त नहीं, कोई हटाने नहीं, कोई पुनर्वर्गीकरण नहीं।
- **उत्पन्न आउटपुट समीक्षा के माध्यम से फिर से प्रवेश करते हैं।** कोई बाईपास नहीं। अन्य सभी की तरह क्यूरेट और बांधें।

## स्टार फ्रेट

रिपो में एक पूर्ण कार्यशील उदाहरण शामिल है: 1,182 रिकॉर्ड, 5 गुट, 7 लेन, 24 संविधान नियम, 892 स्वीकृत संपत्ति, 2 प्रशिक्षण प्रोफाइल। एक आकर्षक विज्ञान-फाई आरपीजी विज़ुअल कैनन, पूरी तरह से क्यूरेट किया गया।

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## डाउनस्ट्रीम प्रारूप

`sdlab` डेटासेट का मालिक है। प्रारूप रूपांतरण [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) द्वारा संभाला जाता है: TRL, LLaVA, Qwen2-VL, JSONL, Parquet और अन्य। `repo-dataset` प्रस्तुत करता है; यह कभी भी समावेश का निर्णय नहीं लेता।

## स्थापना

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Node.js 20+ और स्थानीय होस्ट:8188 पर [ComfyUI](https://github.com/comfyanonymous/ComfyUI) की आवश्यकता है।

### इसे ComfyUI के बिना आज़माएं

आप पूर्ण गैर-उत्पादन सतह का पता लगा सकते हैं - निरीक्षण, क्यूरेशन, स्नैपशॉट, विभाजन, निर्यात - बंडल किए गए स्टार फ्रेट प्रोजेक्ट का उपयोग करके, ComfyUI स्थापित किए बिना या किसी भी SDXL भार को डाउनलोड किए बिना।

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` प्रत्येक परियोजना कॉन्फ़िगरेशन (संविधान, लेन, रुब्रिक, शब्दावली) को मान्य करता है और GPU को छुए बिना पात्रता की रिपोर्ट करता है। कोई भी कमांड जो उत्पन्न स्थिति को परिवर्तित करता है, वह पहले प्रभाव का पूर्वावलोकन करने के लिए `--dry-run` स्वीकार करता है।

यदि आप `--project` भूल जाते हैं, तो CLI `projects/` के अंतर्गत पाए जाने वाले पहले प्रोजेक्ट पर वापस चला जाता है और एक चेतावनी प्रिंट करता है - इसे शांत करने के लिए स्पष्ट रूप से `--project` पास करें।

### अवरुद्ध रन को फिर से शुरू करना

लंबे समय तक चलने वाले उत्पादन कार्यों को पूर्ण किए गए कार्य को दोहराए बिना फिर से शुरू किया जा सकता है:

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

दोनों कमांड काम करते हैं क्योंकि प्रत्येक स्लॉट अपनी मैनिफेस्ट प्रविष्टि को परमाणु रूप से लिखता है जैसे ही यह समाप्त होता है - मध्य-रन में दुर्घटना कभी भी आंशिक स्थिति को दूषित नहीं करती है।

## समस्या निवारण

सामान्य विफलता मोड और समाधान:

किसी भी `sdlab generate` / `sdlab run generate` / `sdlab batch generate` पर **`ECONNREFUSED 127.0.0.1:8188`**
ComfyUI चल नहीं रहा है। ComfyUI शुरू करें (`python main.py --listen 127.0.0.1 --port 8188`) और `curl http://127.0.0.1:8188/system_stats` से पुष्टि करें। किसी भिन्न होस्ट/पोर्ट पर इंगित करने के लिए, `COMFY_URL=http://host:port` सेट करें।

**`missing checkpoint` / `LoRA weight not found`**
आपके वर्कफ़्लो प्रोफ़ाइल में एक मॉडल फ़ाइल का नाम है जो ComfyUI के `models/checkpoints/` या `models/loras/` फ़ोल्डर में नहीं है। `projects/<project>/workflows/profiles/<profile>.json` खोलें, `checkpoint` या `lora` फ़ील्ड का पता लगाएं, और या तो संदर्भित भार डाउनलोड करें या इसे किसी ऐसे भार से बदल दें जो आपके पास पहले से है। फिक्स की पुष्टि करने के लिए `sdlab project doctor --project <project>` को फिर से चलाएं।

**`sdlab project doctor` त्रुटियाँ**
डॉक्टर संरचित त्रुटि कोड लौटाता है। सामान्य:
- `E_PROJECT_NOT_FOUND` - परियोजना निर्देशिका `projects/` के अंतर्गत मौजूद नहीं है। वर्तनी की जाँच करें।
- `E_CONFIG_INVALID` - पाँच JSON कॉन्फ़िगरेशन फ़ाइलों में से एक स्कीमा सत्यापन विफल हो गया। `hint` फ़ील्ड खराब फ़ाइल और फ़ील्ड का नाम देता है।
- `E_RECORD_DRIFT` - किसी रिकॉर्ड का कॉन्फ़िगरेशन फ़िंगरप्रिंट अब इसके स्रोत से मेल नहीं खाता है। संकेत के अनुसार फिर से क्यूरेट या पुन: बांधें।

**`No --project specified, falling back to <name>`**
एक नरम चेतावनी। सही परियोजना का चयन करने और चेतावनी को शांत करने के लिए स्पष्ट रूप से `--project <name>` पास करें।

**पेंटरली / VRAM आउट-ऑफ़-मेमोरी मुद्दे**
पेंटरली डेनोइज़ ट्यूनिंग नोट्स के लिए `docs/internal/HANDOFF.md` देखें। संक्षेप में: डेनोइज़ शक्ति को कम करें, बैच आकार को कम करें या अपने वर्कफ़्लो प्रोफ़ाइल में एक छोटे चेकपॉइंट पर स्विच करें।

**बग की रिपोर्ट करना**
https://github.com/mcp-tool-shop-org/style-dataset-lab/issues पर अपनी sdlab संस्करण (`sdlab --version`), Node संस्करण (`node -v`), पूर्ण कमांड और संरचित त्रुटि आउटपुट के साथ एक समस्या फ़ाइल करें। बग-रिपोर्ट टेम्पलेट फ़ील्ड को पहले से भर देता है।

## सुरक्षा

केवल स्थानीय। कोई टेलीमेट्री नहीं, कोई एनालिटिक्स नहीं, कोई बाहरी अनुरोध नहीं। छवियां आपके GPU और फ़ाइल सिस्टम पर रहती हैं।

## लाइसेंस

MIT

---

<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> द्वारा निर्मित
