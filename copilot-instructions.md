# Fortnite Multi-Bot Management System - Complete Project Specification

## Project Overview

A Discord bot-controlled system for managing multiple Fortnite lobby bots. Users interact exclusively through Discord commands in a public server to add Epic Games accounts, spawn bot instances individually or as groups, and customize bot appearance including skins, level, and crown wins. All interactions use ephemeral messages and message editing to keep channels clean. The system runs as a single Python process connected to an external MongoDB database with all configuration managed server-side via environment variables.

-----

## System Requirements

### Infrastructure

- Single Python server instance (3.9+)
- External MongoDB database (4.4+)
- Discord Bot Token (provided via environment)
- Minimum 2GB RAM (scales with concurrent bot count)
- 2+ CPU cores recommended

### Technology Stack

- **discord.py** - Discord bot framework (primary interface)
- **fortnitepy** - Fortnite API integration
- **Motor** - Async MongoDB driver
- **cryptography** - Credential encryption
- **asyncio** - Concurrent bot management
- **fuzzywuzzy** - Fuzzy cosmetic search

### Control Interface

- **Discord Server Only** - No web dashboard, no DMs
- **Ephemeral Messages** - All responses visible only to command user
- **Message Editing** - Interactive flows edit existing messages
- **Public Server Commands** - All commands run in server channels
- **Free Service** - Always free for all users

-----

## Core Functionality

### 1. User Management

**Discord-Based Identity:**

- Users identified by Discord User ID
- No registration needed
- User profile auto-created on first command
- All data tied to Discord ID

### 2. Epic Games Account Management

**Adding Accounts (Device Auth Flow):**

1. User runs `/addaccount` in server
1. Bot sends ephemeral message with Epic device auth link
1. User visits link and authorizes
1. Bot automatically retrieves Epic username
1. Credentials encrypted and stored
1. Confirmation message edited to show Epic username

**Account Commands:**

- `/addaccount` - Add new Epic account via device auth
- `/listaccounts` - Show all connected accounts (ephemeral embed)
- `/removeaccount <epic_username>` - Remove account with confirmation
- `/testaccount <epic_username>` - Test connection status

**Account Display:**

- Ephemeral embed listing all accounts
- Shows: Epic username, status (🟢 Active, 🔴 Error, ⚫ Banned)
- Last used timestamp and total sessions
- Interactive buttons: Test, Remove

### 3. Bot Instance Management

**Bot Control Commands:**

- `/startbot <epic_username>` - Start specific bot
- `/stopbot <epic_username>` - Stop specific bot
- `/startall` - Start all user’s bots
- `/stopall` - Stop all user’s bots
- `/botstatus [epic_username]` - Show bot status (all or specific)

**Bot Status Display (Ephemeral):**

```
🤖 Your Fortnite Bots

━━━━━━━━━━━━━━━━━━━━
🟢 PlayerName123 (ONLINE)
Uptime: 15m 23s
Timeout: 14m 37s remaining
Party: Solo
Skin: Galaxy Skin
Level: 200 | Crowns: 50

[Stop] [Extend] [Edit Cosmetics]

━━━━━━━━━━━━━━━━━━━━
⚫ AltPlayer456 (OFFLINE)
Last used: 2 hours ago

[Start Bot]

━━━━━━━━━━━━━━━━━━━━
🔄 Refresh
```

**Features:**

- Real-time status updates
- Interactive buttons for quick actions
- Multiple concurrent bots per user (server-configured limit)
- Each bot is separate fortnitepy client instance

### 4. Interactive Cosmetic Customization

**All cosmetic changes use search-and-select flow with message editing.**

**Cosmetic Commands:**

- `/setskin <epic_username>` - Change outfit (interactive search)
- `/setbackbling <epic_username>` - Change back bling (interactive search)
- `/setpickaxe <epic_username>` - Change pickaxe (interactive search)
- `/emote <epic_username>` - Perform emote (interactive search)
- `/setlevel <epic_username> <level>` - Set battle pass level (1-200)
- `/setcrowns <epic_username> <count>` - Set crown wins count

