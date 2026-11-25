param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('AgentCase','ResumeSession','ExecuteCase','Discover')]
  [string]$Mode,
  [string]$CaseFolder,
  [string]$OutputPath,
  [switch]$RunDraft
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$src=Join-Path $root 'src'
$env:PYTHONPATH=$src + [IO.Path]::PathSeparator + $env:PYTHONPATH
if($RunDraft -and $Mode -notin @('AgentCase','ExecuteCase')){
  throw 'RunDraft requires AgentCase or ExecuteCase.'
}
if($Mode -ne 'Discover' -and [string]::IsNullOrWhiteSpace($CaseFolder)){
  throw 'An existing private case folder or Execution_Case.json is required.'
}
switch($Mode){
  'AgentCase' {
    $arguments=@('-3.11','-m','aihawk.academic_agent',$CaseFolder)
    if($RunDraft){$arguments+='--run-draft'}
  }
  'ResumeSession' {
    if(-not (Test-Path -LiteralPath $CaseFolder -PathType Container)){
      throw 'Existing session folder required.'
    }
    $arguments=@('-3.11','-m','aihawk.academic_resume_session',$CaseFolder,'--auto')
  }
  'ExecuteCase' {
    $arguments=@('-3.11','-m','aihawk.academic_execution',$CaseFolder)
    if($RunDraft){$arguments+='--run-draft'}
  }
  'Discover' {
    if([string]::IsNullOrWhiteSpace($OutputPath)){
      throw 'Discover requires OutputPath.'
    }
    $arguments=@('-3.11','-m','aihawk.academic_discovery','--out',$OutputPath)
  }
}
& py @arguments
if($LASTEXITCODE -ne 0){
  throw ('Academic agent exited with code '+$LASTEXITCODE)
}
