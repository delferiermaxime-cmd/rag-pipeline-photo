# ── Stage 1 : installation des dépendances ────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

# FIX : package-lock.json sans le * — obligatoire pour --frozen-lockfile
COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile


# ── Stage 2 : build de production ─────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

# Lance le build — produit .next/standalone grâce à output:'standalone' dans next.config.js
RUN npm run build


# ── Stage 3 : image de production finale (légère) ─────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Utilisateur non-root pour la sécurité
RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

# Copie uniquement ce dont Next.js standalone a besoin pour tourner
COPY --from=builder /app/public                         ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone  ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static      ./.next/static

USER nextjs

EXPOSE 3000

# HOSTNAME=0.0.0.0 indispensable pour que Nginx puisse joindre le conteneur
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
