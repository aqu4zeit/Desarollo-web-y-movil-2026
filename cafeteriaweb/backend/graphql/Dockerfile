FROM node:24-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.js .
USER node
EXPOSE 8090
CMD ["node", "server.js"]
