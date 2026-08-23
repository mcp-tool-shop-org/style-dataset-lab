# Fetch the v4 role set. URLs signed over the ENTIRE query string -- byte-for-byte.
$ErrorActionPreference = 'Stop'
$dest = 'E:\AI\style-dataset-lab\projects\ferrochrome\outputs\candidates\roles-v4'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$items = @(
  @{ name = 'companion.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/92c4f17570d6be506bf2cb5612e3b46607da9015c073355b2267457f95f23d4d.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003220Z&X-Goog-Expires=21599&X-Goog-Signature=ac13cf99e003853cfc8cad72c7db1b4568bc5bc7429adc5801d051be07a70c0e19ec05e4e342fa035bbc955a1bafe2cf77bc734abb2b036f00a3b9d00e668d2d78f9224687a40c06b3b931e88e6efb312c43cd1f0bd889585cade406a3d72cb5ac358d5c5688d2bcbecb51b652d4adc254ba88aa40a416cd0ef737e9f88ac4b61cc44b878ee33cc73bc7d3bf3ed01fd96f27783ac88088d35c0a71dede1f4aeaf90fc3efeeff4045e67529d4049531fcef90e51463f643194f4c9d081bcdf9d388ebedcb7b85cf31c042a442fd1625399c70b8ec8640d0cc2e8434ab347ee8144bf25126e9781ec7a067f2122a72bb601a9591c05787352aa7ad29ff0f000c92&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_companion_00001.png%22' }
  @{ name = 'security.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/d8de170174c60795021b0399ae2080b8d7d37d740a5deebb4f5344af730be982.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003220Z&X-Goog-Expires=21599&X-Goog-Signature=451889694ecbb6d00a7686c982153055bb0a72a08a46c0de114ff0d06b3cb3d48a600eda0bd083c1d7e40392a6fd0b5559c1bb062788e873c000336f526d4ee6883195bc229afd5f40f4c7ed0a59b5c29bad2c5a2a9e0dfe7578851616de1e6d8ff452dda4b0772e4febf8ab40d9f2c31c0529d171b8f6b598020b0bef3ad880c4dd4ef88087f4433c5b6482f01e73847b9ebb57d0d07d3852702d49161e76607f8d07052c7e862be581b44664dbc3c4d9294ae9d1b0eff0b3de77e63fa5d506f1ab20486ff26d6a4bca659f526319a00a9296b98f7c3b9694c0a2e82ceeb790e66399161a82ee769736540391c206a792bc3fc413e708823dc731a8b238989a&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_security_00001.png%22' }
  @{ name = 'medical.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/f8d60059abe85a1562027b8e437ca31c578a5e3c0f962137e330e44483cf6ca0.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003220Z&X-Goog-Expires=21599&X-Goog-Signature=a5513c038e21eb9c245cbcc014d3b3404e6df089602f6a71580ff3c5f994378440ea6bb6a226c4ea9bce43488d706bdabb00ff3b75a8c62145aa1954aa9605d67e6dcfb0229338cf25160db1b14ec03e38a7e3ea88e19f4fb76364b97e64cf4e829ddf187955470d98da73bbad633c56a464c6ac9aa09c3608ecd6833c10e63abeb08ff5e350e3f7333ed00dfc5f08902cc994cf4decf0e3e568b8f1b7af33d6ef626f6b627a82c0ec21ef445387026bf808f5603e58e91452a858f9544f540acb9f44377314296272a675585853ca2eed4be12addb9ae3c8b19ae757a36322f041b2a2f846af88c47f38ecddec589b4227a36a96180f30fce2eef2c24d2c4fb&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_medical_00001.png%22' }
)

foreach ($i in $items) {
  $out = Join-Path $dest $i.name
  curl.exe -L --fail-with-body --retry 3 --retry-all-errors --connect-timeout 20 -s -o $out -- $i.url
  if ($LASTEXITCODE -ne 0) { throw "download failed for $($i.name) (curl exit $LASTEXITCODE)" }
  Write-Output ("{0}  {1:N0} bytes" -f $i.name, (Get-Item $out).Length)
}
