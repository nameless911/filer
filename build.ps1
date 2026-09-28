# exe を dist\ に作り直し、フォルダ版を zip にする。
#   .\build.ps1                    ビルドだけ
#   .\build.ps1 -Release v0.2.0    ビルドして、タグを付けて push し、GitHub の Releases に出す
#
# dist\ の exe が起動しっぱなしなら、ファイラーに「状態を保存して終わって」と頼んでから
# ビルドし、終わったら同じ窓とタブで立ち上げ直す（窓口は control.py）。
#
# このファイルは UTF-8（BOM 付き）で保存すること。BOM が無いと Windows PowerShell 5.1 が文字化けする。
param(
    [string]$Release = "",
    [string]$Notes = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- ツッコミ（ウチ＝ちっちゃい芦毛の関西娘のノリ） ---------------------------
$Nags = @(
    "ちょお待ちぃ！ Filer 開けっぱなしでビルドしよ思たん？ exe 掴んだままやと上書きできへんやろがい！ ウチがいっぺん閉じたるわ",
    "アンタさあ、起動しっぱなしやで！ 走りながら蹄鉄打ち替えられへんのと一緒や。ちょっと止めるで！",
    "おったおった、まだ動いとる Filer！ 片付けてからビルドや。窓もタブもウチが覚えといたるから安心しぃ",
    "なんでやねん！ 開いたまんまやんか！ しゃーないなぁ、保存させてから一旦閉じるで"
)
$Done = @(
    "建て直したったで！ さっきの窓もタブもそのまま戻しといたからな",
    "よっしゃ、ピッカピカの新しい Filer や！ タブも元どおりやで、確かめてみぃ",
    "はい一丁上がり！ 閉じる前の状態で起こしといたで。ウチ、仕事早いやろ？"
)
$Busy = "今それどころちゃうみたいやで。{0} …終わったらもっかい呼んでな"
$Stuck = "返事あらへん…コピーか何かの途中ちゃう？ 無理に閉じたらファイル欠けるかもしれんから、ビルドはやめとくわ"

function Say([string]$msg) { Write-Host "[Filer] $msg" -ForegroundColor Yellow }

# --- 起動しっぱなしの exe を探す ------------------------------------------------
$Targets = @(
    (Join-Path $PSScriptRoot "dist\Filer\Filer.exe"),
    (Join-Path $PSScriptRoot "dist\Filer-portable.exe")
)

function Get-Running {
    # 1 個版の exe は起動用の親と本体の子の 2 段になるので、同じ exe の分をまとめて返す
    Get-CimInstance Win32_Process -Filter "Name='Filer.exe' or Name='Filer-portable.exe'" |
        Where-Object { $_.ExecutablePath -and ($Targets -contains $_.ExecutablePath) }
}

function Request-Quit([int]$ProcessId, [string]$StatePath) {
    # 戻り値: "ok" / "busy <理由>" / "none"（窓口が無い） / "stuck"（返事が無い）
    $pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "Filer-$ProcessId", [System.IO.Pipes.PipeDirection]::InOut)
    try {
        try { $pipe.Connect(500) } catch { return "none" }
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        $writer = New-Object System.IO.StreamWriter($pipe, $utf8)
        $writer.AutoFlush = $true
        $writer.WriteLine("quit-for-restart $StatePath")
        $reader = New-Object System.IO.StreamReader($pipe, $utf8)
        $task = $reader.ReadLineAsync()
        if (-not $task.Wait(10000)) { return "stuck" }
        return [string]$task.Result
    } finally {
        $pipe.Dispose()
    }
}

function Stop-Running {
    # 閉じた exe ごとに、立ち上げ直すための情報を返す
    $running = @(Get-Running)
    if (-not $running) { return @() }
    Say ($Nags | Get-Random)

    $relaunch = @()
    foreach ($group in ($running | Group-Object ExecutablePath)) {
        $exe = $group.Name
        $state = Join-Path $env:TEMP ("filer-restart-" + [guid]::NewGuid().ToString("N") + ".json")
        $answered = $false
        foreach ($p in $group.Group) {
            $reply = Request-Quit $p.ProcessId $state
            if ($reply -eq "none") { continue }
            $answered = $true
            if ($reply -eq "ok") { $relaunch += @{ Exe = $exe; State = $state }; break }
            if ($reply -eq "stuck") { Say $Stuck; exit 1 }
            Say ($Busy -f ($reply -replace '^busy\s*', '')); exit 1
        }
        if (-not $answered) {
            # 窓口を持たない古い exe。窓を閉じる指示だけ出す（状態はいつもの保存先に残る）
            foreach ($p in $group.Group) { (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue).CloseMainWindow() | Out-Null }
            $relaunch += @{ Exe = $exe; State = $null }
        }
    }

    # 本当に終わるまで待つ。強制終了はしない
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Running) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (Get-Running) { Say $Stuck; exit 1 }
    return $relaunch
}

# --- 本体 -----------------------------------------------------------------------
$pyi = Join-Path $PSScriptRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyi)) {
    throw "PyInstaller が見つかりません。.venv\Scripts\python.exe -m pip install -r requirements-dev.txt を実行してください"
}

if ($Release) {
    if (git status --porcelain) { throw "コミットしていない変更があります。コミットしてから出してください" }
    if (git tag --list $Release) { throw "タグ $Release はもうあります" }
}

$relaunch = @(Stop-Running)

Write-Host "== build $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') @ $(git rev-parse --short HEAD)"
try {
    & $pyi --noconfirm --log-level WARN Filer.spec
    if ($LASTEXITCODE) { throw "Filer.spec のビルドに失敗しました" }
    & $pyi --noconfirm --log-level WARN Filer-portable.spec
    if ($LASTEXITCODE) { throw "Filer-portable.spec のビルドに失敗しました" }
    Compress-Archive -Path dist\Filer -DestinationPath dist\Filer.zip -Force
    Write-Host "== done: dist\Filer-portable.exe, dist\Filer.zip, dist\Filer\Filer.exe"
} finally {
    # ビルドが失敗しても、閉じた分は立ち上げ直す（古い exe が残っていればそれで）
    foreach ($r in $relaunch) {
        if (-not (Test-Path $r.Exe)) { continue }
        try {
            if ($r.State) { Start-Process $r.Exe -ArgumentList "--restore", "`"$($r.State)`"" -ErrorAction Stop }
            else { Start-Process $r.Exe -ErrorAction Stop }
        } catch {
            # Smart App Control などに止められたとき。状態ファイルは残すので、後から手で復元できる
            Say ("あかん、Windows に起動止められてもうた… {0}" -f $_.Exception.Message)
            if ($r.State) { Say "状態は $($r.State) に残しといたで。「$($r.Exe) --restore そのパス」で戻せるからな" }
            $r.Failed = $true
        }
    }
    if ($relaunch | Where-Object { -not $_.Failed }) { Say ($Done | Get-Random) }
}

if ($Release) {
    $gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
    if (-not $gh) { $gh = "C:\Program Files\GitHub CLI\gh.exe" }
    if (-not $Notes) { $Notes = "Filer $Release" }
    git tag $Release
    git push origin HEAD $Release
    & $gh release create $Release dist\Filer-portable.exe dist\Filer.zip --title "Filer $Release" --notes $Notes
    if ($LASTEXITCODE) { throw "gh release create に失敗しました" }
}
