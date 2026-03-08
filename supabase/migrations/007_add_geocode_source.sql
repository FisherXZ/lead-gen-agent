-- Add geocode_source to track which tier provided coordinates
ALTER TABLE projects ADD COLUMN IF NOT EXISTS geocode_source TEXT;
-- Values: 'eia_860', 'uspvdb', 'state_gis', 'county_centroid', null

COMMENT ON COLUMN projects.geocode_source IS
  'Which geocoding tier provided lat/lon: eia_860, uspvdb, state_gis, county_centroid';
