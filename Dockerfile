# Build context = racine du repo.
# Stage 1 : build du front (Vite/React) -> front/dist
# Stage 2 : serveur Express qui sert l'API (/api) et le front statique (front/dist)
#   docker build -t job-search-app .

FROM node:20-alpine AS front-build
WORKDIR /app/front
COPY front/package.json front/package-lock.json ./
RUN npm ci
COPY front/ ./
RUN npm run build

# debian (glibc) plutot qu'alpine : evite de compiler lxml/selenium depuis les
# sources (pas de wheels manylinux compatibles musl).
FROM node:20-bookworm-slim AS runtime

# Python + le pipeline de scraping : le bouton "Lancer une recherche" et
# "Preparer candidature" du front spawnent `python3` (server/services/searchRunner.js,
# server/repositories/jsonApplicationsRepository.js) avec PROJECT_ROOT=/app comme cwd.
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY main.py pipeline.py ./
COPY agents/ ./agents/
COPY analyzers/ ./analyzers/
COPY applications/ ./applications/
COPY cv_generator/ ./cv_generator/
COPY config/ ./config/
COPY filters/ ./filters/
COPY hermes_commands/ ./hermes_commands/
COPY notifications/ ./notifications/
COPY scrapers/ ./scrapers/
COPY storage/ ./storage/
COPY utils/ ./utils/

WORKDIR /app/server
COPY server/package.json server/package-lock.json ./
RUN npm ci --omit=dev

COPY server/ ./
COPY --from=front-build /app/front/dist /app/front/dist

# front/public/data et data/ sont generes a l'execution (pipeline Python /
# actions utilisateur) : jamais dans le repo, monter en volume Coolify.
RUN mkdir -p /app/data /app/front/public/data && chown -R node:node /app
USER node

ENV NODE_ENV=production
EXPOSE 3001
CMD ["node", "index.js"]
