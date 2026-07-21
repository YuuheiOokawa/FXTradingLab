FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* vars are inlined into the client JS bundle at BUILD time, not
# read at container runtime — a bug found during the BFF migration review:
# the previous Dockerfile had no ARG/ENV for these at all, so passing
# NEXT_PUBLIC_API_URL via docker-compose's `environment:` (a runtime-only
# mechanism) silently did nothing; every built image always shipped the
# hardcoded fallback URL regardless of docker-compose.yml. Must be passed as
# a build ARG (see docker-compose.yml's `build.args`), not `environment:`.
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system nodejs && adduser --system --ingroup nodejs nextjs

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

USER nextjs
EXPOSE 3000

CMD ["npm", "start"]
