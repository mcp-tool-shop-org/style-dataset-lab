$ErrorActionPreference = 'Continue'
$py = 'E:\AI-Models\ComfyUI_windows_portable\python_embeded\python.exe'
$script = 'E:\AI\style-dataset-lab\scripts\qwen_generate.py'
$out = 'E:\AI\style-dataset-lab\projects\hesperia\outputs\main-cast'
& $py $script --wave 'E:\AI\style-dataset-lab\projects\hesperia\inputs\prompts\_cast-androids.json' --out $out
& $py $script --wave 'E:\AI\style-dataset-lab\projects\hesperia\inputs\prompts\_cast-welded-human.json' --out $out
'CAST_COMPLETE' | Out-File "$out\_cast_done.flag"
