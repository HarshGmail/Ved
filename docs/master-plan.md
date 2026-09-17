# Ved Home AI System - Master Project Plan

## 1. Vision

Build a personal AI assistant inspired by JARVIS: a private, always-available system that can understand voice/text requests, search the internet, remember useful information, operate personal apps through MCP, interact with home devices, understand camera events, manage family photos, and proactively notify the user when something important happens.

The long-term goal is not merely to train a large language model. The goal is to build a complete personal AI operating layer.

The system should eventually be able to:

- Answer questions using current web information.
- Call MCP tools to perform actions.
- Manage reminders, calendar, notes, files, and personal applications.
- Maintain long-term personal/family memory.
- Automatically back up family photos and videos.
- Search and understand the private photo library.
- Receive events from home cameras.
- Detect people at the front door and recognize known people.
- Announce events such as "Your mother is at the front door."
- Control home electronics through MCP.
- Use voice input and natural spoken responses.
- Respond extremely quickly and stream its response while work is happening.
- Use nearby displays/TVs as visual companions when appropriate.
- Eventually run much of the AI stack locally using dedicated GPU hardware.

The system should be designed from the beginning so individual components can be replaced or upgraded without rebuilding the whole system.

---

# 2. Core Architecture

The overall architecture should look approximately like this:

                         USER
                           |
                 +---------+---------+
                 |                   |
              Phone/PWA          Voice/Text
                 |                   |
                 +---------+---------+
                           |
                           v
                     Ved FRONTEND
                    Next.js / PWA
                           |
                    HTTPS / WebSocket
                           |
                           v
                      Ved BACKEND
                     Python/FastAPI
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
       Agent            Memory           Event Bus
     Orchestrator        System
          |
     +----+----+---------+---------+
     |         |         |         |
     v         v         v         v
    LLM      Web       MCP       Vision
             Search    Tools
                         |
              +----------+----------+
              |          |          |
              v          v          v
          Reminders   Calendar    Home
          Photos      Finance     Files
          Email       GitHub      etc.

The backend should be the central nervous system. The frontend should primarily be an interface to the backend rather than containing the core intelligence.

---

# 3. Frontend Strategy

## Initial choice: Next.js PWA

Build the frontend as:

- Next.js
- TypeScript
- React
- PWA support
- Responsive/mobile-first UI
- WebSocket or SSE for streaming
- Push notifications where supported

This gives one codebase that can work on:

- Desktop browser
- Android
- iPhone
- Tablet

Users can install the PWA from the browser.

## Later: Native wrapper if required

If the PWA eventually needs deeper native capabilities, consider:

- Capacitor around the Next.js application
- React Native if a genuinely native frontend becomes necessary

Do not start with separate Next.js + React Native + Flutter applications. That creates unnecessary maintenance before the requirements are known.

The initial goal is one frontend.

---

# 4. Backend

Recommended initial backend:

- Python
- FastAPI
- WebSockets/SSE
- PostgreSQL
- pgvector for semantic memory
- Redis where useful
- Docker

The backend should manage:

- User sessions
- Agent execution
- LLM calls
- MCP connections
- Web search
- Memory retrieval
- Long-running jobs
- Scheduled tasks
- Event handling
- Notifications
- Permissions
- Camera events
- Photo metadata
- Authentication

---

# 5. The LLM Is the Brain, Not the Entire System

Do NOT initially train a foundation model from scratch.

Use an existing strong model first.

The LLM should be responsible for:

- Understanding requests
- Reasoning
- Planning
- Selecting tools
- Producing natural responses
- Deciding when more information is needed

MCP tools should perform the actual actions.

Example:

User:
"Remind me tomorrow morning to call Dad."

LLM:
- Understand intent
- Determine required tool
- Call reminders.create()

MCP server:
- Actually creates the reminder.

This means new capabilities can be added without retraining the model.

---

# 6. MCP Ecosystem

Create separate MCP servers for different capabilities.

Potential MCP servers:

- Reminders
- Calendar
- Notes
- Photos
- Files
- Email
- Finance
- GitHub
- Home automation
- Cameras
- Computer
- Media
- Shopping
- Personal databases

Example tool groups:

calendar.list_events()
calendar.create_event()

reminders.create()
reminders.list()
reminders.complete()

photos.search()
photos.find_person()
photos.get_album()

home.turn_light_on()
home.turn_light_off()
home.get_status()

