# Fortnite Multi-Bot Management System

A Discord bot-controlled system for managing multiple Fortnite lobby bots. Users interact exclusively through Discord commands to add Epic Games accounts, spawn bot instances, and customize bot appearance including skins, level, and crown wins.

## Features

- **Discord-Controlled**: All interactions via slash commands with ephemeral (private) messages
- **Multi-Bot Support**: Run multiple Fortnite bots simultaneously
- **Account Management**: Secure device auth flow for Epic Games accounts
- **Cosmetic Customization**: Interactive search for skins, back blings, pickaxes, and emotes
- **Preset System**: Save and load cosmetic configurations
- **Session Timeouts**: Automatic cleanup with configurable timeouts and extensions
- **Free Service**: Always free for all users

## Requirements

- Python 3.9+
- MongoDB 4.4+
- Discord Bot Token
- Minimum 2GB RAM

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/fortniteLobbyBot.git
   cd fortniteLobbyBot
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Generate encryption key**:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Copy the output to `ENCRYPTION_KEY` in your `.env` file.

6. **Run the bot**:
   ```bash
   python main.py
   ```

## Configuration

All configuration is done via environment variables. See `.env.example` for all options.

### Required Variables

| Variable | Description |
|----------|-------------|
| `MONGODB_URI` | MongoDB connection string |
| `DISCORD_BOT_TOKEN` | Your Discord bot token |
| `ENCRYPTION_KEY` | Fernet encryption key for credentials |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_GUILD_ID` | None | Restrict bot to specific server |
| `DEFAULT_SESSION_TIMEOUT` | 30 | Session timeout in minutes |
| `MAX_ACCOUNTS_PER_USER` | 5 | Max Epic accounts per user |
| `MAX_CONCURRENT_BOTS_PER_USER` | 3 | Max simultaneous bots per user |

## Discord Commands

### Account Management
- `/addaccount` - Add Epic Games account via device auth
- `/confirmauth <code>` - Complete account authorization
- `/listaccounts` - Show all connected accounts
- `/removeaccount <username>` - Remove an account
- `/testaccount <username>` - Test connection status

### Bot Control
- `/startbot <username>` - Start a specific bot
- `/stopbot <username>` - Stop a specific bot
- `/startall` - Start all bots
- `/stopall` - Stop all bots
- `/botstatus [username]` - Show bot status
- `/extend <username>` - Extend session timeout

### Cosmetics
- `/setskin <username>` - Change outfit (interactive search)
- `/setbackbling <username>` - Change back bling
- `/setpickaxe <username>` - Change pickaxe
- `/emote <username>` - Perform emote
- `/setlevel <username> <level>` - Set battle pass level (1-200)
- `/setcrowns <username> <count>` - Set crown wins count
- `/synccosmetics <from> <to|all>` - Copy cosmetics between bots

### Presets
- `/savepreset <name> <username>` - Save current cosmetics
- `/loadpreset <name> <username|all>` - Apply preset
- `/listpresets` - Show all presets
- `/deletepreset <name>` - Delete a preset

### Utility
- `/help [command]` - Show help information
- `/stats` - Show your statistics
- `/ping` - Check bot latency

## Project Structure

```
fortniteLobbyBot/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment config
├── .gitignore             # Git ignore rules
├── config/
│   ├── __init__.py
│   └── settings.py        # Configuration management
├── database/
│   ├── __init__.py
│   ├── models.py          # Pydantic models
│   └── service.py         # MongoDB operations
├── bot/
│   ├── __init__.py
│   ├── instance_manager.py # Fortnite bot management
│   ├── cosmetic_search.py  # Cosmetic search system
│   └── device_auth.py      # Epic Games authentication
├── discord_bot/
│   ├── __init__.py
│   ├── views.py           # Discord UI components
│   └── commands/
│       ├── __init__.py
│       ├── account_commands.py
│       ├── bot_commands.py
│       ├── cosmetic_commands.py
│       ├── preset_commands.py
│       └── utility_commands.py
├── services/
│   ├── __init__.py
│   └── timeout_monitor.py  # Session timeout handling
└── utils/
    ├── __init__.py
    ├── encryption.py       # Credential encryption
    └── helpers.py          # Utility functions
```

## Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token to your `.env` file
5. Enable the following under "Privileged Gateway Intents":
   - None required (we only use slash commands)
6. Go to "OAuth2" > "URL Generator"
7. Select scopes: `bot`, `applications.commands`
8. Select permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
9. Use the generated URL to invite the bot to your server

## Security

- All Epic credentials are encrypted using Fernet symmetric encryption
- Credentials are never logged or displayed
- All Discord responses are ephemeral (only visible to command user)
- Rate limiting prevents abuse
- Users can only access their own data

## License

This project is for educational purposes. Use responsibly and in accordance with Epic Games' Terms of Service.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Epic Games, Inc. or Fortnite. Use at your own risk. Account bans or restrictions may occur.