**Interactive Search Flow Example:**

**Step 1 - User Command:**

```
User: /setskin PlayerName123
Bot: [Ephemeral Message]
🎨 Search for a skin
[Modal opens for text input]
```

**Step 2 - User Searches:**

```
User types: "galaxy"
Bot: [Edits same message]
🔍 Search results for "galaxy":

[Button: Galaxy Scout 🟣]
[Button: Galaxy Grappler 🟣]
[Button: Galaxy Skin 🟪]
[Button: Iridescent Galaxy 🟪]

◀️ Previous | Page 1/1 | Next ▶️
❌ Cancel
```

**Step 3 - User Selects:**

```
User: [Clicks "Galaxy Skin 🟪"]
Bot: [Edits same message]
✅ Skin changed to Galaxy Skin

[Embed Preview]
Bot: PlayerName123
Skin: Galaxy Skin (Legendary)
Applied at: 2:34 PM
```

**Search Features:**

- Fuzzy matching for partial names
- Case-insensitive search
- 25 results per page with pagination
- Clickable buttons for selection
- Cosmetic preview with rarity and description
- Cancel button to abort

**Bulk Operations:**

- `/synccosmetics <from_username> <to_username|all>` - Copy cosmetics between bots
- `/setskinsall` - Apply same skin to all active bots (with search)

### 5. Preset System

**Preset Commands:**

- `/savepreset <name> <epic_username>` - Save current cosmetics as preset
- `/loadpreset <name> <epic_username|all>` - Apply preset to bot(s)
- `/listpresets` - Show all saved presets with interactive buttons
- `/deletepreset <name>` - Delete preset with confirmation

**Preset Contents:**

- Skin, back bling, pickaxe, emote
- Battle pass level
- Crown wins count

**Preset Display (Ephemeral):**

```
📋 Your Presets

━━━━━━━━━━━━━━━━━━━━
🌌 Galaxy Loadout
Skin: Galaxy Skin
Level: 200 | Crowns: 50

[Load to Bot] [Delete]

━━━━━━━━━━━━━━━━━━━━
🔥 Tryhard Setup
Skin: Soccer Skin
Level: 150 | Crowns: 25

[Load to Bot] [Delete]
```

### 6. Session Timeout System

**Server-Configured Timeouts (NOT User-Configurable):**

- Default timeout: Set in ENV (e.g., 30 minutes)
- Warning threshold: Set in ENV (e.g., 5 minutes before timeout)
- Extension duration: Set in ENV (e.g., +15 minutes per extend)
- Max extensions: Set in ENV (e.g., 2 per session)

**Activities That Reset Timer:**

- Any cosmetic change command
- Party join/leave events
- Friend requests accepted
- Manual keepalive/extend commands
- Any Discord command interaction with that bot

**Timeout Warnings:**

- Sent as ephemeral message in last active channel
- Triggered at configured threshold (e.g., 5 min remaining)
- Message: “⏰ Your bot PlayerName123 will stop in 5 minutes. Use `/extend PlayerName123` to continue.”

**Timeout Actions:**

- Graceful shutdown: leave parties, disconnect
- Session logged with reason: “timeout”
- Next `/botstatus` shows: “⚫ PlayerName123 (OFFLINE - Timed out)”
- User can restart immediately with `/startbot`

**Session Commands:**

- `/extend <epic_username>` - Add extension time (shows remaining time)
- `/keepalive <epic_username>` - Reset timer to full duration

### 7. Message Management

**Ephemeral Messages:**

- ALL responses are ephemeral (only command user sees them)
- Keeps server channels completely clean
- No spam or persistent messages
- Private interactions in public server

**Message Editing:**

- Search flows edit the same message
- Confirmation dialogs edit to show results
- Status updates edit existing status message
- Loading indicators while processing
- No new messages spawned during interactions

**Clean Channel Policy:**

- Commands create instant ephemeral response
- Original slash command visible briefly
- No persistent bot messages remain in channels
- Users only see their own interactions

