FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json .
COPY --from=builder /app/node_modules ./node_modules
ENV PORT=3000
EXPOSE 3000
HEALTHCHECK CMD wget -q --spider http://localhost:3000/ || exit 1
CMD ["node", "build"]