camera.get_snapshot()
camera.get_recent_events()
camera.who_is_at_door()

The LLM should see tools through MCP and use them dynamically.

---

# 7. Memory System

Ved needs several types of memory.

## Short-term memory

Current conversation and task state.

## Long-term memory

Useful information about the user, family, preferences, projects, etc.

## Semantic memory

Embeddings stored in PostgreSQL + pgvector.

This enables queries such as:

"Find the information I saved about my car."

or:

"What did I decide about the home server last month?"

## Structured memory

Use normal database tables for facts that need reliable querying.

Do not store everything as embeddings.

The memory architecture should combine:

- PostgreSQL structured data
- pgvector semantic search
- Conversation history
- Files/documents
- Photo metadata

---

# 8. Family Photo Cloud

The home server will eventually act as a private family photo cloud.

Initial design:

                    PHONES
                       |
                Photo/video upload
                       |
                       v
                HOME SERVER
                       |
              +--------+--------+
              |                 |
              v                 v
          PRIMARY SSD        MIRROR SSD
          2 TB initially     2 TB initially

The phone application should be able to:

- Request photo/video access
- Automatically upload new media
- Upload in background where platform permits
- Resume interrupted uploads
- Track upload status
- Avoid duplicate uploads
- Organize media by user/date
- Show storage usage
- Allow browsing of the private library

## Important backup distinction

Two SSDs are a good starting point, but they are not a complete disaster-recovery strategy.

A mirror protects against a single drive failure.

It does not fully protect against:

- Accidental deletion
- Ransomware
- Corruption copied to both disks
- Theft
- Fire
- Power damage
- Other physical disasters

Later add an off-site or cloud backup.

Initial priority:

1. Two SSDs
2. Automated mirroring/backup
3. Versioning
4. Later: off-site backup

---

# 9. Storage Architecture

Start with:

SSD 1:
- Primary photo storage
- Application data where appropriate

SSD 2:
- Mirror/backup

The OS and application code can initially live on the laptop's existing storage.

Keep the storage architecture modular so additional disks can be added later.

Eventually consider:

- Larger NAS
- ZFS
- RAID where appropriate
- Versioned snapshots
- Off-site encrypted backup
- UPS

Do not confuse RAID/mirroring with a full backup strategy.

---

# 10. Current Server Hardware

Existing hardware:

- Approximately 6-year-old Intel i7 octa-core laptop
- Existing Mac M4 available for development
- Planned two 2 TB SSDs
- Future dedicated GPU hardware

The old Intel laptop can initially become the home server.

It can run:

- Linux
- Docker
- Ved backend
- MCP servers
- PostgreSQL
- Photo service
- Event bus
- Camera processing coordination
- Home automation
- Scheduler
- Monitoring

Prefer Ethernet for the server instead of Wi-Fi.

The Mac M4 can remain the development machine and can also be used for local AI experimentation.

---

# 11. GPU Strategy

Do not immediately buy expensive GPUs.

First build the system and measure actual workloads.

Possible future dedicated GPU server:

                    HOME NETWORK
                         |
                    GPU SERVER
                         |
        +----------------+----------------+
        |                |                |
       LLM             Vision           Speech
        |                |                |
    reasoning       cameras/OCR       STT/TTS

The GPU server can be a separate machine from the old i7 server.

This is preferable to forcing a powerful GPU into an old laptop through an external GPU connection.

The old laptop becomes the orchestration/control server.

The GPU machine becomes the AI compute worker.

---

# 12. Training Your Own LLM

FineWeb and other open datasets can eventually be used for training experiments.

Do not start by trying to reproduce a modern 7B/70B foundation model.

Instead:

1. Train a tiny Transformer from scratch.
2. Train on a small FineWeb subset.
3. Understand tokenization and pretraining.
4. Increase model size gradually.
5. Experiment with instruction tuning.
6. Compare local models with API models.
7. Only then consider larger training.

For Ved itself, an existing model plus good agent architecture is more important initially than owning a foundation model.

The long-term system can use:

- Cloud LLMs
- Local LLMs
- Multiple models
- Smaller specialized models

depending on task and latency requirements.

---

# 13. Camera Architecture

This needs to be designed separately from the LLM.

Do NOT continuously send raw camera video to the LLM.