**No DM Usage:**

- Zero direct messages sent
- All notifications via ephemeral in server
- Timeout warnings in last active channel
- If user offline, notifications skipped

-----

## Database Schema (MongoDB)

### Collections

**users**

```javascript
{
  _id: ObjectId,
  discord_id: String (unique, indexed),
  discord_username: String,
  created_at: Date,
  last_active: Date,
  last_active_channel_id: String,  // For timeout warnings
  total_sessions: Number
}
```

**epic_accounts**

```javascript
{
  _id: ObjectId,
  discord_id: String (indexed),
  epic_username: String (indexed),      // Primary identifier
  epic_display_name: String,
  epic_account_id: String (unique),
  encrypted_credentials: String,        // Fernet encrypted device auth
  status: String,                       // 'active', 'error', 'banned'
  added_at: Date,
  last_used: Date,
  total_sessions: Number
}
```

**bot_sessions**

```javascript
{
  _id: ObjectId,
  account_id: ObjectId (indexed),
  discord_id: String (indexed),
  started_at: Date,
  ended_at: Date,
  last_activity: Date (indexed),
  status: String,                       // 'active', 'idle_warning', 'stopped'
  timeout_minutes: Number,              // From ENV at session start
  extensions_used: Number,
  current_cosmetics: {
    skin: String,
    skin_id: String,
    backbling: String,
    backbling_id: String,
    pickaxe: String,
    pickaxe_id: String,
    level: Number,
    crown_wins: Number
  },
  party_info: {
    in_party: Boolean,
    party_size: Number,
    is_leader: Boolean
  },
  termination_reason: String            // 'timeout', 'manual', 'error', 'crash'
}
```

**cosmetic_presets**

```javascript
{
  _id: ObjectId,
  discord_id: String (indexed),
  name: String,
  cosmetics: {
    skin: String,
    skin_id: String,
    backbling: String,
    backbling_id: String,
    pickaxe: String,
    pickaxe_id: String,
    level: Number,
    crown_wins: Number
  },
  created_at: Date,
  updated_at: Date
}
```

**cosmetic_cache**

```javascript
{
  _id: ObjectId,
  type: String (indexed),               // 'skin', 'backbling', 'pickaxe', 'emote'
  cosmetic_id: String (indexed),
  name: String,
  display_name: String,
  rarity: String,
  description: String,
  search_text: String (indexed),        // Lowercase for searching
  last_updated: Date
}
```

**activity_log**

```javascript
{
  _id: ObjectId,
  session_id: ObjectId,
  discord_id: String (indexed),
  action_type: String,                  // 'bot_start', 'cosmetic_change', etc.
  details: Object,
  timestamp: Date (indexed)
}
```

-----

## Discord Bot Commands

### Account Management

```
/addaccount
  Description: Add Epic Games account via device auth
  Ephemeral: Yes
  Flow: Device auth link → Auto-retrieve username → Confirm

/listaccounts
  Description: Show all connected Epic accounts
  Ephemeral: Yes
  Display: Embed with status, buttons for Test/Remove

/removeaccount <epic_username>
  Description: Remove an Epic account
  Ephemeral: Yes
  Confirmation: Yes/No buttons

/testaccount <epic_username>
  Description: Test account connection
  Ephemeral: Yes
  Result: ✅ Success or ❌ Failed (edits message)
```

### Bot Control

```
/startbot <epic_username>
  Description: Start a specific bot
  Ephemeral: Yes
  Process: "Starting..." → Edits to "✅ Bot started"

/stopbot <epic_username>
  Description: Stop a specific bot
  Ephemeral: Yes
  Process: "Stopping..." → Edits to "✅ Bot stopped"

/startall
  Description: Start all user's bots
  Ephemeral: Yes
  Process: Shows list of started bots

/stopall
  Description: Stop all user's bots
  Ephemeral: Yes
  Confirmation: Yes/No buttons

/botstatus [epic_username]
  Description: Show bot status (all or specific)
  Ephemeral: Yes
  Display: Embed with interactive buttons
  Features: Refresh button, Stop/Extend/Edit buttons
```

