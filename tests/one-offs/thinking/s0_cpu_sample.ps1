# S0 (4): sample ck3.exe's CPU use every 2 s for $Seconds, to a CSV (time, percent of one core summed over cores).
# Run beside tests/one-offs/launch_load_test.py; samples before ck3.exe exists are written as "absent".
param([string]$Out, [int]$Seconds = 300)
$end = (Get-Date).AddSeconds($Seconds)
"time,cpu_percent" | Out-File -FilePath $Out -Encoding ascii
while ((Get-Date) -lt $end) {
    try {
        $v = (Get-Counter '\Process(ck3)\% Processor Time' -ErrorAction Stop).CounterSamples[0].CookedValue
        "{0},{1:N1}" -f (Get-Date -Format HH:mm:ss), $v | Out-File -FilePath $Out -Append -Encoding ascii
    } catch {
        "{0},absent" -f (Get-Date -Format HH:mm:ss) | Out-File -FilePath $Out -Append -Encoding ascii
    }
    Start-Sleep -Seconds 2
}
