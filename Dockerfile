FROM mcr.microsoft.com/playwright:v1.63.0-noble
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY *.mjs ./
USER pwuser
ENV NODE_ENV=production PORT=10000
EXPOSE 10000
CMD ["node", "server.mjs"]