### Cosmetics (Interactive Search)

```
/setskin <epic_username>
  Description: Change bot outfit
  Ephemeral: Yes
  Flow: Modal search → Results buttons → Confirmation

/setbackbling <epic_username>
  Description: Change back bling
  Ephemeral: Yes
  Flow: Same as setskin

/setpickaxe <epic_username>
  Description: Change pickaxe
  Ephemeral: Yes
  Flow: Same as setskin

/emote <epic_username>
  Description: Perform emote
  Ephemeral: Yes
  Flow: Search → Bot performs emote → Confirmation

/setlevel <epic_username> <level>
  Description: Set battle pass level (1-200)
  Ephemeral: Yes
  Validation: Range check
  Result: Edits to "✅ Level set to <level>"

/setcrowns <epic_username> <count>
  Description: Set crown wins count
  Ephemeral: Yes
  Validation: Positive number
  Result: Edits to "✅ Crown wins set to <count>"

/synccosmetics <from_username> <to_username|all>
  Description: Copy cosmetics between bots
  Ephemeral: Yes
  Confirmation: Shows source cosmetics, Yes/No buttons
```

### Presets

```
/savepreset <name> <epic_username>
  Description: Save current cosmetics as preset
  Ephemeral: Yes
  Display: Shows what will be saved
  Confirmation: Yes/No buttons

/loadpreset <name> <epic_username|all>
  Description: Apply preset to bot(s)
  Ephemeral: Yes
  Display: Shows preset contents
  Confirmation: Yes/No buttons

/listpresets
  Description: Show all saved presets
  Ephemeral: Yes
  Display: Interactive list with Load/Delete buttons

/deletepreset <name>
  Description: Delete a preset
  Ephemeral: Yes
  Confirmation: Yes/No buttons
```

### Session Management

```
/extend <epic_username>
  Description: Reset activity timer
  Ephemeral: Yes
  Result: "✅ Timer reset to 30 minutes"
```

### Utility

```
/help [command]
  Description: Show help information
  Ephemeral: Yes
  Display: All commands or specific command details

/stats
  Description: Show user statistics
  Ephemeral: Yes
  Display: Total sessions, active bots, accounts

/ping
  Description: Check bot latency
  Ephemeral: Yes
  Result: Shows response time
```

-----

## Architecture Components

### 1. Main Application (main.py)

**Responsibilities:**

- Initialize Discord bot client
- Connect to MongoDB
- Register all commands and event handlers
- Start background tasks (timeout monitor)
- Initialize bot instance manager
- Handle graceful shutdown

**Key Modules:**

- Discord bot setup and configuration
- Command tree registration
- Event listener registration
- Background task scheduling
- Error handling and logging

### 2. Discord Bot Manager

**Responsibilities:**

- Process all Discord slash commands
- Create and manage ephemeral messages
- Handle interactive components (buttons, modals, select menus)
- Edit messages for interactive flows
- Search result pagination
- User permission and rate limit checks

**Key Features:**

- Ephemeral message builder
- Button/select menu component builders
- Modal form creation
- Message editing system
- Cosmetic search pagination handler
- Error message formatting

### 3. Bot Instance Manager

**Responsibilities:**

- Maintain registry of active fortnitepy bots
- Spawn new bot instances
- Track session metadata
- Handle bot lifecycle events
- Graceful shutdown on timeout/stop
- Memory and resource cleanup

**Key Classes:**

```python
class BotInstanceManager:
    - active_bots: Dict[account_id, FortniteBotInstance]
    - start_bot(account_id, credentials)
    - stop_bot(account_id, reason)
    - get_bot_status(account_id)
    - check_activity(account_id)
    
class FortniteBotInstance:
    - client: fortnitepy.Client
    - session_start: datetime
    - last_activity: datetime
    - change_skin(skin_id)
    - change_backbling(backbling_id)
    - set_level(level)
    - set_crown_wins(count)
    - update_activity()
```

