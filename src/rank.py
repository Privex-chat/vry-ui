class Rank:
    def __init__(self, Requests, log, content, ranks_before):
        self.Requests = Requests
        self.log = log
        self.ranks_before = ranks_before
        self.content = content
        self.requestMap = {}

    def get_request(self, puuid):
        if puuid in self.requestMap:
            return self.requestMap[puuid]

        response = self.Requests.fetch('pd', f"/mmr/v1/players/{puuid}", "get")
        self.requestMap[puuid] = response
        return response

    def invalidate_cached_responses(self):
        self.requestMap = {}

    def get_rank(self, puuid, seasonID):
        response = self.get_request(puuid)
        final = {
            "rank": 0,
            "rr": 0,
            "leaderboard": 0,
            "peakrank": 0,
            "wr": "N/A",
            "numberofgames": 0,
            "peakrankact": None,
            "peakrankep": None,
            "statusgood": False,
            "statuscode": None,
        }

        # Guard against None response (e.g. connection failure)
        if response is None:
            self.log(f"get_rank: None response for puuid {puuid}")
            peak_rank_act_ep = self.content.get_act_episode_from_act_id(seasonID) if seasonID else {"act": None, "episode": None}
            final["peakrankact"] = peak_rank_act_ep.get("act")
            final["peakrankep"] = peak_rank_act_ep.get("episode")
            return final

        r = {}
        try:
            if response.ok:
                r = response.json()
                seasonal = (r.get("QueueSkills") or {}).get("competitive", {}).get("SeasonalInfoBySeasonID") or {}
                season_data = seasonal.get(seasonID) if seasonID else None

                if season_data:
                    rankTIER = season_data["CompetitiveTier"]
                    if int(rankTIER) >= 21:
                        final["rank"] = rankTIER
                        final["rr"] = season_data["RankedRating"]
                        final["leaderboard"] = season_data["LeaderboardRank"]
                    elif int(rankTIER) not in (0, 1, 2):
                        final["rank"] = rankTIER
                        final["rr"] = season_data["RankedRating"]
                        final["leaderboard"] = 0
                    else:
                        final["rank"] = 0
                        final["rr"] = 0
                        final["leaderboard"] = 0
                else:
                    final["rank"] = 0
                    final["rr"] = 0
                    final["leaderboard"] = 0
            else:
                self.log("failed getting rank")
                self.log(response.text)
                final["rank"] = 0
                final["rr"] = 0
                final["leaderboard"] = 0
        except TypeError:
            final["rank"] = 0
            final["rr"] = 0
            final["leaderboard"] = 0
        except KeyError:
            final["rank"] = 0
            final["rr"] = 0
            final["leaderboard"] = 0

        max_rank = final["rank"] or 0
        max_rank_season = seasonID
        competitive = (r.get("QueueSkills") or {}).get("competitive") or {}
        seasons = competitive.get("SeasonalInfoBySeasonID")
        if seasons is not None:
            for season in seasons:
                if seasons[season].get("WinsByTier") is not None:
                    for winByTier in seasons[season]["WinsByTier"]:
                        if season in self.ranks_before:
                            if int(winByTier) > 20:
                                winByTier = int(winByTier) + 3
                        if int(winByTier) > max_rank:
                            max_rank = int(winByTier)
                            max_rank_season = season
        final["peakrank"] = max_rank

        try:
            if seasonID:
                season_data = (r.get("QueueSkills") or {}).get("competitive", {}).get(
                    "SeasonalInfoBySeasonID", {}
                ).get(seasonID, {})
                wins = season_data.get("NumberOfWinsWithPlacements", 0)
                total_games = season_data.get("NumberOfGames", 0)
                final["numberofgames"] = total_games
                try:
                    wr = int(wins / total_games * 100)
                except ZeroDivisionError:
                    wr = 100
            else:
                wr = "N/A"
        except (KeyError, TypeError):
            wr = "N/A"

        final["wr"] = wr
        final["statusgood"] = response.ok
        final["statuscode"] = response.status_code

        # Peak rank act and ep
        peak_rank_act_ep = self.content.get_act_episode_from_act_id(max_rank_season) if max_rank_season else {"act": None, "episode": None}
        final["peakrankact"] = peak_rank_act_ep.get("act")
        final["peakrankep"] = peak_rank_act_ep.get("episode")
        return final


if __name__ == "__main__":
    from constants import before_ascendant_seasons, version, NUMBERTORANKS
    from requestsV import Requests
    from logs import Logging
    from errors import Error
    import urllib3
    import pyperclip
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    Logging = Logging()
    log = Logging.log

    ErrorSRC = Error(log)

    Requests = Requests(version, log, ErrorSRC)

    s_id = "67e373c7-48f7-b422-641b-079ace30b427"

    r = Rank(Requests, log, before_ascendant_seasons)

    res = r.get_rank("", s_id)
    print(res)