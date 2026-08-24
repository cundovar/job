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

FROM node:20-alpine AS runtime
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
