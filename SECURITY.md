# Security

eval-builder reads log files you point it at and writes files into a workspace
directory. It makes no network calls. The optional judge runner starts only the
command you pass with `--command`, and only when you also pass
`--enable-judge-plugin`.

Logs often contain personal data. Redaction is on by default but is pattern-based and
will miss things (names, addresses, free-form secrets). Review the workspace before
sharing it.

To report a vulnerability, open a private security advisory on the GitHub repository
or email the maintainer. Please do not file a public issue for security problems.
