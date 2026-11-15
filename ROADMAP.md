# FRIDAY 2.0 — Implementation Roadmap

## Overview

The FRIDAY 2.0 implementation follows a phased approach to ensure systematic development, quality assurance, and risk mitigation. Each phase builds upon previous deliverables and prepares for the next stage.

## Phase 0: Skeleton

### Objectives

- Establish project structure and basic functionality
- Create core gateway and chat interface
- Implement basic persistence layer
- Set up development environment
- Create test framework

### Deliverables

#### Phase 0.1: Project Structure
- Create src/friday/ structure with app.py, core/, gateway/, memory/, voice/, tools/, security/, config/, ui/
- Create tests/{unit,integration}/ structure
- Create scripts/ directory
- Create pyproject.toml with src layout

#### Phase 0.2: Gateway and Chat
- Implement Gateway class with OpenAI-compatible interface (base_url, model, key)
- Create basic chat functionality
- Implement conversation management
- Set up memory storage with sqlite3

#### Phase 0.3: Persistence
- Implement memory system with sqlite3
- Add FTS5 full-text search support
- Create conversation storage and retrieval
- Implement context management

#### Phase 0.4: Tool Runtime
- Create tool calling engine
- Implement tool definitions
- Set up tool execution framework

#### Phase 0.5: Voice Pipeline
- Implement voice output (text-to-speech)
- Implement voice input (speech-to-text)
- Create voice activation detection
- Set up audio recording and playback

#### Phase 0.6: Windows Automation
- Create Windows automation module with controlled access
- Implement operation confirmation system
- Set up audit logging
- Create secure automation wrappers

#### Phase 0.7: Files and Web Intelligence
- Implement file intelligence module
- Create file analysis and search capabilities
- Set up web intelligence integration
- Implement content extraction

#### Phase 0.8: Reminders
- Create reminder and background task system
- Implement task scheduler
- Set up notification system
- Create reminder management

#### Phase 0.9: Packaging and Wake Word
- Create deployment package
- Set up wake word detection
- Configure installation procedures
- Implement maintenance procedures

## Development Principles

### Core Architecture
- **Single Gateway**: One OpenAI-compatible provider class
- **Stdlib Storage**: sqlite3 only, no SQLAlchemy
- **Single User**: No user_id anywhere; single-user app
- **Minimal Tooling**: pytest + ruff only (no black/isort/flake8/mypy)
- **Real Failures**: No fake/demo AI responses or silent provider fallback
- **Test Doubles**: Only live in tests/

### Testing Approach
- **Unit Tests**: tests/unit/
- **System Tests**: tests/integration/
- **Test Doubles**: Scripted providers live only in tests/
- **No Real External Access**: Do NOT hit network or real Credential Manager in pytest

## Phase 1: AI Gateway + Streaming Chat

### Status

Implemented.

### Deliverables

- `gateway/` OpenAI-compatible streaming provider (manual SSE parsing, retries only
  for connection errors and 5xx before the first token, typed errors, reasoning
  filtering, clean cancellation)
- `provider` config section in `%APPDATA%\Friday\config.toml`
- `CoreService.chat_send` / `cancel_chat` / `clear_chat` with in-memory history and
  Qt streaming signals
- Chat UI: transcript, streaming tokens, Stop / New chat, typed error display
- Manual scripts: `scripts/set_key.py`, `scripts/list_models.py`,
  `scripts/live_smoke.py`

### Acceptance Criteria

- `pip install -e ".[dev]"` installs PySide6-Essentials only (no WebEngine/Pdf)
- `ruff check .` clean and `pytest -v` green, with no network in tests
- `python -m friday` opens the chat UI; a missing model/key shows `NotConfigured`
  with remediation steps

## Phase 2: Conversation Persistence

### Status

Implemented.

### Deliverables

- `memory/db.py`: SQLite connection at `%LOCALAPPDATA%\Friday\friday.db`, WAL,
  foreign keys, versioned migrations, thread ownership checks, typed errors
- `memory/conversations.py`: parameterized conversation/message repository and
  automatic titles
- Core persistence: user messages stored immediately; complete and incomplete
  assistant replies stored with status; database-aware context selection with
  `chat.context_char_budget`
- Conversation sidebar with open, new, rename, and confirmed delete actions
- Incomplete replies marked `(incomplete)` when a conversation is reopened

### Acceptance Criteria