### 4. Cosmetic Search System

**Responsibilities:**

- Search cosmetics by partial name (fuzzy matching)
- Paginate results (25 per page)
- Cache cosmetics in MongoDB
- Fetch from Fortnite API when needed
- Sort by rarity and relevance

**Features:**

- Case-insensitive search
- Fuzzy string matching (fuzzywuzzy)
- Result caching for performance
- Category filtering (skin, backbling, pickaxe, emote)
- Rarity-based sorting

**Search Algorithm:**

```python
def search_cosmetics(query, type, limit=25, page=1):
    # Lowercase search
    # Fuzzy match against cached cosmetics
    # Sort by relevance score + rarity
    # Paginate results
    # Return list of cosmetics with IDs
```

### 5. Timeout Monitor

**Background Task:**

- Runs every 60 seconds
- Queries active sessions from MongoDB
- Calculates time since last activity
- Sends warnings at threshold (e.g., 5 min)
- Initiates shutdown for expired sessions
- Updates database with termination reason
- Sends ephemeral warnings in last active channel

**Logic:**

```python
async def timeout_monitor():
    while True:
        await asyncio.sleep(60)
        active_sessions = await get_active_sessions()
        
        for session in active_sessions:
            time_remaining = calculate_remaining_time(session)
            
            if time_remaining <= 0:
                # Timeout reached
                await stop_bot(session.account_id, reason='timeout')
                await send_timeout_notification(session.discord_id)
                
            elif time_remaining <= WARNING_THRESHOLD:
                # Warning
                await send_warning_notification(session.discord_id, time_remaining)
```

### 6. Encryption Module

**Responsibilities:**

- Encrypt Epic credentials using Fernet
- Decrypt credentials for bot spawning
- Secure key management from ENV

**Functions:**

```python
def encrypt_credentials(device_id, account_id, secret) -> str:
    # Return encrypted string

def decrypt_credentials(encrypted_data) -> dict:
    # Return {device_id, account_id, secret}
```

### 7. Database Service

**Responsibilities:**

- Motor async MongoDB client
- Connection pooling
- Query builders for common operations
- Index management
- Transaction support

**Key Operations:**

- CRUD for users, accounts, sessions, presets
- Efficient queries with indexes
- Batch operations for bulk updates
- Error handling and retry logic

-----

## Environment Variables Configuration

```bash
# MongoDB Connection
MONGODB_URI=mongodb://user:pass@host:27017/fortnite_bots

# Discord Bot
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=your_server_id  # Optional: restrict to specific server

# Security
ENCRYPTION_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Timeout Settings (SERVER-CONTROLLED, NOT USER-CONFIGURABLE)
DEFAULT_SESSION_TIMEOUT=30              # minutes
TIMEOUT_WARNING_THRESHOLD=5             # minutes before timeout to warn
SESSION_EXTENSION_DURATION=15           # minutes added per /extend command
MAX_EXTENSIONS_PER_SESSION=2            # max times user can extend

# Resource Limits (SERVER-CONTROLLED)
MAX_ACCOUNTS_PER_USER=5                 # max Epic accounts per Discord user
MAX_CONCURRENT_BOTS_PER_USER=3          # max simultaneous bots per user
MAX_CONCURRENT_BOTS_GLOBAL=50           # total across all users
COMMAND_RATE_LIMIT=10                   # commands per minute per user

# Cosmetic Search Settings
COSMETIC_RESULTS_PER_PAGE=25
COSMETIC_CACHE_REFRESH_HOURS=24

# System Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
```

-----

## Required Python Packages (requirements.txt)

```
discord.py==2.3.2
fortnitepy==3.6.6
motor==3.3.2
cryptography==41.0.7
pydantic==2.5.0
pydantic-settings==2.1.0
python-dotenv==1.0.0
fuzzywuzzy==0.18.0
python-Levenshtein==0.21.1
aiofiles==23.2.1
```

-----

## MongoDB Indexes (Required for Performance)

