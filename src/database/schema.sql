-- =============================================================================
-- DATABASE SCHEMA: FOOTBALL ETL & ANALYTICS
-- =============================================================================

-- 1. DIMENSION TABLE: LEAGUES
CREATE TABLE IF NOT EXISTS dim_leagues (
    league_id       INTEGER PRIMARY KEY,
    league_name     VARCHAR(100) NOT NULL,
    country_code    VARCHAR(10) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. DIMENSION TABLE: TEAMS
CREATE TABLE IF NOT EXISTS dim_teams (
    team_id         VARCHAR(50) PRIMARY KEY,
    team_name       VARCHAR(150) NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. FACT TABLE: MATCHES (Fixtures, schedules, and completed match results)
CREATE TABLE IF NOT EXISTS fact_matches (
    match_id        VARCHAR(50) PRIMARY KEY,
    league_id       INTEGER NOT NULL,
    season          VARCHAR(20) NOT NULL,
    
    -- Round and Tournament Stage Classification
    round           VARCHAR(20) NOT NULL,          -- e.g. '1', 'playoff', '1/8', '1/4', '1/2', 'final'
    round_name      VARCHAR(100) NOT NULL,         -- e.g. 'Round 1', 'Play-offs', 'Round of 16', 'Quarter-Finals', 'Final'
    stage           VARCHAR(50) NOT NULL,          -- 'LEAGUE_STAGE', 'PLAYOFF', 'KNOCKOUT'
    
    -- Schedule & Kickoff Timestamps
    match_date      DATE,                          -- 'YYYY-MM-DD'
    match_time      TIME,                          -- 'HH:MM:SS'
    utc_time        TIMESTAMP,                     -- 'YYYY-MM-DDTHH:MM:SSZ'
    
    -- Participating Teams
    home_team_id    VARCHAR(50) NOT NULL,
    away_team_id    VARCHAR(50) NOT NULL,
    
    -- Match Status
    status          VARCHAR(30) NOT NULL,          -- 'SCHEDULED', 'FINISHED', 'CANCELLED', 'POSTPONED', 'LIVE'
    
    -- Scores & Result Outcomes (NULL for upcoming/scheduled matches)
    score           VARCHAR(20),                   -- '4 - 2' or NULL if unplayed
    home_score      INTEGER,                       -- NULL if unplayed
    away_score      INTEGER,                       -- NULL if unplayed
    match_result    CHAR(1),                       -- 'H' (Home Win), 'D' (Draw), 'A' (Away Win), or NULL
    home_points     INTEGER,                       -- 3, 1, 0 or NULL
    away_points     INTEGER,                       -- 3, 1, 0 or NULL
    goal_difference INTEGER,                       -- home_score - away_score or NULL
    
    -- Metadata
    match_url       TEXT,
    loaded_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Key Constraints
    CONSTRAINT fk_matches_league FOREIGN KEY (league_id) REFERENCES dim_leagues(league_id),
    CONSTRAINT fk_matches_home_team FOREIGN KEY (home_team_id) REFERENCES dim_teams(team_id),
    CONSTRAINT fk_matches_away_team FOREIGN KEY (away_team_id) REFERENCES dim_teams(team_id)
);

-- =============================================================================
-- INDEXES FOR QUERY OPTIMIZATION & DBT JOIN PERFORMANCE
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_matches_league_season ON fact_matches(league_id, season);
CREATE INDEX IF NOT EXISTS idx_matches_stage ON fact_matches(stage);
CREATE INDEX IF NOT EXISTS idx_matches_round ON fact_matches(round);
CREATE INDEX IF NOT EXISTS idx_matches_date ON fact_matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON fact_matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_home_team ON fact_matches(home_team_id);
CREATE INDEX IF NOT EXISTS idx_matches_away_team ON fact_matches(away_team_id);
