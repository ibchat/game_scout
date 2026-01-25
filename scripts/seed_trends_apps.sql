-- Seed Trends Scout with candidate apps
-- Sources: curated list of popular indie/mid-tier games
-- Criteria: mix of genres, avoid only evergreen giants

-- First, try to seed from steam_app_cache if available
INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
SELECT DISTINCT steam_app_id, true, NOW()
FROM steam_app_cache
WHERE steam_app_id NOT IN (SELECT steam_app_id FROM trends_seed_apps)
  AND steam_app_id IS NOT NULL
LIMIT 200
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;

-- Fallback: curated list of popular games (diverse genres, not all giants)
INSERT INTO trends_seed_apps (steam_app_id, is_active, created_at)
VALUES
-- Indie hits
(413150, true, NOW()),  -- Stardew Valley
(367520, true, NOW()),  -- Hollow Knight
(1132000, true, NOW()), -- Hades
(632360, true, NOW()),  -- Risk of Rain 2
(588650, true, NOW()),  -- Dead Cells
(105600, true, NOW()),  -- Terraria
(440900, true, NOW()),  -- Factorio
(294100, true, NOW()),  -- RimWorld
(233450, true, NOW()),  -- The Forest
(252490, true, NOW()),  -- Rust
-- Strategy
(236390, true, NOW()),  -- Europa Universalis IV
(394360, true, NOW()),  -- Hearts of Iron IV
(281990, true, NOW()),  -- Stellaris
(289070, true, NOW()),  -- Sid Meier's Civilization VI
(8930, true, NOW()),    -- Sid Meier's Civilization V
-- Action/Adventure
(239140, true, NOW()),  -- Dying Light
(346110, true, NOW()),  -- ARK: Survival Evolved
(359550, true, NOW()),  -- Tom Clancy's Rainbow Six Siege
(381210, true, NOW()),  -- Dead by Daylight
(427520, true, NOW()),  -- Factorio
-- More indie
(304930, true, NOW()),  -- Unturned
(252950, true, NOW()),  -- Rocket League
(238960, true, NOW()),  -- Path of Exile
(271590, true, NOW()),  -- Grand Theft Auto V
(1174180, true, NOW()), -- Red Dead Redemption 2
(1091500, true, NOW()), -- Cyberpunk 2077
(730, true, NOW()),     -- Counter-Strike 2
(570, true, NOW()),     -- Dota 2
(620, true, NOW())      -- Portal 2
ON CONFLICT (steam_app_id) DO UPDATE SET is_active = EXCLUDED.is_active;