```javascript
// Users
db.users.createIndex({ discord_id: 1 }, { unique: true })

// Epic Accounts
db.epic_accounts.createIndex({ discord_id: 1 })
db.epic_accounts.createIndex({ epic_account_id: 1 }, { unique: true })
db.epic_accounts.createIndex({ epic_username: 1, discord_id: 1 })

// Bot Sessions
db.bot_sessions.createIndex({ discord_id: 1 })
db.bot_sessions.createIndex({ account_id: 1 })
db.bot_sessions.createIndex({ last_activity: 1 })
db.bot_sessions.createIndex({ status: 1 })

// Cosmetic Presets
db.cosmetic_presets.createIndex({ discord_id: 1 })
db.cosmetic_presets.createIndex({ name: 1, discord_id: 1 })

// Cosmetic Cache
db.cosmetic_cache.createIndex({ type: 1, cosmetic_id: 1 }, { unique: true })
db.cosmetic_cache.createIndex({ type: 1, search_text: 1 })

// Activity Log
db.activity_log.createIndex({ discord_id: 1 })
db.activity_log.createIndex({ timestamp: -1 })
```

-----

## Security Requirements

### Credential Protection

- All Epic credentials encrypted with Fernet (symmetric encryption)
- Encryption key stored in environment variable (never in code/database)
- Credentials never logged or displayed to users
- Secure device auth flow (Epic’s official method)

### Discord Security

- All responses ephemeral (no data leakage in channels)
- Rate limiting per user (prevent spam/abuse)
- Command permission checks (users only access own data)
- Input validation on all commands
- SQL injection prevention (MongoDB parameterization)

### Rate Limiting

- Discord commands: Built-in cooldowns per command
- Bot operations: 10 per minute per user (configurable)
- Global rate limits to prevent server overload
- Automatic temporary bans for abuse

### Authorization

- Users identified by Discord ID
- Users can only access their own accounts and bots
- Account ownership validation on all operations
- No cross-user data access

-----

## Error Handling

### Common Error Scenarios

**Epic Authentication Failed:**

```
❌ Failed to authenticate with Epic Games
The authorization may have expired or been invalid.
Please try `/addaccount` again.
```

**Bot Already Running:**

```
⚠️ Bot "PlayerName123" is already online
Use `/botstatus` to view it or `/stopbot PlayerName123` to stop it first.
```

**Max Bots Reached:**

```
🚫 Maximum concurrent bots reached (3/3)
Stop a bot with `/stopbot <username>` to start another.
```

**Max Accounts Reached:**

```
🚫 Maximum accounts reached (5/5)
Remove an account with `/removeaccount <username>` to add another.
```

**Account Not Found:**

```
❌ Account "PlayerName123" not found
Use `/listaccounts` to see your connected accounts.
```

**Bot Not Online:**

```
⚠️ Bot "PlayerName123" is not currently online
Use `/startbot PlayerName123` to start it first.
```

**Cosmetic Not Found:**

```
❌ No cosmetics found matching "xyz"
Try a different search term or check spelling.
```

**Max Extensions Reached:**

```
🚫 Maximum extensions reached for this session (2/2)
The bot will stop when the timeout is reached.
```

### User-Friendly Error Messages

- Clear, actionable descriptions
- Suggestions for resolution
- Relevant commands to fix the issue
- No technical jargon or stack traces

### Logging Strategy

- **DEBUG**: Bot state changes, activity updates, search queries
- **INFO**: Bot starts/stops, user actions, command usage
- **WARNING**: Timeout warnings, rate limit approaches, retries
- **ERROR**: Failed operations, authentication errors, crashes
- **CRITICAL**: Database failures, Discord connection loss

-----

## Development Phases

### Phase 1: Core Infrastructure (Week 1)

- Discord bot initialization and command framework
- MongoDB connection and basic models
- User and account management
- Device auth flow implementation
- Basic error handling

### Phase 2: Bot Management (Week 2)