Recommended architecture:

                         IP CAMERA
                            |
                       RTSP / Stream
                            |
                            v
                    CAMERA PROCESSOR
                            |
                    Computer Vision
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           Person        Face          Object
          detection    recognition     detection
              |             |             |
              +-------------+-------------+
                            |
                         EVENT
                            |
                            v
                           Ved
                            |
                         Action
                            |
                            v
                   Phone / Speaker / TV

Potential cameras:

- Front door
- Living room
- Kitchen
- Additional coverage points

Each camera should preferably provide an IP/RTSP stream over the home network.

The laptop/server receives those streams.

A dedicated camera/NVR/vision service processes them.

The AI agent receives events rather than constantly processing raw video.

---

# 14. Front Door Person Recognition

Example flow:

Camera:
"Person detected."

Vision service:
"Face detected."

Face recognition:
"Known person: Mom."

Event:

PERSON_AT_DOOR
person = Mom
camera = Front Door
confidence = 0.94

Ved:

"Your mom is at the front door."

For unknown people:

PERSON_AT_DOOR
person = UNKNOWN

Ved:

"There is an unrecognized person at the front door."

The system should allow configurable confidence thresholds and avoid treating uncertain recognition as certain identity.

---

# 15. Camera Data Flow

Initial implementation should be:

Camera -> Ethernet/Wi-Fi -> Home Router/Switch -> Server -> Camera/NVR service -> Vision model -> Event Bus -> Ved

When possible, use wired Ethernet/PoE cameras.

A PoE switch can eventually simplify:

- Camera power
- Networking
- Reliability
- Cable management

This should be researched before purchasing cameras.

Potential technologies to investigate later:

- RTSP
- ONVIF
- Frigate
- go2rtc
- OpenCV
- YOLO-family detectors
- face recognition/face embedding models
- GPU-accelerated inference

The exact stack should be selected after deciding the camera hardware.

---

# 16. Home Automation

Home electronics should be connected to Ved through controlled interfaces.

Prefer:

Device
  ->
Home automation platform
  ->
MCP server
  ->
Ved

rather than allowing the LLM direct access to arbitrary devices.

Possible device categories:

- Lights
- Fans
- AC
- TV
- Switches
- Sensors
- Door sensors
- Smart plugs
- Appliances
- Speakers

The LLM should request actions and a permission layer should decide whether they are allowed.

---

# 17. Permission System

This is mandatory because Ved will eventually have access to sensitive systems.

Example:

Read calendar:
ALLOW

Turn off lights:
ALLOW

Read camera:
ALLOW

Unlock door:
REQUIRE CONFIRMATION

Delete photos:
REQUIRE CONFIRMATION

Transfer money:
REQUIRE CONFIRMATION

Execute arbitrary shell command:
DENY by default

The LLM must never have unrestricted system access.

---

# 18. Event-Driven Ved

The system should not only respond to user questions.

It should also react to events.

Potential events:

- PERSON_DETECTED
- FACE_RECOGNIZED
- UNKNOWN_PERSON_AT_DOOR
- DOOR_OPENED
- PACKAGE_DELIVERED
- CALENDAR_EVENT_APPROACHING
- REMINDER_TRIGGERED
- PHOTO_UPLOADED
- SERVER_HEALTH_WARNING
- HOME_SENSOR_ALERT

Architecture:

Camera/Sensor/App
        |
        v
    Event Bus
        |
        v
       Ved
        |
        +--> Notify
        +--> Speak
        +--> Call MCP
        +--> Ignore
        +--> Ask user

This is what allows Ved to become proactive.

---

# 19. Speed and Responsiveness

Fast response is a core requirement.

The user should not wait for an entire task to finish before hearing anything.

Example:

User:
"Hey Ved, what happened in the India vs Afghanistan match last night?"

Desired behavior:

Immediately:
"Certainly, sir. Let me check the latest match information."

At the same time:
- Start web search
- Retrieve relevant sources
- Extract facts
- Compare sources
- Generate response

Then begin speaking as soon as enough reliable information is available.

Architecture:

Voice input
    |
    v
Intent detection
    |
    +----------------------+
    |                      |
    v                      v
Immediate acknowledgement  Search/tool execution
                           |
                           v
                       Results arrive
                           |
                           v
                     LLM synthesis
                           |
                           v
                     Stream response
                           |
                           v
                     TTS streaming

Do not wait for every possible operation before beginning the response.

Use parallel tool execution when independent operations can happen simultaneously.

Use streaming everywhere possible:

- Speech recognition
- LLM generation
- Web search/result processing
- TTS

