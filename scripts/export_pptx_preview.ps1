# Экспорт слайдов презентации в PNG (PowerPoint COM).
# Использование: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/export_pptx_preview.ps1
$ErrorActionPreference = "Stop"
$root = "c:\Users\Yaroslav\Desktop\PROJECTS\EVRAZ_AGENT"
$pptx = Join-Path $root "data\EVRAZ_Agent_defense.pptx"
$outDir = Join-Path $root "data\_defense_preview"

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

# Удаляем старые превью (латинские, кириллические и битые копии).
Get-ChildItem $outDir -File | Where-Object { $_.Name -like "slide_*.png" -or $_.Name -like "Слайд*.PNG" -or $_.Name -like "*.PNG" } | Remove-Item -Force

$ppt = New-Object -ComObject PowerPoint.Application
try {
    $pres = $ppt.Presentations.Open($pptx, $true, $false, $false)
    $count = $pres.Slides.Count
    for ($i = 1; $i -le $count; $i++) {
        $file = Join-Path $outDir ("slide_" + $i.ToString("00") + ".png")
        $pres.Slides.Item($i).Export($file, "PNG", 1600, 900)
    }
    Write-Output ("EXPORTED " + $count + " slides -> " + $outDir)
    $pres.Close()
} finally {
    $ppt.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