- fortnitepy integration
- Bot instance manager
- Start/stop single bot
- Session tracking in MongoDB
- Basic status display

### Phase 3: Multiple Bots (Week 3)

- Concurrent bot handling
- Start/stop all commands
- Bot status for multiple bots
- Resource limit enforcement

### Phase 4: Cosmetic System (Week 4)

- Cosmetic cache setup
- Interactive search flow with modals
- Pagination system
- Apply cosmetics to bots
- Level and crown wins modification

### Phase 5: Timeout System (Week 5)

- Activity tracking
- Timeout monitor background task
- Warning notifications (ephemeral)
- Extension and keepalive commands
- Graceful shutdown logic

### Phase 6: Presets (Week 6)

- Save/load preset system
- Preset management commands
- Apply to single or all bots
- Interactive preset list

### Phase 7: Polish & Testing (Week 7)

- Comprehensive error handling
- Input validation
- Rate limiting
- Security hardening
- Performance optimization
- Documentation

-----

## Testing Requirements

### Unit Tests

- Discord command parsing and validation
- Encryption/decryption functions
- Timeout calculation logic
- Cosmetic search algorithm
- Database query functions

### Integration Tests

- Full bot start/stop cycle
- Device auth flow (mocked)
- Cosmetic change workflow
- Timeout trigger sequence
- Multi-bot operations
- Preset save/load cycle

### Load Tests

- 20+ concurrent bot sessions
- Multiple simultaneous users (10+)
- Cosmetic search performance
- Database query performance
- Memory leak detection
- Rate limit enforcement

### User Experience Tests

- Ephemeral message flow
- Message editing responsiveness
- Search result pagination
- Button interaction reliability
- Error message clarity

-----

## Known Limitations

### Epic Games API

- Rate limiting from Epic’s servers
- Potential for API changes
- Device auth tokens can expire
- Account ban risk (user responsibility)

### Discord Limitations

- 25 buttons max per message (pagination needed)
- 3 second interaction response time limit
- Ephemeral messages can’t be seen by others (by design)
- Message size limits (embeds have field limits)

### System Limitations

- Single-process architecture (vertical scaling only)
- Each bot consumes 100-150MB RAM
- MongoDB as single point of failure
- No automatic credential refresh (user must re-auth)

### Scalability

- Estimate: 50-100 concurrent bots per server max
- Database I/O can become bottleneck
- fortnitepy client limitations
- Discord rate limits on messages

-----

## Future Enhancements

### Potential Features

- Party management (invite friends to bot’s party)
- Scheduled bot sessions (start at specific times)
- Bot behavior customization (auto-emotes, responses)
- Statistics dashboard (usage analytics)
- Bot grouping/tagging system
- Shared presets between users
- Admin commands for server management
- Whitelist/blacklist system
- Premium tier system (if needed)

### Advanced Features

- Multi-server support with shared database
- Load balancing across multiple Python instances
- Automatic credential refresh
- Voice channel integration
- Webhook notifications for status
- Mobile app companion (React Native)

-----

## Success Metrics

### Key Performance Indicators

- Average concurrent bots per user
- Session duration averages
- Command usage frequency
- Timeout frequency (target: <10%)
- User retention rate
- Error rate by command (target: <1%)
- Average response time (target: <2s)

### Monitoring Requirements

- Active bot count (real-time)
- Memory usage per bot
- Database connection pool status
- Command execution times
- Error rates and types
- User activity patterns
- Timeout statistics

-----

## Summary

This specification outlines a complete Fortnite lobby bot management system controlled exclusively via Discord bot in a free public server environment. Users add Epic Games accounts (identified by Epic username), spawn multiple controllable lobby bots, and customize their appearance including skins, level, and crown wins through interactive Discord commands with ephemeral messages and message editing. The system features server-configured automatic timeouts, interactive cosmetic search with pagination, and a preset system. All interactions are ephemeral to keep server channels clean, with no DMs or persistent messages. The entire system runs as a single Python process using discord.py and fortnitepy, connected to an external MongoDB database, with all configuration managed through environment variables.