Latency should be treated as a first-class engineering requirement.

---

# 20. Voice Architecture

Eventually:

Microphone
    |
    v
Speech-to-text
    |
    v
Ved Agent
    |
    v
LLM
    |
    v
Text response
    |
    v
Text-to-speech
    |
    v
Speaker

Possible future additions:

- Wake word
- Speaker identification
- Voice activity detection
- Streaming STT
- Streaming TTS
- Different response modes

The assistant should be able to operate hands-free.

---

# 21. TV / Nearby Display Integration

Long-term goal:

If a TV/display is available near the user, Ved should be able to provide visual context.

Example:

User:
"Hey Ved, what happened in the India vs Afghanistan match?"

Ved:
- Searches the web
- Speaks the answer
- Detects an available display
- Opens a visual panel/tab
- Shows scorecard/source information

Possible architecture:

Ved
   |
   +--> Voice response
   |
   +--> TV/display MCP
             |
             v
        Display content

The display system could eventually support:

- Match scorecards
- Web pages
- Maps
- Photos
- Camera feeds
- Charts
- Documents
- Notifications
- Home status

The TV should be treated as another Ved device/end point.

---

# 22. Device Presence

Eventually Ved should understand available devices.

Example:

DEVICES:

- User iPhone
- User Android/tablet if applicable
- Home TV
- Mac
- Home server
- Speakers
- Other displays

Then Ved can choose where to present information.

For example:

Short answer:
Phone + voice

Long answer:
Phone + voice + visual panel

Camera event:
Phone notification + home speaker

Match:
Voice + TV scorecard

---

# 23. Remote Access

The user wants to access the system from anywhere through the internet.

The home server should host the backend/domain.

Architecture:

Phone
   |
 Internet
   |
 HTTPS
   |
 Domain
   |
 Home network
   |
 Ved server

However, do not expose every internal service directly to the public internet.

Prefer:

- HTTPS
- Reverse proxy
- Authentication
- Strong credentials
- MFA
- VPN or secure private networking where appropriate
- Firewall
- Separate internal/private services

Only expose the minimum public surface.

---

# 24. Domain

The user's existing domain can be used for Ved.

Potential structure:

app.example.com
api.example.com
photos.example.com

The exact domain/subdomain naming can be decided later.

The public web application should connect securely to the home server.

---

# 25. Development vs Production

The Mac M4 should initially be the development environment.

The old Intel laptop becomes the home server.

Development:

Mac M4
  |
  +--> Next.js
  +--> Python
  +--> Docker
  +--> local testing
  +--> local model experiments

Production/home:

Old i7 laptop
  |
  +--> Ved backend
  +--> database
  +--> MCP
  +--> photos
  +--> event bus
  +--> camera services

Future:

Dedicated GPU server
  |
  +--> local LLM
  +--> vision
  +--> speech
  +--> embeddings

---

# 26. Suggested Project Phases

## Phase 0 - Architecture

- Define repositories
- Define APIs
- Define authentication
- Define database schema
- Define MCP conventions
- Define event format
- Define permissions model

## Phase 1 - Ved Core

Build:

- Next.js PWA
- Python/FastAPI backend
- Chat UI
- Streaming responses
- LLM integration
- MCP client
- One or two MCP servers

First milestone:

User -> Ved -> MCP tool -> result -> response

## Phase 2 - Memory

Build:

- PostgreSQL
- Conversation storage
- Structured user memory
- pgvector
- Semantic search
- File/document memory

## Phase 3 - Photo Cloud

Build:

- Phone photo upload
- Video upload
- Primary SSD
- Mirror SSD
- Photo metadata
- Thumbnails
- Albums
- Search
- User accounts
- Backup monitoring

## Phase 4 - Web + Fast Agent

Build:

- Web search
- Parallel tool execution
- Streaming tool status
- Fast acknowledgement
- Streaming LLM output
- Streaming TTS

Target experience:

"Let me check that."

while the actual search is already running.

## Phase 5 - Voice

Build:

- Wake word
- STT
- TTS
- Voice activity detection
- Streaming audio

## Phase 6 - Home Automation

Build:

- Smart switches
- Home automation platform
- MCP integration
- Permissions
- Device status

## Phase 7 - Cameras

Start with ONE camera.

Build:

- RTSP/ONVIF ingestion
- NVR/stream management
- Person detection
- Face recognition
- Event bus
- Ved notifications

Then expand:

