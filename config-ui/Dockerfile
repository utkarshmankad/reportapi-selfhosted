# Pinned by digest, not just tag, so a rebuild months from now pulls the
# exact same base layer instead of whatever "22-slim" resolves to then.
FROM node:22-slim@sha256:48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9 AS base

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 8080

CMD ["npm", "start"]
