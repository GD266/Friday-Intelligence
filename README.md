# FRIDAY 2.0 — Personal AI Assistant

## Project Overview

FRIDAY 2.0 is a powerful native Windows desktop AI assistant designed to enhance productivity through natural conversation, voice interaction, persistent memory, and controlled task execution.

## Key Features

- **Native Desktop Experience**: Built with PySide6 for a genuine Windows application feel
- **Natural Conversation**: AI-powered conversation management with multiple provider support
- **Voice Interaction**: Speech synthesis (Edge-TTS) and speech recognition (Faster-Whisper/Cloud)
- **Persistent Memory**: SQLite-based memory system for maintaining conversation history and user knowledge
- **Windows Automation**: Controlled desktop automation with security safeguards
- **File Intelligence**: Smart file analysis and management
- **Web Research**: Real-time web intelligence gathering
- **Task Execution**: Tool calling engine with explicit confirmation for sensitive operations
- **Background Tasks**: Reminder and background task management

## Technology Stack

- **Python 3.12+** - Primary language
- **PySide6** - Native desktop UI framework
- **PyInstaller** - Windows executable packaging
- **SQLite** - Persistent storage
- **asyncio** - Asynchronous operations
- **Pydantic** - Configuration and data validation
- **Pytest** - Automated testing
- **OpenAI-compatible API clients** - Cloud AI provider integration
- **Edge-TTS** - Speech synthesis
- **Faster-Whisper** - Speech recognition
- **pywin32** - Windows API access and automation

## System Architecture

FRIDAY 2.0 is designed as a modular, event-driven architecture with clear separation of concerns:

1. **Desktop Interface Module**: Manages the native Windows UI
2. **Core Assistant Orchestrator**: Coordinates all system operations
3. **AI Provider Gateway**: Abstracts AI provider interactions
4. **Conversation Management**: Handles dialogue flow and context
5. **Memory System**: Persistent storage and retrieval
6. **Speech Recognition**: Converts speech to text
7. **Speech Synthesis**: Converts text to speech
8. **Tool Calling Engine**: Executes controlled operations
9. **Windows Automation**: Desktop interaction with security
10. **Web Intelligence**: Real-time information gathering
11. **File Intelligence**: File analysis and management
12. **Reminder System**: Background task management
13. **Configuration System**: Secure settings and credential management
14. **Logging System**: Diagnostics and error tracking

## Security Features

- Secure credential storage using Windows Credential Manager
- Explicit confirmation required for sensitive operations
- No unrestricted shell access
- Controlled desktop automation with user approval
- Comprehensive logging for auditing

## System Requirements

- Windows 10/11
- 8 GB RAM minimum
- Python 3.12+
- Internet connection for AI services and web research

## Getting Started

### Phase 0: Skeleton
1. Clone this repository
2. Create a virtual environment: `python -m venv venv`
3. Activate environment and install dependencies
4. Run tests to verify setup
5. Begin implementation of skeleton structure

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture and module design
- [ROADMAP.md](./ROADMAP.md) - Implementation timeline and milestones
- [SECURITY.md](./SECURITY.md) - Security design and implementation

## License

This project is currently in development. All code is proprietary to the FRIDAY 2.0 project.