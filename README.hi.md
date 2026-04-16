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

अनुमोदित दृश्य सामग्री को संस्करणों में विभाजित करें, समीक्षा के आधार पर डेटासेट, उप-समूह (स्प्लिट्स), निर्यात पैकेज और मूल्यांकन पैकेजों में व्यवस्थित करें।

## यह क्या है

एक **दृश्य सामग्री और डेटासेट निर्माण प्रक्रिया**. अपनी परियोजना कैसी दिखेगी, यह परिभाषित करें। संविधान के नियमों के अनुसार सामग्री का चयन करें। ऐसे डेटासेट पैकेज तैयार करें जो दोहराए जा सकें और जिनमें डेटा सुरक्षा बनी रहे। भविष्य में मॉडल की जांच के लिए मूल्यांकन पैकेज बनाएं।

यह पाइपलाइन चार प्रकार के आउटपुट (परिणाम) उत्पन्न करता है:

| पुरातत्विक वस्तु। | यह क्या है। |
|----------|-----------|
| **Snapshot** | चयनित अभिलेखों की एक "फ्रीज" की गई सूची, जिसमें केवल योग्य अभिलेख शामिल हैं। प्रत्येक अभिलेख को शामिल करने का एक स्पष्ट और विशिष्ट कारण दर्ज किया गया है। |
| **Split** | रिसाव-रोधी ट्रेन/वैल्यू/टेस्ट विभाजन। रिकॉर्ड हमेशा एक ही समूह में आते हैं, जो एक विषय परिवार से संबंधित होते हैं। |
| **Export package** | स्वतंत्र डेटासेट: इसमें मैनिफेस्ट (manifest), मेटाडेटा (metadata), चित्र, डेटासेट के विभिन्न भाग, डेटासेट कार्ड और चेकसम (checksums) शामिल हैं। |
| **Eval pack** | कैनन (Canon) के मानकों के अनुरूप सत्यापन कार्य: लेन कवरेज, निषिद्ध विचलन, एंकर/गोल्ड, विषय की निरंतरता। |

पाइपलाइन में मौजूद प्रत्येक संपत्ति में तीन चीजें शामिल होती हैं:

1. **उत्पत्ति का विवरण** -- पूरी पीढ़ी का इतिहास (चेकपॉइंट, लोरा, सीड, सैंपलर, सीएफजी, समय)।
2. **मानकों का अनुपालन** -- यह निर्धारित करता है कि यह संपत्ति किस मानक को पूरा करती है, विफल होती है, या आंशिक रूप से पूरा करती है।
3. **गुणवत्ता मूल्यांकन** -- स्वीकृत/अस्वीकृत/सीमांत श्रेणी में, प्रत्येक पहलू के लिए अलग-अलग स्कोर के साथ।

यह काम गेम आर्ट, कैरेक्टर डिजाइन, जीव (क्रिएचर) डिजाइन, आर्किटेक्चर, वाहन/मैक अवधारणाओं, और किसी भी ऐसे क्षेत्र में किया जाता है जहाँ विज़ुअल उत्पादन को सटीक और अनुरूप बनाए रखने की आवश्यकता होती है।

## शुरुआत कैसे करें।

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

