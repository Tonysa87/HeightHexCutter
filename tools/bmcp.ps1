param([string]$CodeFile)
# Sends a Python snippet to the official Blender MCP add-on (null-delimited JSON on 127.0.0.1:9876)
$code = [System.IO.File]::ReadAllText($CodeFile)
$payload = (@{type = 'execute'; code = $code; strict_json = $false} | ConvertTo-Json -Compress) + [char]0
$c = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 9876)
$s = $c.GetStream(); $s.ReadTimeout = 600000
$b = [System.Text.Encoding]::UTF8.GetBytes($payload); $s.Write($b, 0, $b.Length); $s.Flush()
$ms = New-Object System.IO.MemoryStream; $buf = New-Object byte[] 65536
while ($true) { $n = $s.Read($buf, 0, $buf.Length); if ($n -le 0) { break }; $ms.Write($buf, 0, $n); if ($buf[$n-1] -eq 0) { break } }
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output ([System.Text.Encoding]::UTF8.GetString($ms.ToArray()).TrimEnd([char]0))
$c.Close()
