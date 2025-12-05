# Local Pollution Reporting Software (Flask + HTML + Supabase)

A production-ready web app where citizens can upload geotagged reports of pollution. Built with Flask templates (HTML/CSS/JS) and Supabase (Auth, Postgres, Storage).

## Features
- Email/password signup/login (server-side using service role; for production you may prefer supabase-js on the client with OTP/email confirm).
- Create report with photo validation (≤10MB; JPEG/PNG/WEBP), auto-orient, EXIF stripping, resize (1920px) and 480px thumbnail.
- Optional reverse geocoding via OpenStreetMap Nominatim.
- Leaflet map with marker clustering, popups with photo + metadata, filter controls, synchronized list.
- Admin status changes with audit trail and CSV export.
- "My Reports" page with edit/delete when status is Open.
- Rate limit (5/hour per user) enforced via SQL function.
- BBox validation via environment variables.