उपलब्ध डोमेन: `गेम-आर्ट`, `कैरेक्टर-डिजाइन`, `क्रिएचर-डिजाइन`, `आर्किटेक्चर`, `वाहन-मैकेनिक्स`, या `सामान्य।

## सीएलआई (CLI) - कमांड लाइन इंटरफेस

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

सभी कमांड्स `--project <नाम>` विकल्प को स्वीकार करते हैं (डिफ़ॉल्ट: `star-freight`)।

## परियोजना मॉडल।

प्रत्येक परियोजना `projects/` नामक एक स्वतंत्र फ़ोल्डर में स्थित होती है, और इसमें अपना विशिष्ट नियम (canon), कॉन्फ़िगरेशन (config) और डेटा होता है।

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

## पाइपलाइन।

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **परिभाषित करें:** अपनी शैली का संविधान (स्टाइल कॉन्स्टिट्यूशन) लिखें और मूल्यांकन मानदंड (रिव्यू रूब्रिक) तैयार करें।
2. **उत्पन्न करें:** कॉमफीयूआई (ComfyUI) पूर्ण जानकारी के साथ संभावित विकल्प (कैंडिडेट्स) उत्पन्न करता है।
3. **चयन करें:** प्रत्येक आयाम के लिए स्कोर और विफलता के तरीकों के साथ, विकल्पों को स्वीकृत या अस्वीकृत करें।
4. **जोड़ें:** प्रत्येक संसाधन को संविधान के नियमों से जोड़ें और पास/फेल/आंशिक परिणाम दर्ज करें।
5. **स्नैपशॉट लें:** योग्य रिकॉर्ड को एक निश्चित, विशिष्ट पहचान (फिंगरप्रिंट) वाले संग्रह में स्थिर करें।
6. **विभाजित करें:** डेटा को प्रशिक्षण (ट्रेन), मूल्यांकन (वैल) और परीक्षण (टेस्ट) सेट में विभाजित करें, जिसमें विषय का अलगाव और डेटा संतुलन शामिल हो।
7. **निर्यात करें:** एक आत्मनिर्भर पैकेज बनाएं जिसमें घोषणापत्र (मैनिफेस्ट), मेटाडेटा, चित्र और चेकसम शामिल हों।
8. **मूल्यांकन करें:** मॉडल की पुष्टि के लिए, "कैनन" (परिभाषित मानकों) के अनुरूप परीक्षण उपकरण उत्पन्न करें।

"डाउनस्ट्रीम फॉर्मेट में रूपांतरण (जैसे TRL, LLaVA, Parquet, आदि) [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) द्वारा किया जाता है। `sdlab` डेटासेट की वास्तविक जानकारी रखता है, जबकि `repo-dataset` इसे विशिष्ट फॉर्मेट में परिवर्तित करता है।"

## डोमेन टेम्प्लेट।

प्रत्येक डोमेन टेम्पलेट में लेन (कार्य) की परिभाषाएं, नियमों का संग्रह, मूल्यांकन मापदंड और शब्दावली शामिल होती है, जो उस विशेष उत्पादन प्रक्रिया के लिए डिज़ाइन की गई हैं।

| डोमेन। | सड़कें। | मुख्य चिंताएं। |
|--------|-------|-------------|
| **game-art** | चरित्र, वातावरण, वस्तु, यूआई (उपयोगकर्ता इंटरफ़ेस), जहाज, आंतरिक भाग, उपकरण। | गेमप्ले के पैमाने पर सिल्हूट का विवरण, गुटों के बीच अंतर, और समय के साथ होने वाली टूट-फूट या बदलाव। |
| **character-design** | पोर्ट्रेट (चित्र), पूरे शरीर का चित्रण, विभिन्न कोणों से चित्रण, भावों का चित्रण, गतिशील मुद्रा में चित्रण। | अनुपात की सटीकता, वेशभूषा की तर्कसंगतता, व्यक्तित्व का चित्रण, हाव-भाव की स्पष्टता। |
| **creature-design** | अवधारणा, वर्तनी संबंधी, विस्तृत अध्ययन, क्रिया, माप का संदर्भ, आवास। | शारीरिक संरचना की संभाव्यता, विकासवादी तर्क, और आकृति की विशिष्टता। |
| **architecture** | बाहरी भाग, आंतरिक भाग, सड़क का दृश्य, संरचनात्मक विवरण, खंडहर, परिदृश्य। | संरचनात्मक संभाव्यता, सामग्री की सुसंगति, दृष्टिकोण, युग की अनुरूपता। |
| **vehicle-mech** | बाहरी भाग, कॉकपिट, घटक, आरेख, सिल्हूट शीट, क्षति का प्रकार। | यांत्रिक तर्क, कार्यात्मक डिज़ाइन भाषा, पहुंच बिंदु, क्षति विवरण। |

## डेटासेट का निर्माण।

पूरे डेटासेट की संरचना: स्नैपशॉट, विभाजन, निर्यात, मूल्यांकन।

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

**स्नैपशॉट** योग्य रिकॉर्डों के एक निश्चित चयन को स्थिर करते हैं। प्रत्येक शामिल रिकॉर्ड के लिए एक कारण दर्ज किया गया है। कॉन्फ़िगरेशन फ़िंगरप्रिंट पुनरुत्पादकता सुनिश्चित करते हैं।

**विभाजन** रिकॉर्डों को प्रशिक्षण/मान्यकरण/परीक्षण भागों में आवंटित करते हैं, जिसमें विषय अलगाव (कोई भी विषय परिवार एक से अधिक विभाजनों में नहीं दिखाई देता) और लेन-संतुलित वितरण शामिल है। सीडेड PRNG समान सीड से समान परिणाम सुनिश्चित करता है।

**निर्यात पैकेज** आत्मनिर्भर होते हैं: मैनिफेस्ट, metadata.jsonl, छवियां (सिंबोलिंक या कॉपी की गई), विभाजन, डेटासेट कार्ड (मार्कडाउन + JSON), और BSD-स्वरूप चेकसम। डेटासेट को खरोंच से फिर से बनाने के लिए आवश्यक सब कुछ।

**मूल्यांकन पैकेज** मानक-जागरूक परीक्षण उपकरण हैं जिनमें चार कार्य प्रकार शामिल हैं: लेन कवरेज, निषिद्ध विचलन, एंकर/गोल्ड, और विषय निरंतरता। वे यह साबित करते हैं कि डेटासेट संरचना भविष्य के मॉडल मूल्यांकन को बढ़ावा दे रही है, केवल फ़ाइलें जमा नहीं कर रही है।

`repo-dataset` (https://github.com/mcp-tool-shop-org/repo-dataset) के माध्यम से अन्य प्रारूपों में निर्यात करें (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, और अन्य)। `repo-dataset` प्रारूप रूपांतरण को संभालता है; `sdlab` डेटासेट की सत्यता का स्वामी है।

## स्टार फ्रेट उदाहरण।

एक पूर्ण, कार्यशील उदाहरण के लिए रिपॉजिटरी को क्लोन करें: 1,182 रिकॉर्ड, 28 प्रॉम्प्ट वेव, 5 गुट, 7 लेन, 24 संविधान नियम, और एक कठोर विज्ञान-फाई आरपीजी से 892 स्वीकृत संपत्तियां।

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

## v1.x से माइग्रेट करना।

v2.0 में `games/` को `projects/` और `--game` को `--project` में बदल दिया गया है:

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## सुरक्षा मॉडल

**केवल स्थानीय।** `localhost:8188` पर ComfyUI से संवाद करता है। कोई टेलीमेट्री नहीं, कोई विश्लेषण नहीं, कोई बाहरी अनुरोध नहीं। छवियां आपके GPU और फ़ाइल सिस्टम पर ही रहती हैं।

## आवश्यकताएं

- `localhost:8188` पर चलने वाला [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo चेकपॉइंट + ClassipeintXL LoRA
- Node.js 20+
- प्रशिक्षण के लिए निर्यात के लिए [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset)

## लाइसेंस

MIT

---

<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> द्वारा निर्मित।