- `ruff check .` clean and `pytest -v` green, with temporary databases only
- Conversations and messages survive restart
- Deleting a conversation removes its messages
- Database failures and newer schema versions surface as typed UI errors

### Security Model
- **Secure by Design**: No plaintext credential storage
- **Operation Confirmation**: Explicit user consent for sensitive operations
- **Audit Logging**: Comprehensive logging for all security events
- **Least Privilege**: Minimum permissions required for operations

## Implementation Details

### Component Structure

#### Core Layer
- **core/**: Core service with asyncio event loop in dedicated thread
- **gateway/**: AI provider gateway
- **memory/**: sqlite3-based persistence with FTS5

#### Interface Layer
- **ui/**: PySide6 main window with status, button, output
- **config/**: Pydantic settings from %APPDATA%\Friday\config.toml
- **security/**: Keyring-based secrets management
- **voice/**: Speech recognition and synthesis
- **tools/**: Tool calling and execution

#### Integration Layer
- **scripts/**: Utility scripts
- **tests/**: Comprehensive test suite

### Testing Requirements
- **Acceptance Criteria**: All tests pass
- **No Fake AI**: Real provider calls only; scripted providers live in tests/
- **No Demo**: No fake AI responses or simulations
- **Real Failures**: Real errors shown, no silent fallbacks

## Next Phase Preparation

### Phase 1 Ready for:
- Core service with Qt signals/slots communication
- Gateway with OpenAI-compatible interface
- Memory system with sqlite3 and FTS5
- Basic UI with Ping core functionality
- Secure credential management
- Configuration management
- Logging with redaction
- Test framework with pytest and ruff

### Acceptance Criteria
- **Development**: `pip install -e .[dev]` works in a fresh venv
- **Code Quality**: `ruff check .` passes with no errors
- **Testing**: `pytest -v` passes
- **Functional**: `python -m friday` opens the chat window; streaming replies appear
  live; closing the window ends the process
- **Security**: The API key is stored in Credential Manager and never logged
- **Testing**: No real external access in pytest

## References

- Security documentation: [SECURITY.md](./SECURITY.md)
- Testing requirements: [TESTING.md](./TESTING.md)

## Phase 2: Desktop Interface & Voice Pipeline (Weeks 5-8)

### Objectives

- Implement native desktop interface
- Create voice input/output pipeline
- Integrate speech recognition
- Build speech synthesis
- Implement desktop application entry point

### Deliverables

#### Week 5-6: Desktop Interface
- [ ] Implement main window and UI components using PySide6
- [ ] Create user interaction flows
- [ ] Implement window management
- [ ] Create UI event handling
- [ ] Add basic styling and theming

#### Week 7-8: Voice Pipeline
- [ ] Implement speech recognition module (Faster-Whisper)
- [ ] Implement speech synthesis module (Edge-TTS)
- [ ] Create audio recording and playback
- [ ] Implement voice activation detection
- [ ] Create voice command processing

### Acceptance Criteria

- [ ] Desktop interface is fully functional with all basic UI elements
- [ ] Voice recognition can accurately transcribe speech
- [ ] Speech synthesis can generate clear audio output
- [ ] Voice activation works reliably
- [ ] Voice commands are processed correctly
- [ ] All UI interactions are responsive and user-friendly
- [ ] Comprehensive UI tests pass

## Phase 3: Core Assistant Features (Weeks 9-12)

### Objectives

- Implement conversation management
- Create tool calling engine
- Implement web intelligence
- Build file intelligence
- Add reminder and background task management

### Deliverables

#### Week 9-10: Assistant Core
- [ ] Implement conversation management system
- [ ] Create conversation history and context management
- [ ] Implement tool calling engine with plugin architecture
- [ ] Create tool definitions and execution framework
- [ ] Implement web intelligence integration

#### Week 11-12: Intelligence Systems
- [ ] Implement file intelligence module
- [ ] Create file analysis and search capabilities
- [ ] Implement reminder and background task system
- [ ] Create task scheduler and executor
- [ ] Implement notification system

### Acceptance Criteria

- [ ] Assistant can engage in natural conversations
- [ ] Tool calling system is secure and reliable
- [ ] Web intelligence provides accurate results
- [ ] File intelligence can analyze and search files
- [ ] Reminder system works as expected
- [ ] All systems integrate seamlessly
- [ ] Performance is acceptable for typical use cases

## Phase 4: Windows Automation & Security (Weeks 13-16)

### Objectives

- Implement controlled Windows automation
- Enhance security model
- Create operation confirmation system
- Implement audit logging
- Build access control mechanisms

### Deliverables

#### Week 13-14: Windows Automation
- [ ] Implement Windows automation module with pywin32
- [ ] Create action catalog and templates
- [ ] Implement operation confirmation system
- [ ] Create safe operation wrapper
- [ ] Implement desktop interaction controls

#### Week 15-16: Security Enhancement
- [ ] Implement enhanced security controls
- [ ] Create access control system
- [ ] Implement comprehensive audit logging
- [ ] Add security monitoring
- [ ] Create security policy management

### Acceptance Criteria

- [ ] Windows automation is secure and controlled
- [ ] All operations require appropriate confirmation
- [ ] Security system prevents unauthorized access
- [ ] Audit logs capture all relevant events
- [ ] Security policies are enforceable
- [ ] System withstands security tests

## Phase 5: Integration, Testing & Deployment (Weeks 17-20)

### Objectives

- Integrate all modules
- Perform comprehensive testing
- Create deployment package
- Document user guide
- Set up maintenance procedures

### Deliverables

#### Week 17-18: Integration
- [ ] Integrate all modules into cohesive system
- [ ] Create system orchestration layer
- [ ] Implement error handling and recovery
- [ ] Create system health monitoring
- [ ] Implement graceful shutdown procedures

#### Week 19-20: Finalization
- [ ] Create PyInstaller package
- [ ] Implement comprehensive testing suite
- [ ] Create user documentation
- [ ] Set up maintenance procedures
- [ ] Create deployment procedures

### Acceptance Criteria

- [ ] All modules integrate successfully
- [ ] System passes all tests (unit, integration, system)
- [ ] Deployment package is functional
- [ ] User documentation is complete
- [ ] Maintenance procedures are documented
- [ ] System meets all performance requirements
- [ ] System is ready for production deployment

## Risk Management

### Known Risks and Mitigation Strategies

1. **API Dependency Risk**
   - *Risk*: Dependence on external AI providers
   - *Mitigation*: Implement multiple provider support, local fallback options

2. **Performance Constraints**
   - *Risk*: System performance issues with limited resources
   - *Mitigation*: Optimize code, implement caching, use efficient data structures

3. **Security Vulnerabilities**
   - *Risk*: Security issues in Windows automation
   - *Mitigation*: Implement comprehensive security controls, regular security reviews

4. **Voice Processing Quality**
   - *Risk*: Poor voice recognition/synthesis quality
   - *Mitigation*: Use multiple providers, implement fallback mechanisms

5. **Integration Complexity**
   - *Risk*: Module integration challenges
   - *Mitigation*: Incremental integration, comprehensive testing

### Risk Monitoring

- Weekly risk assessment meetings
- Continuous integration testing
- Security code reviews
- Performance monitoring
- User feedback collection

## Resource Requirements

### Human Resources
- 1 Lead Developer (architect, implementation)
- 0.5 QA Engineer (testing, quality assurance)
- 0.5 DevOps Engineer (deployment, infrastructure)

### Computational Resources
- Development environment: 8 GB RAM (minimum), 16 GB recommended
- Deployment environment: 4 GB RAM minimum
- Storage: Sufficient for application and user data

### Time Requirements
- Total estimated effort: 640 hours (20 weeks)
- Buffer time: 10-15% (64-96 hours)
- Critical path dependencies

## Success Metrics

### Technical Metrics
- System uptime: > 99%
- Average response time: < 2 seconds
- Memory usage: < 2 GB
- CPU usage: < 50% during normal operation

### User Experience Metrics
- User satisfaction: > 85%
- Task completion rate: > 90%
- Voice recognition accuracy: > 90%
- Issue resolution time: < 1 hour

### Quality Metrics
- Code coverage: > 90%
- Bug escape rate: < 0.1%
- Security vulnerabilities: 0 critical, < 5 medium
- Test failure rate: < 1%

## Phase Transitions

Each phase transition includes:
- Comprehensive testing and validation
- Documentation completion
- User acceptance testing
- Risk assessment and mitigation
- Resource reallocation if needed

The system is only ready to proceed to the next phase when all acceptance criteria are met.

## References

- Development documentation: [DEVELOPMENT.md](./DEVELOPMENT.md)
- Security requirements: [SECURITY.md](./SECURITY.md)
- Testing requirements: [TESTING.md](./TESTING.md)