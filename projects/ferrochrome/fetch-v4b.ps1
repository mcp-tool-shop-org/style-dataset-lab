# Fetch the remaining v4 roles. URLs signed over the ENTIRE query string -- byte-for-byte.
$ErrorActionPreference = 'Stop'
$dest = 'E:\AI\style-dataset-lab\projects\ferrochrome\outputs\candidates\roles-v4'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$items = @(
  @{ name = 'warehouse.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/300116b64c06da9c6995172de7ac446df3e7b6e6c37d2b49d505809714ef00a5.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003546Z&X-Goog-Expires=21599&X-Goog-Signature=5dead78c3a016cf01508909ac1212491ccec27d6024d1d9f7c80367e60417f112c4661c5fa9c50ccbfae8804393e245b13d461bfb251b726a86f3fd33c7b2c4b469bd2c2554976f84db666e1526979fce2b7eba6c225acacab02510831b3c2a0bb7cec077e5f3f9a32a5947962dc54ef46f1da81e9081a2494a571cecbf54562e81bad2f7e9ff7b3b4ff0781e70c17e0ec42bb32b3d4c167cec7fc317c91f77ade603ad4939410d98ea523bda82810f471f57d4d44128b301d34d5a01a5185ad183affedb51feb636f4fb98089689987b030fd9f678390873baa45fec2e41facbd05aff50d3f7570a9fc3b9f58bdf0991e489d32aa1ccd8d1bed46ad14697563&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_warehouse_00001.png%22' }
  @{ name = 'maintenance.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/08d26f531c1849823d16083f16fde7469f20002386cb51280ebbfe6a32bfdaa2.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003546Z&X-Goog-Expires=21599&X-Goog-Signature=3742d98933121c1f8c80e8e1d0a396b167fe3fa7f49cce7a62d4b90914f6baa1eb12bd4e5bd4dba06749905bd16f6a0b2044aa6b75d94007b01ce506715797f970bcaad61dc0b2a04fa114a0e19d4c4175baaf55ea2c75a4e58fcd2c2bc9357e804d8230d258ac285947924aaa63225d4e5ef4f9aaa56f63d22879f5f71fc5f0b0466ea3149887a1273a30afc6ae2c7a519d793a2658f82a258c47027ee66ee9741159a98d71b6383505b7ac5676d493427d00a7e534c911eaac9ba64509c0fd1183f4a27b474c56eea09f0e9a287dabf330efdc1e99772d371aede4c9638f74b8c0704c2142f2b09e32c15ce4804d378393a5fd0f60ecdb5cef2dcd4f7b031b&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_maintenance_00001.png%22' }
  @{ name = 'agricultural.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/ba9ed355ebf04e41310fc53c06bc2df07fec23bbe8e13b8927cdc07269aadc86.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T003546Z&X-Goog-Expires=21599&X-Goog-Signature=93e99e21ba63e03024a0900d553222299a9f3f18a94de3197f32557e4fe7a1b7adc2400099d9217b56304dd407a6318f7d406251b3c5a1ecc48ae3ca89566e1804ce15e5d326fee88fd080f1ef637d4d66a0c244e5f58425b0af07c6b221a91062e5d160d06a14fcdf840f3f00055693af977911bf84e4c3bb92e14b2dedab37d503ed4e29814a119b3b133fb40e80e39c62659167c3284fc1bab71a28229ea855132775c34be7b269e1ee8c563d57e3c7b82a1c9c53677383409f16cc1c7d53539ace6d3446150379d8291a9cbc2a2fdc0e246af71542ff25f334c8109d8e9b825a4f542c6b2a551e8b30e39e3b58d5e8606e1e99f47f4a557ce570dbdba130&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_v4_agricultural_00001.png%22' }
)

foreach ($i in $items) {
  $out = Join-Path $dest $i.name
  curl.exe -L --fail-with-body --retry 3 --retry-all-errors --connect-timeout 20 -s -o $out -- $i.url
  if ($LASTEXITCODE -ne 0) { throw "download failed for $($i.name) (curl exit $LASTEXITCODE)" }
  Write-Output ("{0}  {1:N0} bytes" -f $i.name, (Get-Item $out).Length)
}