Front door
Living room
Kitchen
Other coverage areas

## Phase 8 - GPU

Only after measuring workloads:

- Dedicated GPU server
- Local LLM
- Vision models
- STT
- TTS
- Embeddings

## Phase 9 - Displays

Build:

- TV/display detection
- Display MCP
- Browser/tab control
- Visual cards
- Camera feed display
- Web research display
- Match scorecards
- Photo presentation

## Phase 10 - Proactive Ved

Build:

- Event-driven actions
- Scheduled tasks
- Context-aware notifications
- Device awareness
- Long-running tasks
- Personal routines

## Phase 11 - Advanced AI

Experiment with:

- FineWeb
- Custom tokenizer
- Small model training
- Fine-tuning
- Synthetic data
- Local specialized models

---

# 27. First Concrete Milestone

Do not start with cameras, GPUs, or massive datasets.

The first useful milestone should be:

1. Next.js PWA
2. Python/FastAPI backend
3. LLM connection
4. Streaming response
5. MCP client
6. One custom MCP server
7. One useful tool, such as reminders
8. PostgreSQL
9. Conversation history

Example:

User:
"Ved, remind me at 8 PM to call Mom."

Ved:
"Certainly, sir. I'll remind you at 8 PM."

Behind the scenes:

Next.js
   ->
FastAPI
   ->
Agent
   ->
LLM
   ->
MCP
   ->
Reminder server
   ->
Database

Once this works reliably, the architecture has its foundation.

---

# 28. Long-Term Target

The eventual system should feel like this:

                      Ved
                       |
       +---------------+----------------+
       |               |                |
      BRAIN           MEMORY           SENSES
       |               |                |
      LLM          Personal DB       Cameras
      Vision       Photos            Microphones
      Speech       Documents         Sensors
                       |
       +---------------+----------------+
       |
      ACTIONS
       |
   +---+---+---+---+---+---+
   |   |   |   |   |   |   |
 Home Web Apps Calendar Files TV Phone

The user should not need to think about which service is responsible for a task.

The user simply talks to Ved.

Ved figures out:

- What the user wants
- What information is needed
- Which tools are needed
- Which tools can run in parallel
- Whether permission is required
- Where the result should be displayed
- Whether the task should continue in the background
- Whether the user should be notified

---

# 29. Design Principles

1. Build the agent before the foundation model.
2. Keep the frontend replaceable.
3. Keep MCP servers independent.
4. Keep the LLM replaceable.
5. Keep storage independent from application code.
6. Prefer event-driven architecture for home events.
7. Never give the LLM unrestricted system access.
8. Treat latency as a core feature.
9. Stream responses and tool progress.
10. Run independent tasks in parallel.
11. Process camera streams with specialized vision models rather than continuously feeding video to the LLM.
12. Start with one camera and expand.
13. Start with two SSDs, but plan for off-site backup.
14. Measure before buying expensive GPUs.
15. Keep private home services behind secure access controls.
16. Build everything modularly so the system can grow for years.

---

# 30. Ultimate Vision

The final system is a private personal AI infrastructure running from the user's home.

The old i7 server initially provides:

- Storage
- Database
- Backend
- MCP
- Automation
- Event handling
- Photo cloud

The future GPU server provides:

- Local LLM
- Computer vision
- Speech processing
- Embeddings

The phone provides:

- Ved interface
- Voice
- Notifications
- Camera/photo upload
- Remote access

The home provides:

- Cameras
- Sensors
- Displays
- Speakers
- Smart switches
- Appliances

And Ved connects all of it.

The core idea is:

                         YOU
                          |
                     "Hey Ved..."
                          |
                          v
                      Ved CORE
                          |
          +---------------+---------------+
          |               |               |
        THINK           REMEMBER        OBSERVE
          |               |               |
         LLM            Memory          Cameras
          |                               Sensors
          |                               Voice
          |
       DECIDE
          |
     +----+----+----------------+
     |         |                |
     v         v                v
    MCP      WEB             EVENTS
   TOOLS    SEARCH             |
     |         |               |
     +---------+---------------+
               |
             ACT
               |
       +-------+-------+
       |       |       |
      Home   Phone    TV
       |       |       |
       +-------+-------+
               |
          User's world

The system should become progressively more capable without requiring a complete rewrite.

The immediate goal is not "build Iron Man's JARVIS in one shot."

The goal is to build Ved one reliable capability at a time until all of these capabilities become one coherent system.
