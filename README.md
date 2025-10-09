# VRY - UI v2.13

A modern PySide6-based interface for VALORANT Rank Yoinker, providing real-time player statistics and match information directly from VALORANT's game client.

## Features

### Player Information Display
- Real-time rank and RR (Ranked Rating) tracking
- Peak rank with act/episode information
- Previous season ranks
- Headshot percentage and K/D ratios
- Win rate and match statistics
- Account levels and leaderboard positions
- Agent selection and team information
- **New: Earned RR tracking with AFK penalty display**
- **New: Rank display includes act/episode information**

### Match Integration
- Live match data during games
- Agent select information in pregame
- Party member tracking with visual indicators
- Weapon skin and buddy display
- Map information and current game state
- **New: Starting side detection (Attacker/Defender) in pregame**
- **Improved: Better handling of new agents and game content**

### User Interface
- Multiple themes: Dark, Light, Midnight, and VALORANT-themed
- Customizable table columns and display options
- Real-time status updates
- Console output with adjustable verbosity levels
- **New: Freeze table functionality to pause updates**
- **New: Custom theme editor**
- **Improved: Faster player display and table rendering**

### Web Integration
- Built-in Match Loadouts viewer
- VTL.lol player lookup integration
- Local web server for mobile access

### Additional Features
- Discord Rich Presence integration
- Automatic VALORANT client detection
- Export and logging capabilities
- **New: Resource usage monitoring with warnings**
- **Improved: Error handling for missing game data**
- **Improved: Incognito player privacy controls**

## Requirements

- Windows operating system
- VALORANT installed and running
- PySide6 and PySide6-addons (if running from source)

## Installation

Download the latest release executable or build from source using the provided Nuitka build script.

## Configuration

Run with `--config` flag for first-time setup or to modify settings. Configuration includes weapon selection, table customization, and feature toggles.

## Usage

1. Launch VALORANT
2. Run VRY - UI v2.13
3. The application will automatically detect your game state and display relevant player information
4. Switch between tabs for different views and features
5. Access settings through the menu bar for customization
6. Use the **Freeze Table** button to pause updates and inspect current data
7. Monitor real-time game status and starting side information

## Troubleshooting

### Common Issues

**"Unknown agent" errors:**
- The application now gracefully handles new agents not yet in the local database
- Players with unknown agents will display as "Unknown Agent" but the table will continue to load
- Agent data updates automatically when connected to the internet

**Table not loading:**
- Ensure VALORANT is running and you're logged in
- Check that the game state is detected (look at the status indicator)
- Use the refresh button to manually update data
- Check console tab for detailed error messages

**High resource usage:**
- The application includes resource monitoring that will warn if system resources are low
- Reduce console verbosity level in settings if needed
- Close other resource-intensive applications

## Support

For issues and feature requests, please check the console output for detailed error information and ensure you're running the latest version of the application.

 Join the community discord:         
 
[![Discord Banner 2][discord-banner]][discord-url]

## Disclaimer

 THIS PROJECT IS NOT ASSOCIATED OR ENDORSED BY RIOT GAMES. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
    
 Whilst effort has been made to abide by Riot's API rules; you acknowledge that use of this software is done so at your own risk.


[discord-shield]: https://img.shields.io/discord/872101595037446144?color=7289da&label=Support&logo=discord&logoColor=7289da&style=for-the-badge
[discord-url]: https://discord.gg/HeTKed64Ka
[discord-banner]: https://discordapp.com/api/guilds/872101595037446144/widget.png?style=banner2

[downloads-shield]: https://img.shields.io/github/downloads/zayKenyon/VALORANT-rank-yoinker/total?style=for-the-badge&logo=github
[downloads-url]: https://github.com/zayKenyon/VALORANT-rank-yoinker/releases/latest
