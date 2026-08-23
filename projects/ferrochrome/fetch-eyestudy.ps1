# Fetch the eye-study batch. URLs are signed over the ENTIRE query string --
# copy them byte-for-byte, never strip response-content-disposition.
$ErrorActionPreference = 'Stop'
$dest = 'E:\AI\style-dataset-lab\projects\ferrochrome\outputs\candidates\eye-study'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$items = @(
  @{ name = 'eye_b_deep_socket.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/874393cbd49ce2ac024ae963058022c8eecb83d5f2e704ba8494e8ec6fc3d744.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T001720Z&X-Goog-Expires=21599&X-Goog-Signature=55855c7f54b2cafb118e3a29b2601eeb98d519ec356b82c87929edcdb634d91bf33baa45972067d576801dfcebe20cd30086cf774539d32457828054f933299022a4e3ba02e1f973d115010ff881cd368f086b4dd18a31f213e1eb4676971fb050f8cd323a0dea9c50220a6af5a5f55fdaa57b49c9eec81b75aa1df04f70a62927315b99eee6c401e40b865a49fcf15c6c1671c60837edcc4ae1a1336385c373bab22e3bc4d654ef5f0f8cfeeb4024a7d63c9e95b5501c38d57c61ee0ba010f6868b23e777de7946194a30322610b20f0e928f24e95d340191764ece1a5465600bd79950befb3c1f073ef5e962c84c65a3869d6d96f1fe768d2ea8ac5c160108&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_eye_b_00001_.png%22' }
  @{ name = 'eye_d_control_flush.png'
     url  = 'https://storage.googleapis.com/comfy-cloud-assets/0c71befcee56e7bea81a11767fdae58089924f9512e92921d0930f23874e3b70.png?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=comfy-cloud-prod-workload-sa%40comfy-cloud-prod.iam.gserviceaccount.com%2F20260823%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260823T001720Z&X-Goog-Expires=21599&X-Goog-Signature=91a5a53a1f6942b8e5894e9a039bbc3b2fb8a80c083a04ed499367395459d09a4b6eb6a78d4e498be6f07181d28715edb4725c9825b405c9a19a7e87557d78cb380ededc7006db8cd33fc229e178f716ebfff576220c5fabc7ab723c99ce24947e511fae49423772da29336db4ad0b7fae076d46d4097db1f3ae29eb8f0d18469e9c464f384b9ded5c2b578167dc82dde62b33198bae244efbdc9356774137d13a65ac4c02c556c1b3f271c08d846308ff92acf1193449251d0c4c9e39a17b231ae22b392fe14b795e25881504014bd8b24768b8cc0727fc67cd4595dcc45f60779646b17d2f0574ba92224758566e4ce1e43f1b7435fb437b9059f5b1db2fc9&X-Goog-SignedHeaders=host&response-content-disposition=attachment%3B%20filename%3D%22ferrochrome_eye_d_00001_.png%22' }
)

foreach ($i in $items) {
  $out = Join-Path $dest $i.name
  curl.exe -L --fail-with-body --retry 3 --retry-all-errors --connect-timeout 20 -s -o $out -- $i.url
  if ($LASTEXITCODE -ne 0) { throw "download failed for $($i.name) (curl exit $LASTEXITCODE)" }
  $size = (Get-Item $out).Length
  Write-Output ("{0}  {1:N0} bytes" -f $i.name, $size)
}
