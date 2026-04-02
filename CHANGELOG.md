# Changelog

All notable changes to this project are documented here.

## [0.0.1.0] - 2026-04-02

### Added
- Twilio Media Streams voice pipeline (`app/routers/stream.py`): full per-call
  STT→LLM→TTS pipeline over WebSocket. Deepgram nova-2 streaming STT, Claude
  claude-sonnet-4-6 conversation management with state machine, ElevenLabs TTS
  with correct μ-law 8kHz output format. Barge-in via task cancellation.
- New customer onboarding guide (`docs/NEW_CUSTOMER.md`): 8-step developer
  checklist from buying a Twilio number through client handoff, including full
  `PracticeConfig` reference, voice selection guide, test scenarios, and
  troubleshooting section.
- Mermaid architecture diagrams in README: system overview, call flow sequence,
  and conversation state machine.
- Test suite for Twilio Media Streams paths: `test_calls.py` updated for
  `<Connect><Stream>` TwiML, `test_stream.py` added with regression tests for
  ElevenLabs `output_format` query param, greeting content, and after-hours
  path.

### Changed
- Replaced LiveKit SIP integration with Twilio Media Streams. `calls.py` now
  returns `<Connect><Stream>` TwiML instead of `<Dial><Sip>`. No separate
  worker process needed — the voice pipeline runs inline per WebSocket
  connection.
- Dependencies: replaced `livekit-agents` and plugins with `anthropic`,
  `deepgram-sdk<4.0.0` (v6 removed `LiveOptions` from top-level package),
  and `elevenlabs`.
- `app/main.py`: registers stream router and configures `logging.basicConfig`
  so app-level log lines surface alongside Uvicorn in Azure log stream.

### Fixed
- ElevenLabs audio format: `output_format=ulaw_8000` must be a URL query
  parameter, not a request body field. Body placement is silently ignored —
  ElevenLabs returns MP3 by default, which sounds like pure noise when streamed
  as μ-law audio to Twilio.
- WebSocket CLOSE frame fragmentation (Twilio error 31924): removed all
  explicit `ws.close()` calls from inside WebSocket handlers. Azure App
  Service's reverse proxy fragments CLOSE control frames; Twilio rejects
  fragmented frames. Now just `break` or `return` and let the endpoint exit
  naturally.
- Deepgram SDK pinned to `<4.0.0`: v6 removed `LiveOptions` from the
  top-level `deepgram` package.
