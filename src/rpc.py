from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, InvalidID
import nest_asyncio
import time

class Rpc():
    def __init__(self, map_dict, gamemodes, colors, log):
        nest_asyncio.apply()
        self.log = log
        self.discord_running = True
        try:
            self.rpc = Presence("1012402211134910546")
            self.rpc.connect()
            self.log("Connected to discord")
        except DiscordNotFound:
            self.log("Failed connecting to discord")
            self.discord_running = False
        self.gamemodes = gamemodes
        self.map_dict = map_dict
        self.data = {
            "agent": None,
            "rank": None,
            "rank_name": None
        }
        self.last_presence_data = {}
        self.colors = colors
        self.start_time = time.time()

    def set_data(self, data):
        self.data = self.data | data
        self.log("New data set in RPC")
        self.set_rpc(self.last_presence_data)

    def _get_session_state(self, presence):
        """Extract sessionLoopState from either nested or flat presence format."""
        match_data = presence.get("matchPresenceData") or {}
        state = match_data.get("sessionLoopState") or presence.get("sessionLoopState")
        return state

    def _get_match_map(self, presence):
        """Extract matchMap from either nested or flat presence format."""
        match_data = presence.get("matchPresenceData") or {}
        return match_data.get("matchMap") or presence.get("matchMap", "")

    def set_rpc(self, presence):
        if not presence:
            self.last_presence_data = presence
            return

        if self.discord_running:
            try:
                if not presence.get("isValid"):
                    self.last_presence_data = presence
                    return

                # Support both nested (matchPresenceData / partyPresenceData) and
                # flat presence formats produced by different Riot client versions.
                party_data = presence.get("partyPresenceData") or {}
                session_state = self._get_session_state(presence)

                if not session_state:
                    self.last_presence_data = presence
                    return

                if session_state == "INGAME":
                    if not self.data.get("agent"):
                        agent_img = None
                        agent = None
                    else:
                        agent = self.colors.agent_dict.get(self.data.get("agent").lower())
                        agent_img = agent.lower().replace("/", "") if agent else None

                    if presence.get("provisioningFlow") == "CustomGame":
                        gamemode = "Custom Game"
                    else:
                        gamemode = self.gamemodes.get(presence.get('queueId', ''), "Unknown")

                    score_ally = presence.get('partyOwnerMatchScoreAllyTeam', 0)
                    score_enemy = presence.get('partyOwnerMatchScoreEnemyTeam', 0)
                    details = f"{gamemode} // {score_ally} - {score_enemy}"

                    match_map_url = self._get_match_map(presence)
                    mapText = self.map_dict.get(match_map_url.lower()) if match_map_url else None

                    if mapText == "The Range":
                        mapImage = "splash_range_square"
                        details = "in Range"
                        agent_img = str(self.data.get("rank"))
                        agent = self.data.get("rank_name")
                    elif mapText:
                        mapImage = f"splash_{mapText}_square".lower()
                    else:
                        mapText = None
                        mapImage = None

                    if self.last_presence_data and self._get_session_state(self.last_presence_data) != session_state:
                        self.start_time = time.time()

                    self.rpc.update(
                        state=f"In a Party ({party_data.get('partySize', 1)} of {party_data.get('maxPartySize', 5)})",
                        details=details,
                        large_image=mapImage,
                        large_text=mapText,
                        small_image=agent_img,
                        small_text=agent,
                        start=self.start_time,
                        buttons=[{"label": "What's this? 👀", "url": "https://vry-ui.vercel.app/"}]
                    )
                    self.log("RPC in-game data update")

                elif session_state == "MENUS":
                    if presence.get("isIdle"):
                        image = "game_icon_yellow"
                        image_text = "VALORANT - Idle"
                    else:
                        image = "game_icon"
                        image_text = "VALORANT - Online"

                    if party_data.get("partyAccessibility") == "OPEN":
                        party_string = "Open Party"
                    else:
                        party_string = "Closed Party"

                    if party_data.get("partyState") == "CUSTOM_GAME_SETUP":
                        gamemode = "Custom Game"
                    else:
                        gamemode = self.gamemodes.get(presence.get('queueId', ''), "Unknown")

                    self.rpc.update(
                        state=f"{party_string} ({party_data.get('partySize', 1)} of {party_data.get('maxPartySize', 5)})",
                        details=f" Lobby - {gamemode}",
                        large_image=image,
                        large_text=image_text,
                        small_image=str(self.data.get("rank")),
                        small_text=self.data.get("rank_name"),
                        buttons=[{"label": "What's this? 👀", "url": "https://vry-ui.vercel.app/"}]
                    )
                    self.log("RPC menu data update")

                elif session_state == "PREGAME":
                    if presence.get("provisioningFlow") == "CustomGame" or \
                            party_data.get("partyState") == "CUSTOM_GAME_SETUP":
                        gamemode = "Custom Game"
                    else:
                        gamemode = self.gamemodes.get(presence.get('queueId', ''), "Unknown")

                    match_map_url = self._get_match_map(presence)
                    mapText = self.map_dict.get(match_map_url.lower()) if match_map_url else None
                    mapImage = f"splash_{mapText}_square".lower() if mapText else None

                    self.rpc.update(
                        state=f"In a Party ({party_data.get('partySize', 1)} of {party_data.get('maxPartySize', 5)})",
                        details=f"Agent Select - {gamemode}",
                        large_image=mapImage,
                        large_text=mapText,
                        small_image=str(self.data.get("rank")),
                        small_text=self.data.get("rank_name"),
                        buttons=[{"label": "What's this? 👀", "url": "https://vry-ui.vercel.app/"}]
                    )
                    self.log("RPC agent-select data update")

            except InvalidID:
                self.discord_running = False
        else:
            try:
                self.rpc = Presence("1012402211134910546")
                self.rpc.connect()
                self.discord_running = True
                self.log("Reconnected to discord")
                self.set_rpc(presence)
            except DiscordNotFound:
                self.discord_running = False

        self.last_presence_data = presence

    def close(self):
        """Safely close the Discord RPC connection."""
        if self.discord_running:
            try:
                self.rpc.close()
            except Exception:
                pass
            finally:
                self.discord_running = False