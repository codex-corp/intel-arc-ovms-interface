#Requires -Version 5.1
param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("status","list","switch","rollback","pull","configure","enable","disable")]
    [string]$Command,
    [Parameter(Position=1)][string]$Model,
    [string]$Path,
    [string]$Name,
    [string]$Task = "text_generation",
    [string]$Device = "GPU",
    [int]$CacheSize = 2,
    [int]$MaxNumSeqs = 2,
    [int]$Timeout = 180,
    [switch]$NoWait,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Python = Join-Path $ScriptDir ".venv\\Scripts\\python.exe"
if (-not (Test-Path $Python)) { throw "Python venv missing. Run .\\install_all.ps1 first." }
$argsList = @((Join-Path $ScriptDir "tools\\model_manager\\manage_models.py"), "--root", $ScriptDir, $Command)
switch ($Command) {
  "switch" { if (-not $Model) { throw "switch requires a model" }; $argsList += $Model; if ($Path) {$argsList += @("--path",$Path)}; $argsList += @("--timeout","$Timeout"); if($NoWait){$argsList += "--no-wait"}; if($DryRun){$argsList += "--dry-run"} }
  "pull" { if (-not $Model) { throw "pull requires a Hugging Face source" }; $argsList += @($Model,"--task",$Task,"--device",$Device,"--cache-size","$CacheSize","--max-num-seqs","$MaxNumSeqs"); if($Name){$argsList += @("--name",$Name)} }
  "configure" { if (-not $Path) { throw "configure requires -Path" }; $argsList += @($Path,"--task",$Task,"--device",$Device,"--cache-size","$CacheSize","--max-num-seqs","$MaxNumSeqs"); if($Name){$argsList += @("--name",$Name)} }
  "enable" { if (-not $Model) { throw "enable requires a model" }; $argsList += $Model; if($Path){$argsList += @("--path",$Path)} }
  "disable" { if (-not $Model) { throw "disable requires a model" }; $argsList += $Model }
}
& $Python @argsList
exit $LASTEXITCODE
