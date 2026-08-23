# Fetch eye-study A and C. URLs signed over the ENTIRE query string -- byte-for-byte.
$ErrorActionPreference = 'Stop'
$dest = 'E:\AI\style-dataset-lab\projects\ferrochrome\outputs\candidates\eye-study'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$items = @(
  @{ name = 'eye_a_bezel_ring.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/af8e00308b00a4ac0b7a5aa0a88e77084e63134cc0de5f39d334f11184fcbf39.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T001920Z&X-Goog-Expires=21599&X-Goog-Signature=27f3d31b46f31ceca00bc99195e043165f85eed1e71d8e492a4210cb401afc18bc618349b1165f283a2d2e2a8411e6300b6c6feb9363122a6bb36c4666b6d26b705664818041f10215ea8e31474b3878be1700cf5bef0eaf70044d30aa94a183dc894d735619b1a642f8c37f80ed5c121063b405591b6dbb3caf9ac0947a75aeb8da749eb28de304897571ae70a616a11f55c3a6578ae45a65989451b39bac782fdd272856ae742418c802242105c2257c9f710026ccb16b095531b7188ec42bcc75b5f195cd89e4a767cffc1f393694f23744d2274cf4fb76cb55c112fa472e1121e0380a97dc573f3870476707b1ca313d05132fff93e2a330530b19009dae&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_eye_a_00001_.png%22' }
  @{ name = 'eye_c_counterbored.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/af5b7beab806fce6ad8cdd6ce047599a91b09bb3af9feba94ce98ad7c508eed8.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T001920Z&X-Goog-Expires=21599&X-Goog-Signature=6918b6f2a49881f5ef65426eb5b47cccf2816b46b672111d1258ef34bbeee04f4ee569b4bc1ea848742cb1ea6c2f5d8586fc45c00f55320d879001d073f65cf75cb3ee8eabe67b998b964c789c8c9ee48cc782b2001dc1dc14b02773969cf39f15db20304f44706a525daeaff3925b3b586f8881f266172ce3c638883a502b415fadfb43ff81a5676bc69888ec9c83e59ba18f04a3042bb3ab39c823d4f92e988af72cd298992028c3f59574115ebe85795d06f5f2c1ebc807e0abe4c7a5565caba095caea54b57eb3dbecf1385288bfff9c01ac57b5ec20f0c5cfdf98b27ac453c3cf6fd07d76df215baf8a78e2d7b7681fec4496da76698bca1d40abb7f171&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_eye_c_00001_.png%22' }
)

foreach ($i in $items) {
  $out = Join-Path $dest $i.name
  curl.exe -L --fail-with-body --retry 3 --retry-all-errors --connect-timeout 20 -s -o $out -- $i.url
  if ($LASTEXITCODE -ne 0) { throw "download failed for $($i.name) (curl exit $LASTEXITCODE)" }
  Write-Output ("{0}  {1:N0} bytes" -f $i.name, (Get-Item $out).Length)
}
