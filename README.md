# Aussie Tracker

A static site (`docs/`) plus a daily script that refreshes `docs/players.json` from the Bzzoiro Sports Data
(BSD) football API, which is free with no daily quota. Until `players.json` has data, the page shows sample numbers
and a banner saying so.

## Setup
1. **Make a GitHub repo** and upload everything in this folder (including the hidden `.github` folder).
2. **Get a free API key.** Register at sports.bzzoiro.com/register, then copy your token.
3. **Add the key as a secret.** Repo > Settings > Secrets and variables > Actions > New repository secret.
   Name: `BSD_API_KEY`. Value: your token. The key never appears on the site.
4. **Turn on the website.** Repo > Settings > Pages > Deploy from a branch > `main` and `/docs`.
5. **Run it once.** Repo > Actions > Update stats > Run workflow. After that it runs daily at 21:30 UTC.
6. **Read the log.** Lines starting with `!` mean a player could not be matched. Fix by adding `"id": 12345`
   to that player in `data/roster.json` (search the player on sports.bzzoiro.com to find the id in the URL).

## Things to know
- **Not verified against a live key.** I could not read BSD's response schema, so the script reads the field names
  the docs describe (`minutes_played`, `rating`, `goals`, `assists`, `event_date`, `home_score`...) and tolerates a few
  alternatives. If a column shows empty after the first run, open the Action log and check the raw response.
- **Coverage gaps.** BSD's coverage list includes the Premier League-level English divisions, La Liga, Serie A,
  Bundesliga, Ligue 1, Eredivisie, Liga Portugal, Scottish Premiership, Danish Superliga, Eliteserien and MLS.
  It does not list the Indian Super League (Jamie Maclaren) or the Croatian league (Fran Karacic), so those two
  will probably be skipped.
- **Photos and logos** load from BSD's image service. Competition logos use a guessed address and fall back to a
  letter badge if it is wrong. Check BSD's data licence page before making the site public.
- **Season totals** are summed from each player's match log since the season started (July for European leagues,
  January for MLS and Norway).
- **Adding or removing players.** Edit `data/roster.json` and the `P` list near the top of `docs/index.html`.
