FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.js ./

RUN mkdir -p /app/auth_info_baileys && chown node:node /app/auth_info_baileys

ENV NODE_ENV=production
USER node
EXPOSE 3001
CMD ["node", "server.js"]
