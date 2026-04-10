# InterviewPrep AI — Frontend

A Next.js application that provides a web interface for browsing, searching, and analyzing interview experience documents processed by the InterviewPrep AI data pipeline.

## Project Structure

```
ui/
  app/
    page.tsx                    # Landing page with search and stats overview
    documents/
      page.tsx                  # Filterable, paginated document list
      [id]/
        page.tsx                # Document detail with chunks
    search/
      page.tsx                  # Full-text and semantic search
    stats/
      page.tsx                  # Statistics dashboard
  components/
    layout/
      Header.tsx                # Site header with navigation
      Footer.tsx                # Site footer
    documents/
      DocumentCard.tsx          # Document summary card
      DocumentDetail.tsx        # Full document view
      FilterBar.tsx             # Filter dropdowns
      Pagination.tsx            # Page navigation
    search/
      SearchBar.tsx             # Search input with mode toggle
      SearchResults.tsx         # Full-text and semantic result lists
    stats/
      StatCard.tsx              # Single metric display
      CompanyTable.tsx          # Company ranking table
      TopicsChart.tsx           # Topic frequency bars
      OutcomeChart.tsx          # Outcome distribution bars
  lib/
    api.ts                      # Typed API client functions
    types.ts                    # TypeScript interfaces matching backend schemas
```

## Pages

- **Home (`/`)** — Search bar, quick stats, project description
- **Documents (`/documents`)** — Browse all documents with filters (platform, company, role, difficulty, outcome) and pagination
- **Document Detail (`/documents/[id]`)** — Full document content, metadata fields, and collapsible text chunks
- **Search (`/search`)** — Full-text search with keyword matching or semantic search with vector similarity. Filter by platform, company, difficulty.
- **Stats (`/stats`)** — Overview metrics, top companies, topic frequency, outcome distribution

## Local Setup

1. Install dependencies:
   ```
   cd ui
   npm install
   ```

2. Create `.env.local` from the example:
   ```
   cp .env.local.example .env.local
   ```

3. Set the backend URL in `.env.local`:
   ```
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
   ```

4. Start the dev server:
   ```
   npm run dev
   ```

   The app runs at `http://localhost:3000`.

## Docker

Build and run the frontend as a Docker container:

```bash
# From the ui/ directory
docker build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
  -t interviewprep-frontend .

docker run -p 3000:3000 interviewprep-frontend
```

**Important:** `NEXT_PUBLIC_API_BASE_URL` must be passed as a **build arg**, not a runtime env var. Next.js inlines `NEXT_PUBLIC_*` variables into the client JavaScript bundle at build time. Setting it via `docker run -e` has no effect on browser-side code.

The Dockerfile uses `output: "standalone"` (configured in `next.config.mjs`) to produce a self-contained Node.js server without `node_modules`.

## Cloud Run Deployment

The frontend runs on Cloud Run:

- **Memory:** 512Mi
- **CPU:** 1 vCPU
- **Min instances:** 0 (scales to zero when idle)

When deploying, rebuild the image with the backend's Cloud Run URL:

```bash
docker buildx build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://<BACKEND_CLOUD_RUN_URL> \
  -t us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/frontend:latest \
  --push .
```

## Backend Connection

All data is fetched from the FastAPI backend via the `NEXT_PUBLIC_API_BASE_URL` environment variable. The UI makes no direct database connections. The backend must be running for the UI to display data.
