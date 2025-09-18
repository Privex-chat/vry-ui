import time
import requests
from colr import color
from src.constants import sockets, hide_names
import json
import concurrent.futures
from threading import Lock

class Loadouts:
    def __init__(self, Requests, log, colors, Server, current_map):
        self.Requests = Requests
        self.log = log
        self.colors = colors
        self.Server = Server
        self.current_map = current_map
        self.buddy_cache = {}
        self.cache_lock = Lock()
        

        self._preload_buddies()

    def _preload_buddies(self):
        try:
            response = requests.get("https://valorant-api.com/v1/buddies", timeout=10)
            if response.status_code == 200:
                buddies_data = response.json()
                if buddies_data.get("status") == 200 and buddies_data.get("data"):
                    with self.cache_lock:
                        for buddy in buddies_data["data"]:
                            self.buddy_cache[buddy["uuid"]] = {
                                "displayName": buddy["displayName"],
                                "displayIcon": buddy["displayIcon"]
                            }
                    self.log(f"Pre-loaded {len(self.buddy_cache)} buddies to cache")
        except Exception as e:
            self.log(f"Failed to pre-load buddies: {e}")

    def get_buddy_info_batch(self, buddy_uuids):
        if not buddy_uuids:
            return {}
        
        uncached_uuids = []
        results = {}
        
        with self.cache_lock:
            for uuid in buddy_uuids:
                if uuid in self.buddy_cache:
                    results[uuid] = self.buddy_cache[uuid]
                else:
                    uncached_uuids.append(uuid)
        
        if not uncached_uuids:
            return results
        
        def fetch_single_buddy(buddy_uuid):
            try:
                response = requests.get(
                    f"https://valorant-api.com/v1/buddies/{buddy_uuid}", 
                    timeout=5
                )
                if response.status_code == 200:
                    buddy_data = response.json()
                    if buddy_data.get("status") == 200 and buddy_data.get("data"):
                        data = buddy_data["data"]
                        buddy_info = {
                            "displayName": data["displayName"],
                            "displayIcon": data["displayIcon"]
                        }
                        with self.cache_lock:
                            self.buddy_cache[buddy_uuid] = buddy_info
                        return buddy_uuid, buddy_info
            except Exception as e:
                self.log(f"Error fetching buddy {buddy_uuid}: {e}")
            return buddy_uuid, None
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_uuid = {
                executor.submit(fetch_single_buddy, uuid): uuid 
                for uuid in uncached_uuids
            }
        
            try:
                for future in concurrent.futures.as_completed(future_to_uuid, timeout=15):
                    uuid, buddy_info = future.result()
                    if buddy_info:
                        results[uuid] = buddy_info
            except concurrent.futures.TimeoutError:
                self.log("Timeout waiting for buddy requests - continuing with partial results")
        
        return results

    def get_match_loadouts(self, match_id, players, weaponChoose, valoApiSkins, names, state="game"):
        playersBackup = players
        weaponLists = {}
        valApiWeapons = requests.get("https://valorant-api.com/v1/weapons", timeout=10).json()
        
        if state == "game":
            team_id = "Blue"
            PlayerInventorys = self.Requests.fetch("glz", f"/core-game/v1/matches/{match_id}/loadouts", "get")
        elif state == "pregame":
            pregame_stats = players
            players = players["AllyTeam"]["Players"]
            team_id = pregame_stats['Teams'][0]['TeamID']
            PlayerInventorys = self.Requests.fetch("glz", f"/pregame/v1/matches/{match_id}/loadouts", "get")
        
        for player in range(len(players)):
            if team_id == "Red":
                invindex = player + len(players) - len(PlayerInventorys["Loadouts"])
            else:
                invindex = player
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
                            weaponLists.update({players[player]["Subject"]: color(skin_display_name, fore=rgb_color)})
        
        final_json = self.convertLoadoutToJsonArray(PlayerInventorys, playersBackup, state, names)
        self.log(f"json for website: {final_json}")
        self.Server.send_payload("matchLoadout", final_json)
        return [weaponLists, final_json]

    def convertLoadoutToJsonArray(self, PlayerInventorys, players, state, names):
        
        try:
            valoApiSprays = requests.get("https://valorant-api.com/v1/sprays", timeout=10)
            valoApiWeapons = requests.get("https://valorant-api.com/v1/weapons", timeout=10)
            valoApiAgents = requests.get("https://valorant-api.com/v1/agents", timeout=10)
            valoApiTitles = requests.get("https://valorant-api.com/v1/playertitles", timeout=10)
            valoApiPlayerCards = requests.get("https://valorant-api.com/v1/playercards", timeout=10)
        except requests.exceptions.RequestException as e:
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
            
            all_buddy_uuids = set()
            for i in range(len(PlayerInventorys)):
                PlayerInventory = PlayerInventorys[i]["Loadout"]
                for skin in PlayerInventory["Items"]:
                    for socket in PlayerInventory["Items"][skin]["Sockets"]:
                        if socket == sockets["skin_buddy"]:
                            buddy_uuid = PlayerInventory["Items"][skin]["Sockets"][socket]["Item"]["ID"]
                            if buddy_uuid:
                                all_buddy_uuids.add(buddy_uuid)
            
            self.log(f"Fetching {len(all_buddy_uuids)} unique buddies...")
            buddy_info_map = self.get_buddy_info_batch(list(all_buddy_uuids))
            self.log(f"Successfully fetched {len(buddy_info_map)} buddy details")
            
            for i in range(len(PlayerInventorys)):
                PlayerInventory = PlayerInventorys[i]["Loadout"]
                player_subject = players[i]["Subject"]
                
                final_json[player_subject] = {}

                if hide_names:
                    for agent in valoApiAgents.json()["data"]:
                        if agent["uuid"] == players[i]["CharacterID"]:
                            final_json[player_subject]["Name"] = agent["displayName"]
                            break
                else:
                    final_json[player_subject]["Name"] = names[player_subject]

                final_json[player_subject]["Team"] = players[i]["TeamID"]
                final_json[player_subject]["Level"] = players[i]["PlayerIdentity"]["AccountLevel"]

                for title in valoApiTitles.json()["data"]:
                    if title["uuid"] == players[i]["PlayerIdentity"]["PlayerTitleID"]:
                        final_json[player_subject]["Title"] = title["titleText"]
                        break

                for PCard in valoApiPlayerCards.json()["data"]:
                    if PCard["uuid"] == players[i]["PlayerIdentity"]["PlayerCardID"]:
                        final_json[player_subject]["PlayerCard"] = PCard["largeArt"]
                        break

                for agent in valoApiAgents.json()["data"]:
                    if agent["uuid"] == players[i]["CharacterID"]:
                        final_json[player_subject]["AgentArtworkName"] = agent["displayName"] + "Artwork"
                        final_json[player_subject]["Agent"] = agent["displayIcon"]
                        break

                final_json[player_subject]["Sprays"] = {}
                spray_selections = [
                    s for s in PlayerInventory.get("Expressions", {}).get("AESSelections", [])
                    if s.get("TypeID") == "d5f120f8-ff8c-4aac-92ea-f2b5acbe9475"
                ]
                for j, spray in enumerate(spray_selections):
                    final_json[player_subject]["Sprays"][j] = {}
                    for sprayValApi in valoApiSprays.json()["data"]:
                        if spray["AssetID"].lower() == sprayValApi["uuid"].lower():
                            final_json[player_subject]["Sprays"][j].update({
                                "displayName": sprayValApi["displayName"],
                                "displayIcon": sprayValApi["displayIcon"],
                                "fullTransparentIcon": sprayValApi["fullTransparentIcon"]
                            })
                            break

                final_json[player_subject]["Weapons"] = {}
                
                for skin in PlayerInventory["Items"]:
                    final_json[player_subject]["Weapons"][skin] = {}

                    for socket in PlayerInventory["Items"][skin]["Sockets"]:
                        for var_socket in sockets:
                            if socket == sockets[var_socket]:
                                final_json[player_subject]["Weapons"][skin][var_socket] = \
                                    PlayerInventory["Items"][skin]["Sockets"][socket]["Item"]["ID"]


                    buddy_uuid = None
                    for socket in PlayerInventory["Items"][skin]["Sockets"]:
                        if socket == sockets["skin_buddy"]:
                            buddy_uuid = PlayerInventory["Items"][skin]["Sockets"][socket]["Item"]["ID"]
                            break

                    if buddy_uuid and buddy_uuid in buddy_info_map:
                        buddy_info = buddy_info_map[buddy_uuid]
                        final_json[player_subject]["Weapons"][skin].update({
                            "buddy_uuid": buddy_uuid,
                            "buddy_displayName": buddy_info["displayName"],
                            "buddy_displayIcon": buddy_info["displayIcon"]
                        })

                    for weapon in valoApiWeapons.json()["data"]:
                        if skin == weapon["uuid"]:
                            final_json[player_subject]["Weapons"][skin]["weapon"] = weapon["displayName"]
                            
                            skin_uuid = PlayerInventory["Items"][skin]["Sockets"][sockets["skin"]]["Item"]["ID"]
                            for skinValApi in weapon["skins"]:
                                if skinValApi["uuid"] == skin_uuid:
                                    final_json[player_subject]["Weapons"][skin]["skinDisplayName"] = skinValApi["displayName"]
                                    
                                    chroma_uuid = PlayerInventory["Items"][skin]["Sockets"][sockets["skin_chroma"]]["Item"]["ID"]
                                    for chroma in skinValApi["chromas"]:
                                        if chroma["uuid"] == chroma_uuid:
                                            if chroma["displayIcon"]:
                                                final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = chroma["displayIcon"]
                                            elif chroma["fullRender"]:
                                                final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = chroma["fullRender"]
                                            elif skinValApi["displayIcon"]:
                                                final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = skinValApi["displayIcon"]
                                            else:
                                                final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = skinValApi["levels"][0]["displayIcon"]
                                            break
                                    
                                    if skinValApi["displayName"].startswith("Standard") or skinValApi["displayName"].startswith("Melee"):
                                        final_json[player_subject]["Weapons"][skin]["skinDisplayIcon"] = weapon["displayIcon"]
                                    break
                            break

        return final_final_json
