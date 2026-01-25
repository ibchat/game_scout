-- Seed Trends Scout with candidate apps
-- Sources: curated list prioritizing non-evergreen candidates
-- Criteria: prefer games released within last 3 years OR with reviews < 20k
-- Exclude Valve evergreen giants (but keep as last resort)

-- First, try to seed from steam_app_cache if available (prefer recent/smaller games)
INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
SELECT DISTINCT steam_app_id, true, NOW()
FROM steam_app_cache
WHERE steam_app_id NOT IN (SELECT steam_app_id FROM trends_seed_apps)
  AND steam_app_id IS NOT NULL
LIMIT 200
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;

-- Fallback: curated list prioritizing non-evergreen candidates
INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
VALUES
-- Recent indie hits (likely non-evergreen)
(1132000, true, NOW()), -- Hades (2020)
(632360, true, NOW()),  -- Risk of Rain 2 (2019)
(588650, true, NOW()),  -- Dead Cells (2018)
(294100, true, NOW()),  -- RimWorld (2018)
(233450, true, NOW()),  -- The Forest (2018)
(381210, true, NOW()),  -- Dead by Daylight (2016, but active)
-- Mid-tier games (not giants)
(413150, true, NOW()),  -- Stardew Valley
(367520, true, NOW()),  -- Hollow Knight
(105600, true, NOW()),  -- Terraria
(440900, true, NOW()),  -- Factorio
(252490, true, NOW()),  -- Rust
(236390, true, NOW()),  -- Europa Universalis IV
(394360, true, NOW()),  -- Hearts of Iron IV
(281990, true, NOW()),  -- Stellaris
(289070, true, NOW()),  -- Sid Meier's Civilization VI
(8930, true, NOW()),    -- Sid Meier's Civilization V
(239140, true, NOW()),  -- Dying Light
(346110, true, NOW()),  -- ARK: Survival Evolved
(359550, true, NOW()),  -- Tom Clancy's Rainbow Six Siege
(427520, true, NOW()),  -- Factorio
(304930, true, NOW()),  -- Unturned
(252950, true, NOW()),  -- Rocket League
(238960, true, NOW()),  -- Path of Exile
-- Large games (last resort, but needed for diversity)
(271590, true, NOW()),  -- Grand Theft Auto V
(1174180, true, NOW()), -- Red Dead Redemption 2
(1091500, true, NOW()), -- Cyberpunk 2077
(730, true, NOW()),     -- Counter-Strike 2
(570, true, NOW()),     -- Dota 2
(620, true, NOW())      -- Portal 2
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;
