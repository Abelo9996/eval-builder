Output docs/demo.gif
Set FontSize 14
Set Width 1600
Set Height 900
Set Theme "Builtin Dark"
Set TypingSpeed 30ms
Hide
Type "cd \"$(mktemp -d)\" && clear"
Enter
Show
Type "curl -sLO https://raw.githubusercontent.com/Abelo9996/eval-builder/main/examples/sample_logs.jsonl"
Enter
Wait
Type "uvx eval-builder ingest sample_logs.jsonl"
Enter
Wait
Sleep 1.5s
Type "uvx eval-builder select -n 10 --stratify category"
Enter
Wait+Screen@20s /next: run draft/
Sleep 2s
Type "uvx eval-builder draft && grep -m1 -A10 'id: case-002' evalset/cases.yaml | cut -c1-120"
Enter
Wait+Screen@20s /role: user/
Sleep 5s
