# Player rating methodology

Champions has two Classic rating rulesets. **World Cup Form** uses the original campaign formula documented below. **Prime Form** keeps the rolled historical roster but replaces each selectable player’s campaign rating with one stable career-prime estimate.

The draft pool treats every player-tournament record the same way. There are no fame bonuses, manual overrides, “icon” lists, or post-hoc boosts. A player from Bulgaria 1994 is evaluated with the same formula as a player from Brazil 2002.

## Sources and coverage

The generator fetches the `squads`, `player_appearances`, `goals`, and `qualified_teams` CSVs from [The Fjelstul World Cup Database](https://github.com/jfjelstul/worldcup).

- Squad membership, player names, broad positions, appearances, starts, goals, and team finish come from the database.
- Player-appearance coverage begins in 1970. For 1930–1966, the generator deliberately uses squad membership, goals, and team finish only; it does not fabricate match appearances.
- The source does not contain assists or exact minutes played. `assists` is stored as `null`. Minutes are an explicit estimate: **90 per start + 30 per substitute appearance**.
- Specific sub-positions are deterministic formation-role estimates because the source records only goalkeeper, defender, midfielder, and forward. A stable hash distributes defenders across CB/FB/WB, midfielders across DM/CM/CAM/W, and forwards across ST/CF/W. The broad source position remains authoritative for slot compatibility.

Each generated player keeps the underlying inputs in the JSON so the rating can be audited.

## Formula

All values are calculated per player, per tournament:

```text
rating = round(
  48
  + min(14, appearances × 1.8)
  + min(6, starts × 0.8)
  + min(7, estimatedMinutes ÷ 90)
  + min(14, goals × positionGoalWeight)
  + teamSuccessModifier
)
```

The result is clamped to **45–97**.

Position goal weights reward rare scoring from deeper positions without making goals irrelevant for forwards:

| Broad position | Goal weight |
| --- | ---: |
| GK | 5.0 |
| DEF | 3.2 |
| MID | 2.1 |
| FWD | 1.45 |

Team-success modifiers:

| Finish | Modifier |
| --- | ---: |
| Winner | +14 |
| Runner-up / final | +11 |
| Semifinal | +9 |
| Quarterfinal | +7 |
| Round of 16 | +5 |
| Second group stage | +4 |
| Other / group or first stage | +2 |

## Team strength

World Cup 2026 teams use the official FIFA/Coca-Cola Men’s World Ranking published **11 June 2026**. FIFA ranking points are linearly converted to a 58–94 game-strength range:

```text
strength = round(58 + ((fifaPoints - 1100) / (1880 - 1100)) × 36)
```

The result is clamped to 58–94. This single aggregate strength is split into small deterministic attack, defense, goalkeeper, and mental variations inside the match engine. It is not a full roster rating.

## Classic Prime Form

Prime Form is an optional game ruleset selected after the Classic formation. It does not rewrite the historical squad: `Argentina 2010` still contains the real 2010 roster, but Lionel Messi is displayed at his career-prime **94** while retaining his original 2010 World Cup Form rating of **77** for context.

The same player is linked across tournaments by the source `playerId`, so every version receives exactly the same prime rating.

### Curated elite benchmarks

The project contains an editorial benchmark table for 101 historically elite players. Examples include:

| Player | Prime rating |
| --- | ---: |
| Pelé | 96 |
| Diego Maradona | 95 |
| Franz Beckenbauer | 95 |
| Johan Cruyff | 95 |
| Ronaldo | 95 |
| Lionel Messi | 94 |
| Cristiano Ronaldo | 94 |
| Zinedine Zidane | 94 |

These are independent game-design estimates. They are not official FIFA ratings, EA Sports ratings, or factual measurements.

### Archive-wide fallback

Every other player receives a deterministic career-prime estimate from the strongest evidence available in this archive:

```text
translatedPeak = 66 + (bestWorldCupFormRating - 50) × 0.50
longevity      = min(2.5, (WorldCupCampaigns - 1) × 0.90)
experience     = min(1.5, totalWorldCupAppearances ÷ 16)
scoring        = min(1.5, totalWorldCupGoals ÷ 10)

primeRating = round(translatedPeak + longevity + experience + scoring)
```

Fallback ratings are clamped to **72–89**. The 90–96 band is therefore reserved for manually reviewed elite benchmarks instead of being reached from one exceptional World Cup campaign alone. This produces one consistent prime estimate for all 8,482 unique players.

Prime Form is intentionally a fun, opinionated alternate ruleset. Club-career statistics are not consistently available across the full 1930–2022 archive, so the fallback is a historical-football game model rather than a comprehensive club-career calculation.

## Interpretation limits

World Cup Form ratings describe performance and team success in one tournament—not full-career ability. Prime Form is a separate editorial estimate. Older tournaments have thinner event coverage, goalkeepers and defenders have fewer box-score events, and estimated minutes are intentionally coarse. All values are independent game inputs, not official FIFA or commercial video-game ratings.
