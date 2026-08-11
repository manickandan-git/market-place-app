FROM node:22-alpine

WORKDIR /app

# Dependencies are installed into the image's own /app/node_modules.
# docker-compose.yml bind-mounts the rest of this directory over the image
# at runtime for hot reload, but overlays anonymous volumes on
# /app/node_modules and /app/.next so the host's (Windows) node_modules
# never shadows these Linux-built ones — same reasoning as the uv-based
# services only mounting their source dirs, not the whole service directory.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
