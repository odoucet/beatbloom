# Security

BeatBloom 0.3 is experimental. Use supported FFmpeg and Python dependency
versions and review third-party media and filter settings before processing.
The application does not execute shell commands from configuration; subprocess
arguments are passed directly to FFmpeg. `--grade` is a user-supplied FFmpeg
filter graph and is intended for trusted local use.

Report a suspected vulnerability privately through the repository's GitHub
Security advisory reporting if it is enabled. Otherwise open a minimal issue
asking for a private contact, without including exploit details or private data.
Include the BeatBloom and FFmpeg versions and a minimal reproduction once a
private channel has been established.

Security fixes are developed for the latest release. There are no separate
long-term support branches yet.
