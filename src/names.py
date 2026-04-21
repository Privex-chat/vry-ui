import re
import time
import requests


class Names:

    def __init__(self, Requests, log):
        self.Requests = Requests
        self.log = log
        # Per-session incognito name cache: puuid -> (resolved_name_or_None, timestamp)
        self._incognito_cache = {}
        self._incognito_cache_ttl = 3600  # 1 hour — names don't change mid-session

    def get_name_from_puuid(self, puuid):
        response = requests.put(
            self.Requests.pd_url + "/name-service/v2/players",
            headers=self.Requests.get_headers(),
            json=[puuid],
            verify=False,
        )
        data = response.json()[0]
        return data["GameName"] + "#" + data["TagLine"]

    def get_multiple_names_from_puuid(self, puuids):
        response = requests.put(
            self.Requests.pd_url + "/name-service/v2/players",
            headers=self.Requests.get_headers(),
            json=puuids,
            verify=False,
        )

        if 'errorCode' in response.json():
            self.log(f'{response.json()["errorCode"]}, new token retrieved')
            response = requests.put(
                self.Requests.pd_url + "/name-service/v2/players",
                headers=self.Requests.get_headers(refresh=True),
                json=puuids,
                verify=False,
            )

        name_dict = {}
        for player in response.json():
            puuid = player["Subject"]
            game_name = player.get("GameName", "")
            tag_line = player.get("TagLine", "")

            if game_name:
                name_dict[puuid] = f"{game_name}#{tag_line}"
            else:
                # GameName is empty — player is in incognito/streamer mode.
                # Try to resolve via vtl.lol, caching the result.
                resolved = self._resolve_incognito(puuid)
                name_dict[puuid] = resolved if resolved else ""

        return name_dict

    def _resolve_incognito(self, puuid):
        """
        Attempt to look up the real in-game name for an incognito player via
        vtl.lol.  Results are cached per-session with a 1-hour TTL.  Returns
        the name string on success, or None on failure.  Never makes more than
        one network request per PUUID per session.
        """
        cached = self._incognito_cache.get(puuid)
        if cached is not None:
            name, ts = cached
            if time.time() - ts < self._incognito_cache_ttl:
                return name  # May be None if previous lookup failed

        name = None
        try:
            resp = requests.get(
                f"https://vtl.lol/id/{puuid}",
                timeout=3,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                html = resp.text
                # vtl.lol title is usually "Name#Tag | vtl.lol" or "Name#Tag - vtl.lol"
                m = re.search(r'<title>\s*([^<|–]+)', html, re.IGNORECASE)
                if m:
                    candidate = m.group(1).strip()
                    # Strip trailing separator chars and site name
                    candidate = re.sub(r'\s*[|–\-]+\s*vtl\.lol.*$', '', candidate, flags=re.IGNORECASE).strip()
                    if '#' in candidate and len(candidate) > 2:
                        name = candidate
                        self.log(f"vtl.lol resolved incognito PUUID {puuid[:8]}... -> {name}")
        except Exception as e:
            self.log(f"vtl.lol lookup failed for {puuid[:8]}...: {e}")

        self._incognito_cache[puuid] = (name, time.time())
        return name

    def get_names_from_puuids(self, players):
        players_puuid = [player["Subject"] for player in players]
        return self.get_multiple_names_from_puuid(players_puuid)

    def get_players_puuid(self, Players):
        return [player["Subject"] for player in Players]

    def clear_incognito_cache(self):
        """Reset cache between game sessions."""
        self._incognito_cache.clear()
