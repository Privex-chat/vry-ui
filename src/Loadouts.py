import sys
import time
import asyncio
import aiohttp
from colr import color
from src.constants import sockets, hide_names
from threading import Lock

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class Loadouts:
    def __init__(self, Requests, log, colors, Server, current_map):
        self.Requests = Requests
        self.log = log
        self.colors = colors
        self.Server = Server
        self.current_map = current_map

        self.buddy_cache = {}
        self.cache_lock = Lock()
        
        # Lazy session creation
        self._session = None
        self._loop = None
        self._session_lock = Lock()
        
        # Cache static API data
        self._weapons_cache = None
        self._sprays_cache = None
        self._agents_cache = None
        self._titles_cache = None
        self._playercards_cache = None
        
    def _get_loop(self):
        """Get or create event loop for current thread"""
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _preload_buddies(self):
        """Preload buddy data into cache"""
        try:
            session = await self._get_session()
            async with session.get("https://valorant-api.com/v1/buddies") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == 200 and data.get("data"):
                        with self.cache_lock:
                            for buddy in data["data"]:
                                self.buddy_cache[buddy["uuid"]] = {
                                    "displayName": buddy["displayName"],
                                    "displayIcon": buddy["displayIcon"]
                                }
                        self.log(f"Cached {len(self.buddy_cache)} buddies")
        except Exception as e:
            self.log(f"Failed to preload buddies: {e}")

    async def _get_cached_api_data(self, endpoint, cache_attr):
        """Fetch and cache API data"""
        cached = getattr(self, cache_attr, None)
        if cached:
            return cached
            
        try:
            session = await self._get_session()
            async with session.get(f"https://valorant-api.com/v1/{endpoint}") as response:
                if response.status == 200:
                    data = await response.json()
                    setattr(self, cache_attr, data)
                    return data
        except Exception as e:
            self.log(f"API fetch error ({endpoint}): {e}")
        return None

    async def get_buddy_info_batch(self, buddy_uuids):
        if not buddy_uuids:
            return {}

        results = {}
        uncached = []

        with self.cache_lock:
            for uuid in buddy_uuids:
                if uuid in self.buddy_cache:
                    results[uuid] = self.buddy_cache[uuid]
                else:
                    uncached.append(uuid)

        if not uncached:
            return results

        session = await self._get_session()
        
        async def fetch_buddy(uuid):
            try:
                async with session.get(f"https://valorant-api.com/v1/buddies/{uuid}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == 200 and data.get("data"):
                            info = {
                                "displayName": data["data"]["displayName"],
                                "displayIcon": data["data"]["displayIcon"]
                            }
                            with self.cache_lock:
                                self.buddy_cache[uuid] = info
                            return uuid, info
            except Exception:
                pass
            return uuid, None

        fetch_results = await asyncio.gather(*[fetch_buddy(u) for u in uncached])
        for uuid, info in fetch_results:
            if info:
                results[uuid] = info

        return results

    def get_match_loadouts(self, match_id, players, weaponChoose, valoApiSkins, names, state="game"):
        loop = self._get_loop()
        
        # Preload buddies on first call
        if not self.buddy_cache:
            loop.run_until_complete(self._preload_buddies())
            
        return loop.run_until_complete(
            self._get_match_loadouts_async(match_id, players, weaponChoose, valoApiSkins, names, state)
        )

    async def _get_match_loadouts_async(self, match_id, players, weaponChoose, valoApiSkins, names, state="game"):
        playersBackup = players
        weaponLists = {}

        # Get weapons from cache or fetch
        weapons_data = await self._get_cached_api_data("weapons", "_weapons_cache")
        if not weapons_data:
            return [{}, {}]
        valApiWeapons = weapons_data

        if state == "game":
            team_id = "Blue"
            PlayerInventorys = self.Requests.fetch("glz", f"/core-game/v1/matches/{match_id}/loadouts", "get")
        elif state == "pregame":
            pregame_stats = players
            players = players["AllyTeam"]["Players"]
            team_id = pregame_stats['Teams'][0]['TeamID']
            PlayerInventorys = self.Requests.fetch("glz", f"/pregame/v1/matches/{match_id}/loadouts", "get")

        for i, player in enumerate(players):
            if team_id == "Red":
                invindex = i + len(players) - len(PlayerInventorys["Loadouts"])
            else:
                invindex = i
            inv = PlayerInventorys["Loadouts"][invindex]
            if state == "game":
                inv = inv["Loadout"]
                
            for weapon in valApiWeapons["data"]:
                if weapon["displayName"].lower() == weaponChoose.lower():
                    skin_id = inv["Items"][weapon["uuid"].lower()]["Sockets"]["bcef87d6-209b-46c6-8b19-fbe40bd95abc"]["Item"]["ID"]
                    for skin in valoApiSkins.json()["data"]:
                        if skin_id.lower() == skin["uuid"].lower():
                            rgb_color = self.colors.get_rgb_color_from_skin(skin["uuid"].lower(), valoApiSkins)
                            skin_display_name = skin["displayName"].replace(f" {weapon['displayName']}", "")
                            weaponLists[players[i]["Subject"]] = color(skin_display_name, fore=rgb_color)
                    break

        final_json = await self.convertLoadoutToJsonArray(PlayerInventorys, playersBackup, state, names, valApiWeapons)
        self.log(f"Loadout JSON generated for {len(final_json.get('Players', {}))} players")
        self.Server.send_payload("matchLoadout", final_json)
        return [weaponLists, final_json]

    async def convertLoadoutToJsonArray(self, PlayerInventorys, players, state, names, valApiWeapons):
        try:
            # Fetch all API data concurrently with caching
            sprays_data, agents_data, titles_data, cards_data = await asyncio.gather(
                self._get_cached_api_data("sprays", "_sprays_cache"),
                self._get_cached_api_data("agents", "_agents_cache"),
                self._get_cached_api_data("playertitles", "_titles_cache"),
                self._get_cached_api_data("playercards", "_playercards_cache")
            )
            
            if not all([sprays_data, agents_data, titles_data, cards_data]):
                return {"Players": {}, "time": int(time.time()), "map": self.current_map}
                
            valoApiSprays = sprays_data
            valoApiAgents = agents_data
            valoApiTitles = titles_data
            valoApiPlayerCards = cards_data
            
        except Exception as e:
            self.log(f"Error fetching API data: {e}")
            return {"Players": {}, "time": int(time.time()), "map": self.current_map}

        final_final_json = {
            "Players": {},
            "time": int(time.time()),
            "map": self.current_map
        }
        final_json = final_final_json["Players"]

        if state == "game":
            PlayerInventorys = PlayerInventorys["Loadouts"]

            # Collect all buddy UUIDs
            all_buddy_uuids = set()
            for inv_data in PlayerInventorys:
                inv = inv_data["Loadout"]
                for skin in inv["Items"]:
                    for socket in inv["Items"][skin]["Sockets"]:
                        if socket == sockets["skin_buddy"]:
                            buddy_uuid = inv["Items"][skin]["Sockets"][socket]["Item"]["ID"]
                            if buddy_uuid:
                                all_buddy_uuids.add(buddy_uuid)

            buddy_info_map = await self.get_buddy_info_batch(list(all_buddy_uuids))

            for i, inv_data in enumerate(PlayerInventorys):
                PlayerInventory = inv_data["Loadout"]
                player_subject = players[i]["Subject"]

                final_json[player_subject] = {}

                # Name
                if hide_names:
                    for agent in valoApiAgents["data"]:
                        if agent["uuid"] == players[i]["CharacterID"]:
                            final_json[player_subject]["Name"] = agent["displayName"]
                            break
                else:
                    final_json[player_subject]["Name"] = names.get(player_subject, "Unknown")

                final_json[player_subject]["Team"] = players[i]["TeamID"]
                final_json[player_subject]["Level"] = players[i]["PlayerIdentity"]["AccountLevel"]

                # Title
                for title in valoApiTitles["data"]:
                    if title["uuid"] == players[i]["PlayerIdentity"]["PlayerTitleID"]:
                        final_json[player_subject]["Title"] = title["titleText"]
                        break

                # Player Card
                for card in valoApiPlayerCards["data"]:
                    if card["uuid"] == players[i]["PlayerIdentity"]["PlayerCardID"]:
                        final_json[player_subject]["PlayerCard"] = card["largeArt"]
                        break

                # Agent
                for agent in valoApiAgents["data"]:
                    if agent["uuid"] == players[i]["CharacterID"]:
                        final_json[player_subject]["AgentArtworkName"] = agent["displayName"] + "Artwork"
                        final_json[player_subject]["Agent"] = agent["displayIcon"]
                        break

                # Sprays
                final_json[player_subject]["Sprays"] = {}
                spray_selections = [
                    s for s in PlayerInventory.get("Expressions", {}).get("AESSelections", [])
                    if s.get("TypeID") == "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
                ]
                for j, spray in enumerate(spray_selections):
                    final_json[player_subject]["Sprays"][j] = {}
                    for sprayApi in valoApiSprays["data"]:
                        if spray["AssetID"].lower() == sprayApi["uuid"].lower():
                            final_json[player_subject]["Sprays"][j] = {
                                "displayName": sprayApi["displayName"],
                                "displayIcon": sprayApi["displayIcon"],
                                "fullTransparentIcon": sprayApi["fullTransparentIcon"]
                            }
                            break

                # Weapons
                final_json[player_subject]["Weapons"] = {}

                for skin in PlayerInventory["Items"]:
                    final_json[player_subject]["Weapons"][skin] = {}

                    for socket in PlayerInventory["Items"][skin]["Sockets"]:
                        for var_socket in sockets:
                            if socket == sockets[var_socket]:
                                final_json[player_subject]["Weapons"][skin][var_socket] = \
                                    PlayerInventory["Items"][skin]["Sockets"][socket]["Item"]["ID"]

                    # Buddy info
                    buddy_uuid = None
                    for socket in PlayerInventory["Items"][skin]["Sockets"]:
                        if socket == sockets["skin_buddy"]:
                            buddy_uuid = PlayerInventory["Items"][skin]["Sockets"][socket]["Item"]["ID"]
                            break

                    if buddy_uuid and buddy_uuid in buddy_info_map:
                        info = buddy_info_map[buddy_uuid]
                        final_json[player_subject]["Weapons"][skin].update({
                            "buddy_uuid": buddy_uuid,
                            "buddy_displayName": info["displayName"],
                            "buddy_displayIcon": info["displayIcon"]
                        })

                    # Weapon and skin info
                    for weapon in valApiWeapons["data"]:
                        if skin == weapon["uuid"]:
                            final_json[player_subject]["Weapons"][skin]["weapon"] = weapon["displayName"]

                            skin_uuid = PlayerInventory["Items"][skin]["Sockets"][sockets["skin"]]["Item"]["ID"]
                            for skinApi in weapon["skins"]:
                                if skinApi["uuid"] == skin_uuid:
                                    final_json[player_subject]["Weapons"][skin]["skinDisplayName"] = skinApi["displayName"]

                                    chroma_uuid = PlayerInventory["Items"][skin]["Sockets"][sockets["skin_chroma"]]["Item"]["ID"]
                                    for chroma in skinApi["chromas"]:
                                        if chroma["uuid"] == chroma_uuid:
                                            icon = chroma.get("displayIcon") or chroma.get("fullRender") or \
                                                   skinApi.get("displayIcon") or skinApi["levels"][0].get("displayIcon")
                                            final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = icon
                                            break

                                    if skinApi["displayName"].startswith(("Standard", "Melee")):
                                        final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = weapon["displayIcon"]
                                    break
                            break

        return final_final_json

    def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            try:
                loop = self._get_loop()
                loop.run_until_complete(self._session.close())
            except Exception:
                pass
        self._session = None
