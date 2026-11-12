FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
ARG NEXT_PUBLIC_VED_API_URL=/api
ARG NEXT_PUBLIC_VAPID_PUBLIC_KEY=
ARG VED_BACKEND_INTERNAL_URL=http://backend:8000
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_VED_API_URL=${NEXT_PUBLIC_VED_API_URL} \
    NEXT_PUBLIC_VAPID_PUBLIC_KEY=${NEXT_PUBLIC_VAPID_PUBLIC_KEY} \
    VED_BACKEND_INTERNAL_URL=${VED_BACKEND_INTERNAL_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD wget -qO /dev/null http://127.0.0.1:3000/ || exit 1
CMD ["node", "server.js"]
