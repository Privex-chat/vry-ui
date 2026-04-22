import time


class Coregame:
    def __init__(self, Requests, log):
        self.log = log
        self.Requests = Requests
        self.response = ""

    def get_coregame_match_id(self):
        try:
            self.response = self.Requests.fetch(
                url_type="glz",
                endpoint=f"/core-game/v1/players/{self.Requests.puuid}",
                method="get",
            )
            if not self.response or self.response.get("errorCode") == "RESOURCE_NOT_FOUND":
                return 0
            match_id = self.response['MatchID']
            self.log(f"retrieved coregame match id: '{match_id}'")
            return match_id
        except (KeyError, TypeError):
            self.log("cannot find coregame match id (first attempt)")
            time.sleep(5)
            try:
                self.response = self.Requests.fetch(
                    url_type="glz",
                    endpoint=f"/core-game/v1/players/{self.Requests.puuid}",
                    method="get",
                )
                if not self.response or self.response.get("errorCode") == "RESOURCE_NOT_FOUND":
                    return 0
                match_id = self.response['MatchID']
                self.log(f"retrieved coregame match id (retry): '{match_id}'")
                return match_id
            except (KeyError, TypeError):
                self.log("cannot find coregame match id (retry failed)")
                print(f"No match id found. {self.response}")
            return 0

    def get_coregame_stats(self):
        self.match_id = self.get_coregame_match_id()
        if self.match_id != 0:
            return self.Requests.fetch(
                url_type="glz",
                endpoint=f"/core-game/v1/matches/{self.match_id}",
                method="get",
            )
        return None

    def get_current_map(self, map_urls, map_splashes) -> dict:
        """
        Abstracts get_coregame_stats() to get the current map name and splash.
        Returns a dict with 'name' and 'splash', or 'N/A' when not in a match.
        """
        coregame_stats = self.get_coregame_stats()

        if (coregame_stats is None
                or "errorCode" in coregame_stats
                or "MapID" not in coregame_stats):
            return 'N/A'

        current_map = map_urls.get(coregame_stats['MapID'].lower())
        if current_map is None:
            return 'N/A'

        return {'name': current_map, 'splash': map_splashes.get(current_map)}