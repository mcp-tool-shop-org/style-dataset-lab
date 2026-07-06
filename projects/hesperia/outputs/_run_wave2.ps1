$ErrorActionPreference = 'Continue'
$py = 'E:\AI-Models\ComfyUI_windows_portable\python_embeded\python.exe'
$script = 'E:\AI\style-dataset-lab\scripts\qwen_generate.py'
$out = 'E:\AI\style-dataset-lab\projects\hesperia\outputs\npcs-wave-2'
& $py $script --wave 'E:\AI\style-dataset-lab\projects\hesperia\inputs\prompts\_npcs-wave-2a.json' --out $out
& $py $script --wave 'E:\AI\style-dataset-lab\projects\hesperia\inputs\prompts\_npcs-wave-2b.json' --out $out
'WAVE2_COMPLETE' | Out-File "$out\_wave2_done.flag"
